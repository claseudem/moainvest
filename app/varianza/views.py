"""Controlador de la app "Análisis de Varianza": histórico de precios de un
ticker y histogramas de volatilidad mensual (los datos llegan desde la API)."""
from __future__ import annotations

from flask import Blueprint, render_template, request

from app.core.navigation import get_app
from app.core.tickers import parse_tickers
from app.varianza.api import MAX_VOLATILITY_TICKERS

bp = Blueprint(
    "varianza",
    __name__,
    url_prefix="/app/analisis-varianza",
    template_folder="templates",
    static_folder="static",
)

# Chips de sugerencia del formulario de volatilidad.
SUGGESTED_TICKERS = ("AAPL", "MSFT", "NVDA", "GOOG", "AMZN", "SPY")


@bp.get("/")
def index():
    """Deep links desde las acciones del activo (core/_asset_actions.html):

    - ``?ticker=AAPL``: rellena el histórico de precios y el histograma con ese activo;
    - ``?tickers=AAPL,MSFT``: rellena el histograma con varios (p. ej. desde Mis activos).

    Con alguno de los dos, ``varianza.js`` lanza el análisis al cargar.
    """
    ticker = next(iter(parse_tickers(request.args.get("ticker"), 1)), "")
    initial = parse_tickers(request.args.get("tickers"), MAX_VOLATILITY_TICKERS) or ([ticker] if ticker else [])
    return render_template(
        "varianza/index.html",
        active_app=get_app("analisis-varianza"),
        max_tickers=MAX_VOLATILITY_TICKERS,
        suggested_tickers=SUGGESTED_TICKERS,
        initial_ticker=ticker,
        initial_tickers=initial,
    )
