"""Controlador de MI PERFIL (``/app/mi-perfil/``): espacio personal de cada usuario.

El nombre viene de la cuenta iniciada (``cuentas``). Sin autenticación no se
muestra ningún nombre inventado. El progreso de misiones se guarda en el
navegador, por usuario y por perfil, desde ``static/mi_perfil.js``.

El perfil de comunidad (foto, profesión, bio, visibilidad) y el bloque de
Interacción (comparar posturas, seguir / conectar, notas) usan la API de
COMUNIDAD (``app/personas/api.py``) desde ``static/comunidad.js``; si la base de
datos no está disponible, se guardan en el navegador y la página lo avisa.
"""
from __future__ import annotations

from flask import Blueprint, render_template, url_for

from app.core.navigation import get_app
from app.cuentas.views import current_user
from app.mi_perfil.content import PROFILES, XP_PER_LEVEL, profiles_payload
from app.personas import members
from app.personas.views import assets

bp = Blueprint(
    "mi_perfil",
    __name__,
    url_prefix="/app/mi-perfil",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/mi_perfil",
)


# Sugerencias del campo Profesión (se puede escribir cualquier otra).
PROFESSIONS = (
    "Estudiante",
    "Ingeniería",
    "Finanzas",
    "Economía",
    "Administración de empresas",
    "Negocios internacionales",
    "Mercadeo",
    "Diseño",
    "Análisis de datos",
    "Contaduría",
    "Emprendimiento",
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
        community={
            "userKey": (user or {}).get("id") or "anon",
            "signedIn": user is not None,
            "defaultName": name,
            "profiles": [{"slug": p.slug, "name": p.name} for p in PROFILES],
            "assets": [{"ticker": a["ticker"], "name": a["name"]} for a in assets(user)],
            "quickTags": members.QUICK_TAGS,
            "avatarColors": members.AVATAR_COLORS,
            "limits": {"name": members.MAX_NAME, "profession": members.MAX_PROFESSION, "bio": members.MAX_BIO, "note": members.MAX_NOTE},
            "urls": {
                "profile": url_for("personas_api.perfil"),
                "members": url_for("personas_api.miembros"),
                "relations": url_for("personas_api.relaciones"),
                "notes": url_for("personas_api.notas"),
                "votes": url_for("personas_api.votos"),
                "community": url_for("personas.index"),
            },
        },
        professions=PROFESSIONS,
    )
