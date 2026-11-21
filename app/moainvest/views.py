"""Controlador: sitio MOAINVEST (Resumen, Gráficas e Informe), en la raíz.

El navbar solo enlaza a «Inicio» (``/``) y «App» (``/app/``, que redirige a la
primera app del sidebar); Gráficas e Informe siguen accesibles desde el contenido.

Plantillas Jinja2 en ``moainvest/templates/moainvest/``. Las páginas se renderizan con el
registro de watchlists; los precios, velas e informes los pide el JavaScript
(``moainvest/static/moainvest.js``) a la API JSON (``/api/...``).
"""
from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, url_for

from app.core.navigation import APPS, default_app
from app.core.watchlists import WATCHLISTS, Symbol, Watchlist, get_watchlist
from app.personas.content import TEAMS

bp = Blueprint(
    "moainvest",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/moainvest",
)

# Navegación principal (cabecera, menú móvil y pie de página).
MAIN_NAV = (
    ("moainvest.resumen", "Inicio"),
    ("moainvest.app_home", "App"),
)

# Rangos del gráfico de velas: etiqueta del botón, range e interval de /api/candles.
CHART_RANGES = (
    {"label": "1D", "range": "5d", "interval": "15m"},
    {"label": "5D", "range": "5d", "interval": "1h"},
    {"label": "1M", "range": "1mo", "interval": "1d"},
    {"label": "6M", "range": "6mo", "interval": "1d"},
    {"label": "1A", "range": "1y", "interval": "1d"},
    {"label": "5A", "range": "5y", "interval": "1wk"},
    {"label": "Todo", "range": "max", "interval": "1mo"},
)
DEFAULT_RANGE = "1M"

# Cada cuánto refresca los precios moainvest.js (QUOTE_POLL_MS); se muestra en el inicio.
QUOTE_REFRESH_SECONDS = 15


@bp.app_context_processor
def inject_moainvest_nav() -> dict:
    return {"moainvest_nav": MAIN_NAV}


def chart_url(watchlist: Watchlist, ticker: str | None = None) -> str:
    return url_for("moainvest.grafica", slug=watchlist.slug, ticker=ticker or watchlist.symbols[0].ticker)


def tape_symbols() -> list[tuple[Watchlist, Symbol]]:
    """Todos los símbolos de todas las watchlists, sin repetir ticker (cinta del inicio)."""
    seen: set[str] = set()
    tape = []
    for watchlist in WATCHLISTS:
        for symbol in watchlist.symbols:
            if symbol.ticker not in seen:
                seen.add(symbol.ticker)
                tape.append((watchlist, symbol))
    return tape


@bp.get("/")
def resumen():
    overview = get_watchlist("overview") or WATCHLISTS[0]
    tape = tape_symbols()
    # Cifras de la barra de métricas: solo datos reales del registro de la app.
    metrics = {
        "assets": len(tape),
        "watchlists": len(WATCHLISTS),
        "tools": len(APPS),
        "refresh_seconds": QUOTE_REFRESH_SECONDS,
    }
    return render_template(
        "moainvest/resumen.html",
        watchlist=overview,
        watchlists=WATCHLISTS,
        tape=tape,
        metrics=metrics,
        chart_url=chart_url,
        teams=TEAMS,
    )


@bp.get("/app/", strict_slashes=False)
def app_home():
    """Entrada a la App: redirige a la primera app del sidebar (``default_app()``)."""
    return redirect(url_for(default_app().endpoint))


@bp.get("/graficas", strict_slashes=False)
def graficas():
    return redirect(chart_url(WATCHLISTS[0]))


@bp.get("/graficas/<slug>")
def graficas_watchlist(slug: str):
    watchlist = get_watchlist(slug)
    if watchlist is None:
        abort(404)
    return redirect(chart_url(watchlist))


@bp.get("/graficas/<slug>/<path:ticker>")
def grafica(slug: str, ticker: str):
    watchlist = get_watchlist(slug)
    symbol = next((s for s in watchlist.symbols if s.ticker == ticker), None) if watchlist else None
    if symbol is None:
        abort(404)
    return render_template(
        "moainvest/grafica.html",
        watchlists=WATCHLISTS,
        active=watchlist,
        symbol=symbol,
        ranges=CHART_RANGES,
        default_range=DEFAULT_RANGE,
        chart_url=chart_url,
    )


@bp.get("/informe")
def informe():
    return render_template("moainvest/informe.html", watchlists=WATCHLISTS)


@bp.app_errorhandler(404)
def not_found(_error):
    """Cualquier ruta inexistente muestra el 404 con la estética del sitio."""
    return render_template("moainvest/404.html"), 404
