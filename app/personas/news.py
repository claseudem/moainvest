"""Noticias de los activos de la plataforma (Yahoo Finance vía ``yfinance``).

``news_for(tickers)`` devuelve las noticias recientes de esos tickers, ya
normalizadas para la tarjeta de COMUNIDAD:

    {"id", "ticker", "tickers", "title", "summary", "source", "published",
     "url", "image", "trend", "demo"}

``image`` es la miniatura que publica Yahoo (o ``None`` si no hay); la portada
de noticias del inicio la usa como imagen de la noticia principal.

``trend`` (``subir`` / ``bajar`` / ``medio``) es la tendencia que sugiere la
noticia para el activo o el mercado. Se estima con un léxico de palabras
alcistas y bajistas sobre el titular y el resumen (``trend_of``): es una
lectura orientativa, no un análisis de sentimiento profesional.

Para cada ticker se pide primero ``Ticker.news`` (trae resumen) y, si Yahoo no
responde, ``Search`` (solo titular). Cada ticker se guarda en caché
``NEWS_CACHE_TTL`` segundos. Si no llega ninguna noticia real, se devuelven las
de ``DEMO_NEWS``, marcadas con ``demo=True`` para que la página lo indique.

Para cambiar de proveedor basta con reemplazar ``_fetch_live``: el resto de la
app solo conoce el formato normalizado.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

NEWS_CACHE_TTL = 900
PER_TICKER = 4
MAX_WORKERS = 8
MAX_IMAGE_WIDTH = 1200

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _iso(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def _image(node: dict) -> str | None:
    """URL de la miniatura de Yahoo (``thumbnail``): la mayor resolución hasta ``MAX_IMAGE_WIDTH``."""
    thumb = node.get("thumbnail") or {}
    sizes = [r for r in thumb.get("resolutions") or [] if isinstance(r, dict) and r.get("url")]
    fitting = [r for r in sizes if (r.get("width") or 0) <= MAX_IMAGE_WIDTH] or sizes
    if fitting:
        return max(fitting, key=lambda r: r.get("width") or 0)["url"]
    return thumb.get("originalUrl") or None


# Raíces de palabras (inglés y español) que suelen acompañar subidas o bajadas.
_UP_WORDS = (
    "surge", "soar", "jump", "rall", "gain", "climb", "rise", "rising", "beat", "record high", "upgrade",
    "closes up", "shares up", "bull", "rebound", "boost", "outperform", "strong", "top estimates", "higher", "advance", "raises",
    "sube", "subid", "alza", "dispar", "repunt", "récord", "mejora", "crec", "gana", "eleva", "impuls",
)
_DOWN_WORDS = (
    "fall", "drop", "plunge", "tumble", "slump", "sink", "slide", "decline", "miss", "downgrade", "bear",
    "closes down", "shares down", "loss", "lower", "cut", "weak", "selloff", "sell-off", "crash", "lows", "fear", "warn", "worst",
    "cae", "caíd", "baja", "desplom", "pérdid", "retroced", "recort", "hunde", "debil", "temor",
)


def _hits(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for word in words if re.search(r"\b" + re.escape(word), text))


def trend_of(title: str, summary: str | None = None) -> str:
    """``subir``, ``bajar`` o ``medio`` según el balance de palabras del texto."""
    text = f"{title} {summary or ''}".lower()
    score = _hits(text, _UP_WORDS) - _hits(text, _DOWN_WORDS)
    return "subir" if score > 0 else "bajar" if score < 0 else "medio"


def _normalize_ticker_news(ticker: str, item: dict) -> dict | None:
    """Formato nuevo de ``Ticker.news``: los datos vienen dentro de ``content``."""
    content = item.get("content") or item
    title = content.get("title")
    if not title:
        return None
    url = (content.get("canonicalUrl") or {}).get("url") or (content.get("clickThroughUrl") or {}).get("url") or content.get("link")
    related = [t.get("symbol") for t in (content.get("finance") or {}).get("stockTickers") or [] if t.get("symbol")]
    return {
        "id": item.get("id") or content.get("id") or url or title,
        "title": title,
        "summary": (content.get("summary") or content.get("description") or "").strip() or None,
        "source": (content.get("provider") or {}).get("displayName") or content.get("publisher"),
        "published": _iso(content.get("pubDate") or content.get("providerPublishTime")),
        "url": url,
        "image": _image(content),
        "related": related,
    }


def _normalize_search_news(item: dict) -> dict | None:
    """Formato de ``Search(...).news``: plano, sin resumen."""
    if not item.get("title"):
        return None
    return {
        "id": item.get("uuid") or item.get("link") or item["title"],
        "title": item["title"],
        "summary": None,
        "source": item.get("publisher"),
        "published": _iso(item.get("providerPublishTime")),
        "url": item.get("link"),
        "image": _image(item),
        "related": list(item.get("relatedTickers") or []),
    }


def _fetch_live(ticker: str) -> list[dict]:
    import yfinance as yf

    rows: list[dict] = []
    try:
        rows = [n for n in (_normalize_ticker_news(ticker, i) for i in yf.Ticker(ticker).news or []) if n]
    except Exception:  # Yahoo cambia o cae a menudo: se intenta con Search
        rows = []
    if not rows:
        try:
            rows = [n for n in (_normalize_search_news(i) for i in yf.Search(ticker, news_count=PER_TICKER).news or []) if n]
        except Exception:
            rows = []
    return rows[:PER_TICKER]


def _cached(ticker: str) -> list[dict]:
    hit = _cache.get(ticker)
    if hit and time.time() - hit[0] < NEWS_CACHE_TTL:
        return hit[1]
    rows = _fetch_live(ticker)
    if rows:  # un fallo no se cachea: se reintenta en la siguiente petición
        _cache[ticker] = (time.time(), rows)
    return rows


def news_for(tickers: list[str]) -> tuple[list[dict], bool]:
    """Noticias de ``tickers`` (más recientes primero) y si son de demostración."""
    if not tickers:
        return [], False
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tickers))) as pool:
        per_ticker = dict(zip(tickers, pool.map(_cached, tickers)))

    merged: dict[str, dict] = {}
    for ticker, rows in per_ticker.items():
        for row in rows:
            key = row["id"]
            if key in merged:  # la misma noticia para varios activos: una sola tarjeta
                if ticker not in merged[key]["tickers"]:
                    merged[key]["tickers"].append(ticker)
                continue
            merged[key] = {
                "id": key,
                "ticker": ticker,
                "tickers": [ticker],
                "title": row["title"],
                "summary": row["summary"],
                "source": row["source"],
                "published": row["published"],
                "url": row["url"],
                "image": row.get("image"),
                "trend": trend_of(row["title"], row["summary"]),
                "demo": False,
            }

    if not merged:
        return demo_news(tickers), True
    items = sorted(merged.values(), key=lambda n: n["published"] or "", reverse=True)
    return items, False


# DEMO: noticias de ejemplo para cuando Yahoo Finance no responde. No son reales.
# (titular, resumen, tendencia)
DEMO_NEWS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "AAPL": (
        ("Apple amplía su apuesta por la IA en el dispositivo", "La compañía presentó nuevas funciones que procesan datos en el iPhone sin enviarlos a la nube, una estrategia que los analistas ven como diferenciadora.", "subir"),
    ),
    "MSFT": (
        ("Azure sigue impulsando los ingresos de Microsoft", "El negocio de nube crece a doble dígito y compensa la desaceleración en licencias tradicionales, según el último reporte trimestral.", "subir"),
    ),
    "^GSPC": (
        ("El S&P 500 cierra la semana atento a los datos de inflación", "Los inversionistas esperan la publicación del IPC para ajustar sus expectativas sobre la próxima decisión de tasas de la Reserva Federal.", "medio"),
    ),
    "^IXIC": (
        ("El Nasdaq oscila con la temporada de resultados tecnológicos", "Las grandes tecnológicas concentran la atención del índice mientras el mercado evalúa el ritmo de inversión en inteligencia artificial.", "medio"),
    ),
    "BTC-USD": (
        ("Bitcoin consolida tras una semana de alta volatilidad", "Los flujos hacia fondos cotizados de bitcoin se moderan y el precio se mantiene en un rango estrecho a la espera de catalizadores.", "medio"),
    ),
    "SONY": (
        ("Sony eleva su previsión anual por el negocio de videojuegos", "La división PlayStation supera las expectativas gracias a las ventas de software y suscripciones.", "subir"),
    ),
    "UEC": (
        ("El uranio repunta por la demanda de energía nuclear", "Productores como Uranium Energy Corp se benefician de nuevos contratos de suministro de largo plazo.", "subir"),
    ),
    "EURUSD=X": (
        ("El euro se mantiene estable frente al dólar", "El mercado de divisas aguarda las próximas comunicaciones del BCE y de la Fed para definir dirección.", "medio"),
    ),
}


def demo_news(tickers: list[str]) -> list[dict]:
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    for ticker in tickers:
        for title, summary, trend in DEMO_NEWS.get(ticker, ()):
            items.append(
                {
                    "id": f"demo-{ticker}-{len(items)}",
                    "ticker": ticker,
                    "tickers": [ticker],
                    "title": title,
                    "summary": summary,
                    "source": "MOAINVEST · ejemplo",
                    "published": (now - timedelta(hours=3 * len(items) + 1)).isoformat(),
                    "url": None,
                    "image": None,
                    "trend": trend,
                    "demo": True,
                }
            )
    return items
