"""Controlador de la app "Noticias": feed del mercado y suscripción a alertas."""
from __future__ import annotations

from flask import Blueprint, render_template

from app.core.navigation import get_app
from app.noticias import feed

bp = Blueprint(
    "noticias",
    __name__,
    url_prefix="/app/noticias",
    template_folder="templates",
    static_folder="static",
)


@bp.get("/")
def index():
    return render_template("noticias/index.html", active_app=get_app("noticias"), filters=feed.FILTERS)
