"""API de las alertas (campana de la barra superior y paso 01 de Informes).

    GET  /api/alertas                 alertas recientes + no leídas + preferencias (evalúa si toca)
    POST /api/alertas/leidas          {"ids": [...]} o {} para marcar todas como leídas
    GET  /api/alertas/preferencias    umbral y watchlists silenciadas
    PUT  /api/alertas/preferencias    {"umbral": 3|5|10, "silenciadas": ["overview", ...]}
    GET  /api/alertas/noticias        titulares para la campana (si hay suscripción con vía «campana»)

Todas exigen sesión (401 si no la hay): son datos de cada usuario.
"""
from __future__ import annotations

import re
from functools import wraps

from flask import Blueprint, jsonify, request

from app.alertas import rules, service, store
from app.core.db import DBError
from app.alertas.rules import Settings
from app.alertas.store import StoreError
from app.core.watchlists import WATCHLISTS
from app.cuentas.views import current_user
from app.noticias import feed as news_feed
from app.noticias import subscriptions
from app.noticias.api import favorites_of

bp = Blueprint("alertas_api", __name__, url_prefix="/api/alertas")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
WATCHLIST_SLUGS = {w.slug for w in WATCHLISTS}


def _requires_user(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Inicia sesión para ver tus alertas."}), 401
        try:
            return view(user["id"], *args, **kwargs)
        except StoreError as exc:
            return jsonify({"error": str(exc)}), 503

    return wrapper


def _settings_json(settings: Settings, saved: bool) -> dict:
    return {
        "umbral": settings.threshold,
        "umbrales": list(rules.THRESHOLDS),
        "silenciadas": sorted(settings.muted_watchlists),
        "guardadas": saved,
        "watchlists": [{"slug": w.slug, "nombre": w.name} for w in WATCHLISTS],
    }


@bp.get("")
@_requires_user
def list_alerts(user_id: str):
    settings, saved = store.get_settings(user_id)
    scan_error = None
    try:
        service.scan_user(user_id, settings)
    except StoreError as exc:
        scan_error = str(exc)
    items = store.list_alerts(user_id)
    return jsonify(
        {
            "items": items,
            "no_leidas": sum(1 for item in items if not item.get("leida")),
            "preferencias": _settings_json(settings, saved),
            "error_evaluacion": scan_error,
        }
    )


@bp.post("/leidas")
@_requires_user
def mark_read(user_id: str):
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if ids is not None:
        if not isinstance(ids, list) or not all(isinstance(i, str) and UUID_RE.match(i) for i in ids):
            return jsonify({"error": "ids debe ser una lista de identificadores de alerta."}), 400
    store.mark_read(user_id, ids)
    return jsonify({"ok": True})


@bp.get("/preferencias")
@_requires_user
def get_preferences(user_id: str):
    settings, saved = store.get_settings(user_id)
    return jsonify(_settings_json(settings, saved))


@bp.put("/preferencias")
@_requires_user
def put_preferences(user_id: str):
    data = request.get_json(silent=True) or {}
    current, _ = store.get_settings(user_id)
    threshold = data.get("umbral", current.threshold)
    muted = data.get("silenciadas", sorted(current.muted_watchlists))
    if threshold not in rules.THRESHOLDS:
        return jsonify({"error": "El umbral debe ser 3, 5 o 10 (%)."}), 400
    if not isinstance(muted, list) or not set(muted) <= WATCHLIST_SLUGS:
        return jsonify({"error": "Alguna watchlist de 'silenciadas' no existe."}), 400
    settings = Settings(threshold=threshold, muted_watchlists=frozenset(muted))
    store.save_settings(user_id, settings)
    service.forget_scan(user_id)  # el próximo GET ya evalúa con el umbral nuevo
    return jsonify(_settings_json(settings, True))


@bp.get("/noticias")
@_requires_user
def headlines(user_id: str):
    """Titulares para la pestaña "Noticias" de la campana.

    Solo si el usuario activó las alertas de noticias con la vía "campana"
    (``/app/noticias/``); el alcance decide los activos: sus favoritos o todos.
    """
    try:
        sub, _ = subscriptions.get(user_id)
    except DBError as exc:
        if not exc.missing_table:
            return jsonify({"error": str(exc)}), 503
        return jsonify({"suscrito": False, "pendiente": True, "items": []})
    if not (sub.activa and sub.via_app):
        return jsonify({"suscrito": False, "items": []})
    favorites = favorites_of(user_id)
    tickers = news_feed.tickers_for_scope(sub.alcance, [f["ticker"] for f in favorites])
    names = {f["ticker"]: f["nombre"] for f in favorites if f.get("nombre")}
    quotes = service.fetch_quotes(tickers)
    items = []
    for item in news_feed.build(tickers, names, limit=25):
        for asset in item["activos"]:
            quote = quotes.get(asset["ticker"])
            asset["variacion"] = quote.change_percent if quote else None
        items.append(item)
    return jsonify({"suscrito": True, "alcance": sub.alcance, "items": items})
