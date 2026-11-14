"""Controlador de PERSONAS, la comunidad (``/app/personas/``).

Es el directorio de quienes forman parte de MOAINVEST. No muestra el progreso
personal de nadie: eso vive en "Mi perfil". Los integrantes llegan de
``community.members()`` (solo perfiles públicos), y los indicadores son
demostrativos mientras no exista una base de datos de usuarios.

``/personas/`` redirige aquí (ver ``core/views.py``).
"""
from __future__ import annotations

from flask import Blueprint, render_template, url_for

from app.core.navigation import get_app
from app.mi_perfil.content import PROFILES
from app.personas import community
from app.personas.content import PILLARS

bp = Blueprint(
    "personas",
    __name__,
    url_prefix="/app/personas",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/personas",
)

# Niveles del filtro: cada nivel de una ruta de cinco.
LEVELS = tuple(range(1, 6))


@bp.get("/")
def index():
    count, count_source = community.member_count()
    target = community.next_target(count)
    by_profile = [
        {"slug": profile.slug, "name": profile.name, "count": community.DEMO_BY_PROFILE.get(profile.slug, 0)}
        for profile in PROFILES
    ]
    top = max((item["count"] for item in by_profile), default=0) or 1

    return render_template(
        "personas/index.html",
        active_app=get_app("personas"),
        profiles=PROFILES,
        levels=LEVELS,
        payload={
            "members": community.members(),
            "profiles": [{"slug": profile.slug, "name": profile.name} for profile in PROFILES],
        },
        by_profile=[{**item, "percent": round(item["count"] * 100 / top)} for item in by_profile],
        new_this_week=community.DEMO_NEW_THIS_WEEK,
        growth_percent=community.DEMO_GROWTH_PERCENT,
        pillars=PILLARS,
        member_count=count,
        count_source=count_source,
        next_target=target,
        next_percent=min(100, round(count * 100 / target)) if target else 100,
        milestones=community.milestone_states(count),
        invite_url=url_for("cuentas.registro", _external=True),
    )
