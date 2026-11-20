"""API del sitio MOAINVEST.

    GET /api/radar?watchlist=overview   Radar de noticias del Inicio (ver ``radar.py``)
    GET /api/mercados/<slug>/quotes     Precios de una categoría de /mercados
    GET /api/mercados/curva             Curva de rendimiento del Tesoro de EE. UU. y su forma

Son públicas, como los precios del Resumen: el sitio rojo se ve sin iniciar sesión.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request

from app.core import market_data
from app.core.watchlists import get_watchlist
from app.moainvest import markets, radar

bp = Blueprint("moainvest_api", __name__, url_prefix="/api")


@bp.get("/radar")
def radar_view():
    watchlist = get_watchlist(request.args.get("watchlist", "overview"))
    if watchlist is None:
        return jsonify({"error": "watchlist no encontrada"}), 404
    response = jsonify(radar.build(watchlist, market_data.get_quote))
    # Los titulares se cachean 30 min en el servidor; el navegador, 2 min.
    response.headers["Cache-Control"] = "public, max-age=120"
    return response


def _quotes(tickers: list[str]) -> dict[str, dict]:
    """Precios de ``tickers`` en paralelo; uno que falle no tumba al resto."""

    def load(ticker: str) -> dict | None:
        try:
            return market_data.get_quote(ticker).to_dict()
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = dict(zip(tickers, pool.map(load, tickers)))
    return {t: q for t, q in loaded.items() if q is not None}


@bp.get("/mercados/<slug>/quotes")
def market_quotes(slug: str):
    market = markets.get_market(slug)
    if market is None:
        return jsonify({"error": "mercado no encontrado"}), 404
    return jsonify(_quotes(market.tickers))


@bp.get("/mercados/curva")
def yield_curve():
    market = next(m for m in markets.MARKETS if m.kind == "yield")
    quotes = _quotes(market.tickers)
    points = [
        {"ticker": s.ticker, "nombre": s.display_name, "anios": s.years, "rendimiento": (quotes.get(s.ticker) or {}).get("price")}
        for s in market.symbols
    ]
    shape = markets.curve_shape({p["anios"]: p["rendimiento"] for p in points})
    return jsonify({"puntos": points, **shape})
