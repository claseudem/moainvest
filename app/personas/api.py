"""API de COMUNIDAD: noticias de activos y votos de sentimiento.

- ``GET  /api/comunidad/noticias?tickers=AAPL,MSFT``  noticias normalizadas
- ``GET  /api/comunidad/votos``                       conteo y voto propio
- ``POST /api/comunidad/votos``  ``{"ticker", "voto": "sube"|"baja"|null}``
- ``GET  /api/comunidad/notas?ticker=AAPL&mias=1``    notas (tesis) por activo
- ``POST /api/comunidad/notas``  ``{"ticker", "tag", "text"}``  · ``DELETE /notas/<ticker>``
- ``GET|PUT /api/comunidad/perfil``                   perfil de comunidad propio
- ``GET  /api/comunidad/miembros``                    perfiles públicos
- ``POST /api/comunidad/relaciones`` ``{"target", "kind": "seguir"|"conectar", "active"}``

Si InsForge no está disponible (o una tabla aún no existe) se responde 503 con
``mode: "local"`` y la página guarda en ``localStorage`` y lo indica.
"""
from __future__ import annotations

import re

from functools import wraps

from flask import Blueprint, jsonify, request

from app.cuentas.views import current_user
from app.mi_perfil.content import PROFILES as INTEREST_PROFILES
from app.personas import members, news, votes
from app.personas.db import DBError
from app.personas.views import assets
from app.personas.votes import VoteStoreError

bp = Blueprint("personas_api", __name__, url_prefix="/api/comunidad")

TICKER_RE = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")
MAX_TICKERS = 40


@bp.get("/noticias")
def noticias():
    raw = request.args.get("tickers")
    if raw:
        tickers = [t for t in (p.strip().upper() for p in raw.split(",")) if TICKER_RE.match(t)]
    else:
        tickers = [a["ticker"] for a in assets(current_user())]
    items, demo = news.news_for(list(dict.fromkeys(tickers))[:MAX_TICKERS])
    return jsonify({"items": items, "demo": demo})


@bp.get("/votos")
def votos():
    user = current_user()
    try:
        data = votes.tally(user["id"] if user else None)
    except VoteStoreError as exc:
        return jsonify({"error": str(exc), "mode": "local"}), 503
    return jsonify({**data, "mode": "server", "canVote": user is not None})


@bp.post("/votos")
def votar():
    user = current_user()
    if user is None:
        return jsonify({"error": "Inicia sesión para votar.", "mode": "local"}), 401
    body = request.get_json(silent=True) or {}
    ticker = str(body.get("ticker") or "").strip().upper()
    vote = body.get("voto")
    if not TICKER_RE.match(ticker) or vote not in (*votes.VOTES, None):
        return jsonify({"error": "Voto inválido."}), 400
    try:
        votes.cast(user["id"], ticker, vote)
        data = votes.tally(user["id"], use_cache=False)
    except VoteStoreError as exc:
        return jsonify({"error": str(exc), "mode": "local"}), 503
    return jsonify({**data, "mode": "server", "canVote": True})


# ── Perfil, notas y relaciones ───────────────────────────────────


def community_api(view):
    """Exige sesión y traduce un fallo de InsForge en 503 ``mode: "local"``."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Inicia sesión para participar en la comunidad.", "mode": "local"}), 401
        try:
            return view(user, *args, **kwargs)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except DBError as exc:
            return jsonify({"error": str(exc), "mode": "local"}), 503

    return wrapper


def _ticker(value) -> str:
    ticker = str(value or "").strip().upper()
    if not TICKER_RE.match(ticker):
        raise ValueError("Activo inválido.")
    return ticker


@bp.get("/notas")
@community_api
def notas(user):
    ticker = request.args.get("ticker")
    items = members.notes(
        user["id"],
        ticker=_ticker(ticker) if ticker else None,
        author_id=user["id"] if request.args.get("mias") else None,
    )
    return jsonify({"items": items, "tags": members.QUICK_TAGS, "mode": "server"})


@bp.post("/notas")
@community_api
def guardar_nota(user):
    body = request.get_json(silent=True) or {}
    ticker = _ticker(body.get("ticker"))
    members.save_note(user["id"], ticker, body.get("tag"), body.get("text"))
    return jsonify({"items": members.notes(user["id"], ticker=ticker), "mode": "server"})


@bp.delete("/notas/<ticker>")
@community_api
def borrar_nota(user, ticker):
    ticker = _ticker(ticker)
    members.delete_note(user["id"], ticker)
    return jsonify({"items": members.notes(user["id"], ticker=ticker), "mode": "server"})


def _profile_payload(user) -> dict:
    profile = members.get_profile(user["id"])
    mine = votes.tally(user["id"])["mine"]
    return {
        "profile": profile,
        "defaults": {"nombre": user.get("name")},
        "social": members.social_counts(user["id"]),
        "activity": {"votes": len(mine), "notes": len(members.notes(user["id"], author_id=user["id"]))},
        "mode": "server",
    }


@bp.get("/perfil")
@community_api
def perfil(user):
    return jsonify(_profile_payload(user))


@bp.put("/perfil")
@community_api
def guardar_perfil(user):
    body = request.get_json(silent=True) or {}
    if body.get("avatar") and members.valid_avatar(body["avatar"]) is None:
        raise ValueError("La foto no es válida o es demasiado grande.")
    members.save_profile(user["id"], body, valid_slugs={p.slug for p in INTEREST_PROFILES})
    return jsonify(_profile_payload(user))


@bp.get("/miembros")
@community_api
def miembros(user):
    return jsonify({"items": members.members(user["id"]), "mode": "server"})


@bp.post("/relaciones")
@community_api
def relaciones(user):
    body = request.get_json(silent=True) or {}
    members.set_relation(user["id"], str(body.get("target") or ""), body.get("kind"), bool(body.get("active")))
    return jsonify({"items": members.members(user["id"]), "mode": "server"})
