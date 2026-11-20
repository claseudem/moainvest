"""Controlador de COMUNIDAD (``/app/personas/``).

Vista unificada del sentimiento de mercado: noticias de los activos presentes en
la plataforma y votación "Sube" / "Baja" con ranking por votos. Los activos son
los de las watchlists más los de "Mis activos" del usuario (``assets()``).

La ruta conserva el prefijo ``/app/personas`` (y ``/personas/`` redirige aquí,
ver ``core/views.py``); ``/app/comunidad/`` es un alias.
"""
from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

from app.core.navigation import get_app
from app.core.watchlists import WATCHLISTS
from app.cuentas.views import current_user
from app.favoritos import store
from app.favoritos.store import StoreError
from app.personas import members

bp = Blueprint(
    "personas",
    __name__,
    url_prefix="/app/personas",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/personas",
)


@bp.record_once
def _comunidad_alias(state) -> None:
    state.app.add_url_rule(
        "/app/comunidad/",
        endpoint="comunidad_redirect",
        view_func=lambda: redirect(url_for("personas.index"), code=301),
    )


def assets(user: dict | None) -> list[dict]:
    """Activos presentes: los de "Mis activos" primero y luego los de las watchlists."""
    items: dict[str, dict] = {}
    if user is not None:
        try:
            for row in store.list_favorites(user["id"]):
                items[row["ticker"]] = {"ticker": row["ticker"], "name": row.get("nombre") or row["ticker"], "mine": True}
        except StoreError:
            pass
    for watchlist in WATCHLISTS:
        for symbol in watchlist.symbols:
            items.setdefault(symbol.ticker, {"ticker": symbol.ticker, "name": symbol.display_name, "mine": False})
    return list(items.values())


@bp.get("/")
def index():
    user = current_user()
    return render_template(
        "personas/index.html",
        active_app=get_app("personas"),
        payload={
            "assets": assets(user),
            "signedIn": user is not None,
            "userKey": user["id"] if user else "anon",
            "newsUrl": url_for("personas_api.noticias"),
            "votesUrl": url_for("personas_api.votos"),
            "notesUrl": url_for("personas_api.notas"),
            "quickTags": members.QUICK_TAGS,
        },
    )
