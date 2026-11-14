"""Controlador de la app "Pronosticador": la página del dashboard (los datos
llegan por la API de ``api.py``)."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from app.core.navigation import get_app
from app.pronosticador.econometrics import ALLOWED_LAGS, DEFAULT_LAGS

bp = Blueprint(
    "pronosticador",
    __name__,
    url_prefix="/app/pronosticador",
    template_folder="templates",
    static_folder="static",
)


@bp.get("/")
def index():
    return render_template(
        "pronosticador/index.html",
        active_app=get_app("pronosticador"),
        allowed_lags=ALLOWED_LAGS,
        default_lags=DEFAULT_LAGS,
        mlflow_ui_url=current_app.config.get("MLFLOW_UI_URL", ""),
    )
