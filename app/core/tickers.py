"""Validación de tickers de Yahoo Finance que llegan por la URL (sin Flask).

Las páginas que aceptan deep links (``?ticker=AAPL`` o ``?tickers=AAPL,MSFT``)
usan estas funciones para descartar lo que no parezca un ticker antes de
pintarlo en un formulario.
"""
from __future__ import annotations

import re

# Letras, números y ``^ = . -`` (``^GSPC``, ``BTC-USD``, ``EURUSD=X``).
TICKER_RE = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")


def parse_tickers(text: str | None, limit: int) -> list[str]:
    """Tickers válidos y sin repetir de ``"aapl, msft btc-usd"``, como mucho ``limit``."""
    seen: list[str] = []
    for raw in re.split(r"[\s,;]+", (text or "").upper()):
        if raw and TICKER_RE.match(raw) and raw not in seen:
            seen.append(raw)
    return seen[:limit]
