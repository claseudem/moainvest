"""API del sitio MOAINVEST.

    GET /api/radar?watchlist=overview   Radar de noticias del Inicio (ver ``radar.py``)

Es pública, como los precios del Resumen: el Inicio se ve sin iniciar sesión.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core import market_data
from app.core.watchlists import get_watchlist
from app.moainvest import radar

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
