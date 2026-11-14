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


# Rutas de antes del área "App": las páginas de las subapps cuelgan ahora de
# /app/. Se redirigen con 301 (conservando subruta y query string) para no
# romper enlaces ni marcadores.
LEGACY_APP_PREFIXES = ("analisis-varianza", "quant-stats", "informes", "personas")


def _legacy_app_redirect(prefix: str, rest: str = ""):
    target = f"/app/{prefix}/{rest}"
    if request.query_string:
        target += "?" + request.query_string.decode()
    return redirect(target, code=301)


for _prefix in LEGACY_APP_PREFIXES:
    bp.add_url_rule(
        f"/{_prefix}/",
        endpoint=f"legacy_{_prefix}",
        view_func=_legacy_app_redirect,
        defaults={"prefix": _prefix},
    )
    bp.add_url_rule(
        f"/{_prefix}/<path:rest>",
        endpoint=f"legacy_{_prefix}_rest",
        view_func=_legacy_app_redirect,
        defaults={"prefix": _prefix},
    )
