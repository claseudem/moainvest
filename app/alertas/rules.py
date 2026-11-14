"""Reglas de las alertas de movimientos: cuándo una variación merece avisar.

Lógica pura (sin red, sin base de datos ni Flask) para poder probarla a fondo.
El servicio (``service.py``) le pasa las cotizaciones y lo ya notificado, y
guarda lo que esta función devuelve.

Anti-ruido:

* Solo avisa si ``|% del día| >= umbral`` del usuario (±3, ±5 o ±10 %).
* Un aviso por activo, sesión y dirección. Solo se repite si el movimiento
  **se intensifica** al siguiente múltiplo del umbral (nivel 2 = 2× umbral,
  nivel 3 = 3× umbral; no hay más niveles).
* La sesión se identifica por el **cierre anterior** del activo: cambia cuando
  empieza una sesión nueva y no cambia en fin de semana. Así un mismo
  movimiento no se notifica otra vez el sábado.
* Un activo que está en varias watchlists solo se silencia si **todas** sus
  watchlists están silenciadas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.core.market_data import Quote
from app.core.watchlists import Watchlist

THRESHOLDS = (3, 5, 10)
DEFAULT_THRESHOLD = 5
MAX_LEVEL = 3

Direction = Literal["up", "down"]


@dataclass(frozen=True, slots=True)
class Settings:
    """Preferencias de alertas de un usuario."""

    threshold: int = DEFAULT_THRESHOLD
    muted_watchlists: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class Trigger:
    """Un movimiento que cruzó el umbral y todavía no se había notificado."""

    ticker: str
    name: str
    watchlists: tuple[str, ...]
    change_percent: float
    price: float | None
    currency: str | None
    direction: Direction
    level: int
    threshold: int
    session: str

    @property
    def key(self) -> tuple[str, str, str, int]:
        return (self.ticker, self.session, self.direction, self.level)


def session_key(quote: Quote) -> str | None:
    """Identificador de la sesión de mercado de ``quote`` (su cierre anterior)."""
    if quote.previous_close is None:
        return None
    return f"{quote.previous_close:.10g}"


def level_for(change_percent: float, threshold: int) -> int:
    """0 si no llega al umbral; 1, 2 o 3 según los múltiplos del umbral alcanzados."""
    return min(int(abs(change_percent) // threshold), MAX_LEVEL)


def tickers_by_watchlist(watchlists: Iterable[Watchlist]) -> dict[str, tuple[str, ...]]:
    """``ticker -> (slugs de las watchlists que lo contienen)``, sin repetir tickers."""
    membership: dict[str, list[str]] = {}
    for watchlist in watchlists:
        for symbol in watchlist.symbols:
            membership.setdefault(symbol.ticker, []).append(watchlist.slug)
    return {ticker: tuple(slugs) for ticker, slugs in membership.items()}


def watched_tickers(watchlists: Iterable[Watchlist], settings: Settings) -> dict[str, tuple[str, ...]]:
    """Tickers que se vigilan: los que tienen al menos una watchlist sin silenciar."""
    return {
        ticker: slugs
        for ticker, slugs in tickers_by_watchlist(watchlists).items()
        if any(slug not in settings.muted_watchlists for slug in slugs)
    }


def evaluate(
    watchlists: Iterable[Watchlist],
    settings: Settings,
    quotes: dict[str, Quote],
    already_sent: set[tuple[str, str, str, int]],
    names: dict[str, str] | None = None,
) -> list[Trigger]:
    """Movimientos nuevos que hay que notificar, del más brusco al más suave.

    ``already_sent`` contiene las claves ``(ticker, sesión, dirección, nivel)``
    ya notificadas. Si un activo pasa del nivel 1 al 3 de golpe, se emite un
    solo aviso, el de nivel 3.
    """
    names = names or {}
    triggers: list[Trigger] = []
    for ticker, slugs in watched_tickers(watchlists, settings).items():
        quote = quotes.get(ticker)
        if quote is None or quote.change_percent is None:
            continue
        session = session_key(quote)
        level = level_for(quote.change_percent, settings.threshold)
        if session is None or level == 0:
            continue
        direction: Direction = "up" if quote.change_percent >= 0 else "down"
        sent_levels = [k[3] for k in already_sent if k[:3] == (ticker, session, direction)]
        if sent_levels and max(sent_levels) >= level:
            continue
        triggers.append(
            Trigger(
                ticker=ticker,
                name=names.get(ticker) or quote.name or ticker,
                watchlists=tuple(s for s in slugs if s not in settings.muted_watchlists),
                change_percent=quote.change_percent,
                price=quote.price,
                currency=quote.currency,
                direction=direction,
                level=level,
                threshold=settings.threshold,
                session=session,
            )
        )
    triggers.sort(key=lambda t: abs(t.change_percent), reverse=True)
    return triggers
