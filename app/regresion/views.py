"""Página de entrenamiento y comparación de modelos de regresión."""
from __future__ import annotations

from flask import Blueprint, render_template

from app.core.navigation import get_app

bp = Blueprint(
    "regresion",
    __name__,
    url_prefix="/app/regresion",
    template_folder="templates",
    static_folder="static",
)


@bp.get("/")
def index():
    return render_template("regresion/index.html", active_app=get_app("regresion"))