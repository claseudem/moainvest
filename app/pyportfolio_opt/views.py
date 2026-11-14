"""Controlador de la app "Pyportfolio opt": retornos esperados con
PyPortfolioOpt (los datos llegan desde la API de la propia app)."""
from __future__ import annotations

from flask import Blueprint, render_template

from app.core.navigation import get_app
from app.pyportfolio_opt.api import ALLOWED_PERIODS, MAX_TICKERS, SPAN_MAX, SPAN_MIN
from app.pyportfolio_opt.expected import DEFAULT_SPAN, METHODS, TRADING_DAYS_PER_YEAR

bp = Blueprint(
    "pyportfolio_opt",
    __name__,
    url_prefix="/app/pyportfolio-opt",
    template_folder="templates",
    static_folder="static",
)

PERIOD_LABELS = {"1y": "1 año", "2y": "2 años", "5y": "5 años", "10y": "10 años", "max": "Todo"}
DEFAULT_PERIOD = "5y"

# Tickers con los que arranca el formulario y chips de sugerencia.
DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA", "SPY")
SUGGESTED_TICKERS = ("AAPL", "MSFT", "NVDA", "GOOG", "AMZN", "SPY", "QQQ", "BTC-USD")


@bp.get("/")
def index():
    return render_template(
        "pyportfolio_opt/index.html",
        active_app=get_app("pyportfolio-opt"),
        periods=[(p, PERIOD_LABELS[p]) for p in ALLOWED_PERIODS],
        default_period=DEFAULT_PERIOD,
        methods=METHODS,
        default_span=DEFAULT_SPAN,
        span_min=SPAN_MIN,
        span_max=SPAN_MAX,
        frequency=TRADING_DAYS_PER_YEAR,
        max_tickers=MAX_TICKERS,
        default_tickers=", ".join(DEFAULT_TICKERS),
        suggested_tickers=SUGGESTED_TICKERS,
    )
