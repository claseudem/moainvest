"""Controlador de la sección PERSONAS, publicada en ``/personas``.

Página pública del sitio MOAINVEST. El nivel seleccionado viaja en la query
(``?nivel=3``), así que funciona sin JavaScript y cada nivel tiene su enlace.
El contenido vive en ``content.py`` y el contador de comunidad en
``community.py``.
"""
from __future__ import annotations

from flask import Blueprint, render_template, request, url_for

from app.personas import community
from app.personas.content import (
    DEMO_PROGRESS,
    LEVELS,
    LEVELS_BY_NUMBER,
    PILLARS,
    TEAM,
    XP_PER_LEVEL,
    level_requirement,
    level_state,
)

bp = Blueprint(
    "personas",
    __name__,
    url_prefix="/personas",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/personas",
)


@bp.get("/")
def index():
    progress = DEMO_PROGRESS
    # Por defecto se muestra el nivel actual; ``?nivel=`` permite recorrer el resto.
    selected = request.args.get("nivel", type=int)
    if selected not in LEVELS_BY_NUMBER:
        selected = progress.current or LEVELS[-1].number

    count, count_source = community.member_count()
    target = community.next_target(count)

    return render_template(
        "personas/index.html",
        team=TEAM,
        pillars=PILLARS,
        levels=[
            {"level": level, "state": level_state(level.number, progress)} for level in LEVELS
        ],
        selected=LEVELS_BY_NUMBER[selected],
        selected_state=level_state(selected, progress),
        selected_requirement=level_requirement(selected),
        progress=progress,
        xp_per_level=XP_PER_LEVEL,
        partial_percent=round(progress.partial_xp * 100 / XP_PER_LEVEL),
        member_count=count,
        count_source=count_source,
        next_target=target,
        next_percent=min(100, round(count * 100 / target)) if target else 100,
        milestones=community.milestone_states(count),
        invite_url=url_for("cuentas.registro", _external=True),
    )
