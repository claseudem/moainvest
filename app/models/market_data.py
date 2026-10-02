"""Modelo de datos de mercado: descarga y cachea precios desde Yahoo Finance.

Toda la interacción con ``yfinance`` vive aquí. Los controladores nunca
llaman a ``yfinance`` directamente: piden datos a través de las funciones
de este módulo, así que cambiar de proveedor de datos en el futuro solo
requiere tocar este archivo.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

import yfinance as yf

from config import Config

# Caché en memoria: clave -> (timestamp de escritura, valor). Es intencionalmente
# simple (sin dependencias externas); para producción con varios workers
# convendría cambiarla por Redis u otra caché compartida.
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: int, loader: Callable[[], Any]) -> Any:
    now = time.time()
    hit = _cache.get(key)
    if hit is not None and (now - hit[0]) < ttl:
        return hit[1]
    value = loader()
    _cache[key] = (now, value)
    return value


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


@dataclass(slots=True)
class Quote:
    """Snapshot del precio actual de un símbolo."""

    symbol: str
    name: str
    price: float | None
    previous_close: float | None
    change: float | None
    change_percent: float | None
    currency: str | None = None

    @property
    def is_up(self) -> bool:
        return (self.change or 0) >= 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_up"] = self.is_up
        return data


def get_quote(ticker: str) -> Quote:
    """Devuelve el último precio disponible de ``ticker`` (cacheado unos segundos)."""

    def load() -> Quote:
        yf_ticker = yf.Ticker(ticker)
        try:
            fast_info = yf_ticker.fast_info
        except Exception:
            fast_info = {}

        # `fast_info` es un mapeo especial de yfinance; su `.get()` solo
        # resuelve de forma fiable las claves en camelCase.
        price = _clean_float(fast_info.get("lastPrice") if fast_info else None)
        prev_close = _clean_float(fast_info.get("previousClose") if fast_info else None)
        currency = fast_info.get("currency") if fast_info else None

        change = None
        change_percent = None
        if price is not None and prev_close:
            change = price - prev_close
            change_percent = (change / prev_close) * 100

        return Quote(
            symbol=ticker,
            name=_get_display_name(ticker),
            price=price,
            previous_close=prev_close,
            change=change,
            change_percent=change_percent,
            currency=currency,
        )

    return _cached(f"quote:{ticker}", Config.QUOTE_CACHE_TTL, load)


def get_display_name(ticker: str) -> str:
    """Nombre del símbolo según Yahoo Finance (el ticker si no se encuentra)."""
    return _get_display_name(ticker)


def _get_display_name(ticker: str) -> str:
    """Nombre "bonito" del símbolo. Se cachea mucho más tiempo que el precio
    porque casi nunca cambia, y consultarlo (``Ticker.info``) es más lento
    que ``fast_info``."""

    def load() -> str:
        try:
            info = yf.Ticker(ticker).info
            return info.get("shortName") or info.get("longName") or ticker
        except Exception:
            return ticker

    return _cached(f"name:{ticker}", 60 * 60 * 6, load)


def get_candles(ticker: str, range_: str = "6mo", interval: str = "1d") -> list[dict[str, Any]]:
    """Devuelve velas OHLC en el formato que espera lightweight-charts."""

    def load() -> list[dict[str, Any]]:
        history = yf.Ticker(ticker).history(period=range_, interval=interval)
        candles: list[dict[str, Any]] = []
        for index, row in history.iterrows():
            open_ = _clean_float(row.get("Open"))
            high = _clean_float(row.get("High"))
            low = _clean_float(row.get("Low"))
            close = _clean_float(row.get("Close"))
            if None in (open_, high, low, close):
                continue
            volume = _clean_float(row.get("Volume")) or 0
            candles.append(
                {
                    "time": int(index.timestamp()),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": int(volume),
                }
            )
        return candles

    return _cached(f"candles:{ticker}:{range_}:{interval}", Config.CANDLE_CACHE_TTL, load)


def get_earnings(ticker: str, limit: int = 12) -> list[dict[str, Any]]:
    """Reportes de resultados (earnings) de ``ticker``, del más reciente al más
    antiguo, con el EPS estimado por los analistas y el reportado. Incluye los
    reportes futuros ya anunciados (con ``eps_reported`` a ``None``).

    Se cachea una hora: estos datos solo cambian una vez por trimestre.
    """

    def load() -> list[dict[str, Any]]:
        try:
            table = yf.Ticker(ticker).get_earnings_dates(limit=limit)
        except Exception:
            return []
        if table is None:
            return []

        earnings: list[dict[str, Any]] = []
        for index, row in table.iterrows():
            earnings.append(
                {
                    "time": int(index.timestamp()),
                    "eps_estimate": _clean_float(row.get("EPS Estimate")),
                    "eps_reported": _clean_float(row.get("Reported EPS")),
                    "surprise_percent": _clean_float(row.get("Surprise(%)")),
                }
            )
        earnings.sort(key=lambda e: e["time"], reverse=True)
        return earnings

    return _cached(f"earnings:{ticker}:{limit}", 60 * 60, load)
