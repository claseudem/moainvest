"""Controlador de la app "Graficador".

Sirve la página con el gráfico de un ticker (``?ticker=AAPL``); los datos los
pide el navegador a ``/api/candles/<ticker>`` de ``core``. Quant stats cuelga
del Graficador como subsecciones "Quant stats" y "Comparar" (ver
``app/core/navigation.py``) y recibe el mismo ``?ticker=``.
"""
from __future__ import annotations

import re

from flask import Blueprint, render_template, request

from app.core.navigation import get_app
from app.core.watchlists import default_watchlist

bp = Blueprint(
    "graficador",
    __name__,
    url_prefix="/app/graficador",
    template_folder="templates",
    static_folder="static",
)

# Botones de rango: el ``range`` y el ``interval`` deben estar en
# ``ALLOWED_RANGES``/``ALLOWED_INTERVALS`` de ``app/core/api.py``.
CHART_RANGES = (
    {"label": "1D", "range": "1d", "interval": "5m"},
    {"label": "5D", "range": "5d", "interval": "15m"},
    {"label": "1M", "range": "1mo", "interval": "1h"},
    {"label": "6M", "range": "6mo", "interval": "1d"},
    {"label": "1A", "range": "1y", "interval": "1d"},
    {"label": "5A", "range": "5y", "interval": "1wk"},
    {"label": "Todo", "range": "max", "interval": "1mo"},
)
DEFAULT_RANGE = "6M"

SERIES_TYPES = (
    {"value": "candles", "label": "Velas"},
    {"value": "line", "label": "Línea"},
    {"value": "area", "label": "Área"},
)

# Tickers de Yahoo: letras, números y ``^ = . -`` (``^GSPC``, ``BTC-USD``, ``EURUSD=X``).
TICKER_RE = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")


def default_ticker() -> str:
    """Primer símbolo de la watchlist por defecto."""
    return default_watchlist().symbols[0].ticker


@bp.get("/")
def index():
    ticker = (request.args.get("ticker") or "").strip().upper() or default_ticker()
    error = None if TICKER_RE.match(ticker) else f"«{ticker}» no es un ticker válido de Yahoo Finance."
    html = render_template(
        "graficador/index.html",
        active_app=get_app("graficador"),
        active_section="grafico",
        # Las pestañas y el sidebar llevan el activo a Quant stats y Comparar.
        section_args={"ticker": ticker} if not error else {},
        ticker="" if error else ticker,
        query=ticker,
        error=error,
        ranges=CHART_RANGES,
        default_range=DEFAULT_RANGE,
        series_types=SERIES_TYPES,
    )
    return html, 400 if error else 200
