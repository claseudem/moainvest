"""API de "Mis activos": autocompletado del campo "Agregar un activo".

    GET /api/favoritos/buscar?q=appl   símbolos por ticker o nombre (sin q: populares)

Exige sesión (401 si no la hay). La usan también los buscadores de
"¿Qué piensas tú?". Las noticias y los votos viven en sus propias apps
(``app/noticias`` y ``app/comunidad``).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.cuentas.views import current_user
from app.favoritos import search, store
from app.favoritos.store import StoreError

bp = Blueprint("favoritos_api", __name__, url_prefix="/api/favoritos")

MAX_QUERY = 40


@bp.get("/buscar")
def buscar():
    user = current_user()
    if user is None:
        return jsonify({"error": "Inicia sesión para buscar activos."}), 401
    query = (request.args.get("q") or "").strip()[:MAX_QUERY]
    try:
        mine = {f["ticker"] for f in store.list_favorites(user["id"])}
    except StoreError:
        mine = set()
    items = [{**m.to_dict(), "en_lista": m.ticker in mine} for m in search.search(query)]
    return jsonify({"q": query, "populares": not query, "items": items})
