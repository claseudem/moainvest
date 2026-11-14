"""Controlador de MI PERFIL (``/app/mi-perfil/``): espacio personal de cada usuario.

El nombre viene de la cuenta iniciada (``cuentas``). Sin autenticación no se
muestra ningún nombre inventado. El progreso se guarda en el navegador, por
usuario y por perfil, desde ``static/mi_perfil.js``: no hay persistencia en
servidor todavía, y la página lo dice.
"""
from __future__ import annotations

from flask import Blueprint, render_template

from app.core.navigation import get_app
from app.cuentas.views import current_user
from app.mi_perfil.content import PROFILES, XP_PER_LEVEL, profiles_payload

bp = Blueprint(
    "mi_perfil",
    __name__,
    url_prefix="/app/mi-perfil",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/mi_perfil",
)


@bp.get("/")
def index():
    user = current_user()
    name = (user or {}).get("name") or None
    return render_template(
        "mi_perfil/index.html",
        active_app=get_app("mi-perfil"),
        profiles=PROFILES,
        user_name=name,
        user_initial=(name or "?")[:1].upper(),
        payload={
            "profiles": profiles_payload(),
            "xpPerLevel": XP_PER_LEVEL,
            # Clave de almacenamiento por usuario: el progreso de una cuenta no se mezcla con otra.
            "userKey": (user or {}).get("id") or "anonimo",
        },
    )
