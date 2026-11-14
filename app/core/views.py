"""Blueprint de "core": no tiene páginas propias.

Aporta a las demás apps el layout con sidebar (``core/base.html``), el sidebar,
los iconos (``core/icons.html``), los estáticos comunes (``core.static``) y las
variables globales de las plantillas.
"""
from __future__ import annotations

from flask import Blueprint, current_app, redirect, request

from app.core.navigation import APPS

bp = Blueprint(
    "core",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/core",
)


@bp.app_context_processor
def inject_globals() -> dict:
    return {
        # Entradas del sidebar (core/sidebar.html).
        "apps": APPS,
        # Nombre de la marca para títulos y sidebar (ver Config.SITE_NAME).
        "site_name": current_app.config["SITE_NAME"],
    }


# Rutas antiguas -> su ubicación actual. Se redirigen con 301 (conservando
# subruta y query string) para no romper enlaces ni marcadores:
# - las subapps colgaban de la raíz antes de existir el área /app/;
# - Quant stats vivía en /app/quant-stats/ antes de integrarse en el Graficador.
# La app Informes se eliminó y sus rutas (/informes, /app/informes) dan 404.
LEGACY_REDIRECTS = {
    "/analisis-varianza": "/app/analisis-varianza",
    "/quant-stats": "/app/graficador/quant-stats",
    "/app/quant-stats": "/app/graficador/quant-stats",
    "/pronosticador": "/app/pronosticador",
    "/personas": "/app/personas",
}


def _legacy_redirect(target_prefix: str, rest: str = ""):
    target = f"{target_prefix}/{rest}"
    if request.query_string:
        target += "?" + request.query_string.decode()
    return redirect(target, code=301)


for _old, _new in LEGACY_REDIRECTS.items():
    _name = _old.strip("/").replace("/", "_")
    bp.add_url_rule(
        f"{_old}/",
        endpoint=f"legacy_{_name}",
        view_func=_legacy_redirect,
        defaults={"target_prefix": _new},
    )
    bp.add_url_rule(
        f"{_old}/<path:rest>",
        endpoint=f"legacy_{_name}_rest",
        view_func=_legacy_redirect,
        defaults={"target_prefix": _new},
    )
