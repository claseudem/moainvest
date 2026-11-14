"""Controlador de la app "¿Qué piensas tú?": votación semanal de la comunidad."""
from __future__ import annotations

from flask import Blueprint, render_template

from app.core import catalog
from app.core.navigation import get_app

bp = Blueprint(
    "comunidad",
    __name__,
    url_prefix="/app/que-piensas-tu",
    template_folder="templates",
    static_folder="static",
)


@bp.get("/")
def index():
    return render_template("comunidad/index.html", active_app=get_app("que-piensas-tu"), categories=catalog.CATEGORIES)
