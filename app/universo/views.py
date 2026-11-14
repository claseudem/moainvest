"""Controlador de la app "Mi universo de acciones": tabla con las acciones del
universo (``universe.UNIVERSE``), filtros por sector y búsqueda, y enlaces
rápidos al graficador y a quant stats. Los precios en vivo los pide el JS a
``/api/quote/<ticker>`` de ``core``.
"""
from __future__ import annotations

from flask import Blueprint, render_template

from app.core.navigation import get_app
from app.universo.universe import UNIVERSE, format_market_cap, sectors

bp = Blueprint(
    "universo",
    __name__,
    url_prefix="/app/universo",
    template_folder="templates",
    static_folder="static",
)


@bp.get("/")
def index():
    return render_template(
        "universo/index.html",
        active_app=get_app("universo"),
        stocks=UNIVERSE,
        sectors=sectors(),
        format_market_cap=format_market_cap,
    )
