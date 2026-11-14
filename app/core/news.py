"""Titulares recientes de Yahoo Finance (los usan alertas, noticias y comunidad).

Fuente principal: ``yfinance.Search`` (devuelve ``relatedTickers`` y sirve para
filtrar por relevancia). Respaldo: ``Ticker.news``, que tiene otro formato y a
veces responde "Yahoo is down". Si fallan las dos, la alerta se envía igual,
sin contexto.

Un titular **acompaña** al movimiento, no lo explica con certeza. Por eso la
interfaz lo llama "Contexto" y no "Motivo".
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

NEWS_CACHE_TTL = 30 * 60
MAX_WORKERS = 8
MAX_AGE_HOURS = 72
PER_TICKER = 8

_cache: dict[str, tuple[float, list["Headline"]]] = {}


@dataclass(frozen=True, slots=True)
class Headline:
    id: str
    title: str
    publisher: str | None
    url: str | None
    published_at: int  # epoch (s)
    related: tuple[str, ...] = ()
    # Portada: la original (grande, para reducirla en el servidor) y la
    # miniatura cuadrada de 140 px que ya sirve Yahoo (para el email).
    image_url: str | None = None
    thumb_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["related"] = list(self.related)
        return data


def _parse_time(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def _images(thumbnail: Any, original: str | None = None) -> tuple[str | None, str | None]:
    """``(original, miniatura)`` de ``thumbnail.resolutions``: la más ancha y la más estrecha."""
    resolutions = [
        r for r in ((thumbnail or {}).get("resolutions") or [])
        if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"].startswith("https://")
    ]
    if not resolutions:
        return original, None
    by_width = sorted(resolutions, key=lambda r: r.get("width") or 0)
    small = by_width[0]["url"] if len(by_width) > 1 else None
    return original or by_width[-1]["url"], small


def normalize(item: dict[str, Any]) -> Headline | None:
    """Convierte un artículo de cualquiera de los dos formatos de yfinance."""
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    if content:  # Ticker.news (yfinance >= 0.2.50)
        title = content.get("title")
        published = _parse_time(content.get("pubDate") or content.get("displayTime"))
        provider = content.get("provider") or {}
        url = (content.get("canonicalUrl") or {}).get("url") or (content.get("clickThroughUrl") or {}).get("url")
        publisher = provider.get("displayName")
        related: tuple[str, ...] = ()
        uid = item.get("id") or content.get("id")
        thumbnail = content.get("thumbnail") or {}
        image, thumb = _images(thumbnail, thumbnail.get("originalUrl") if isinstance(thumbnail, dict) else None)
    else:  # yf.Search
        title = item.get("title")
        published = _parse_time(item.get("providerPublishTime"))
        url = item.get("link")
        publisher = item.get("publisher")
        related = tuple(item.get("relatedTickers") or ())
        uid = item.get("uuid")
        image, thumb = _images(item.get("thumbnail"))
    if not title or published is None:
        return None
    return Headline(
        id=str(uid or url or title),
        title=title.strip(),
        publisher=publisher,
        url=url,
        published_at=published,
        related=related,
        image_url=image,
        thumb_url=thumb,
    )


def _fetch(ticker: str) -> list[Headline]:
    raw: list[dict[str, Any]] = []
    try:
        raw = yf.Search(ticker, news_count=PER_TICKER, max_results=1).news or []
    except Exception:
        raw = []
    if not raw:
        try:
            raw = yf.Ticker(ticker).news or []
        except Exception:
            raw = []
    headlines = [h for h in (normalize(item) for item in raw) if h is not None]
    headlines.sort(key=lambda h: h.published_at, reverse=True)
    return headlines


def headlines_for(ticker: str) -> list[Headline]:
    """Titulares de ``ticker`` (cacheados 30 min), del más reciente al más antiguo."""
    hit = _cache.get(ticker)
    if hit and time.time() - hit[0] < NEWS_CACHE_TTL:
        return hit[1]
    headlines = _fetch(ticker)
    _cache[ticker] = (time.time(), headlines)
    return headlines


def _is_recent(headline: Headline, now: float, max_age_hours: int) -> bool:
    return now - headline.published_at <= max_age_hours * 3600


def relevance(headline: Headline, ticker: str, name: str | None) -> int:
    """2 si el titular nombra al activo, 1 si Yahoo lo marca como relacionado, 0 si no."""
    title = headline.title.lower()
    plain = ticker.lstrip("^").split("-")[0].split("=")[0].lower()
    first_word = (name or "").split(" ")[0].lower()
    if (first_word and len(first_word) > 2 and first_word in title) or (len(plain) > 2 and plain in title.split()):
        return 2
    if ticker in headline.related:
        return 1
    return 0


def best_headline(ticker: str, name: str | None = None, *, max_age_hours: int = 48, now: float | None = None) -> Headline | None:
    """Titular más relevante y reciente de las últimas ``max_age_hours`` (o ``None``).

    Si un titular nombra al activo, gana a uno que solo lo trae en
    ``relatedTickers``. A igual relevancia, gana el más reciente.
    """
    now = time.time() if now is None else now
    candidates = [
        (relevance(h, ticker, name), h.published_at, h)
        for h in headlines_for(ticker)
        if _is_recent(h, now, max_age_hours)
    ]
    candidates = [c for c in candidates if c[0] > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


def feed(tickers: list[str], *, limit: int = 25, now: float | None = None) -> list[tuple[Headline, list[str]]]:
    """Titulares recientes de varios tickers, sin repetir, del más nuevo al más viejo.

    Cada titular va con los tickers vigilados a los que se refiere: los que lo
    devolvieron en su búsqueda más los de ``relatedTickers``.
    """
    now = time.time() if now is None else now
    watched = set(tickers)
    # Una búsqueda por ticker: en paralelo, para que un feed de 12 activos sin
    # caché tarde lo que el más lento y no la suma de todos.
    if tickers:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tickers))) as pool:
            fetched = dict(zip(tickers, pool.map(headlines_for, tickers)))
    else:
        fetched = {}
    seen: dict[str, tuple[Headline, list[str]]] = {}
    for ticker in tickers:
        for headline in fetched[ticker]:
            if not _is_recent(headline, now, MAX_AGE_HOURS):
                continue
            entry = seen.setdefault(headline.id, (headline, [t for t in headline.related if t in watched]))
            if ticker not in entry[1]:
                entry[1].append(ticker)
    items = sorted(seen.values(), key=lambda e: e[0].published_at, reverse=True)
    return items[:limit]


def utc_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
