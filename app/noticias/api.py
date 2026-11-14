"""API de "Noticias".

    GET /api/noticias?filtro=todos|mis-activos|indices|tecnologia|cripto|...
    GET /api/noticias/imagen?u=<portada de Yahoo>&w=360|720   miniatura WebP de la portada
    GET /api/noticias/suscripcion
    PUT /api/noticias/suscripcion   {"activa", "via_app", "via_email", "email", "alcance"}

Todas exigen sesión (401 si no la hay).
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, Response, jsonify, request

from app.core import db
from app.cuentas.views import current_user
from app.favoritos import store as favorites_store
from app.noticias import feed, images, subscriptions
from app.noticias.subscriptions import InvalidSubscription

bp = Blueprint("noticias_api", __name__, url_prefix="/api/noticias")


def _requires_user(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Inicia sesión para ver las noticias."}), 401
        try:
            return view(user, *args, **kwargs)
        except db.DBError as exc:
            return jsonify({"error": str(exc)}), 503

    return wrapper


def favorites_of(user_id: str) -> list[dict]:
    """Favoritos del usuario; si InsForge falla, lista vacía (el feed sigue funcionando)."""
    try:
        return favorites_store.list_favorites(user_id)
    except favorites_store.StoreError:
        return []


@bp.get("")
@_requires_user
def noticias(user: dict):
    filtro = request.args.get("filtro", "todos")
    if filtro not in feed.FILTER_SLUGS:
        return jsonify({"error": f"Filtro desconocido: {filtro}"}), 400
    favorites = favorites_of(user["id"])
    mine = [f["ticker"] for f in favorites]
    tickers = feed.tickers_for(filtro, mine)
    names = {f["ticker"]: f["nombre"] for f in favorites if f.get("nombre")}
    return jsonify(
        {
            "filtro": filtro,
            "tickers": tickers,
            "mis_activos": mine,
            "items": feed.build(tickers, names) if tickers else [],
        }
    )


@bp.get("/suscripcion")
@_requires_user
def get_subscription(user: dict):
    try:
        sub, exists = subscriptions.get(user["id"], user.get("email"))
    except db.DBError as exc:
        if not exc.missing_table:
            raise
        # Sin tabla: valores por defecto y el navegador guarda los cambios.
        sub, exists = subscriptions.Subscription(email=user.get("email")), False
        return jsonify({**sub.to_dict(), "guardada": False, "email_cuenta": user.get("email"), "almacenamiento": "local"})
    return jsonify({**sub.to_dict(), "guardada": exists, "email_cuenta": user.get("email"), "almacenamiento": "servidor"})


@bp.put("/suscripcion")
@_requires_user
def put_subscription(user: dict):
    missing = False
    try:
        current, exists = subscriptions.get(user["id"], user.get("email"))
    except db.DBError as exc:
        if not exc.missing_table:
            raise
        missing, exists = True, False
        current = subscriptions.Subscription(email=user.get("email"))
    # Se valida siempre, también sin tabla: el navegador solo guarda datos coherentes.
    try:
        sub = subscriptions.validate(request.get_json(silent=True) or {}, current)
    except InvalidSubscription as exc:
        return jsonify({"error": str(exc)}), 400
    if missing:
        body, status = db.pending_table(subscriptions.TABLE, suscripcion=sub.to_dict())
        return jsonify(body), status
    try:
        subscriptions.save(user["id"], sub, exists)
    except db.DBError as exc:
        if not exc.missing_table:
            raise
        body, status = db.pending_table(subscriptions.TABLE, suscripcion=sub.to_dict())
        return jsonify(body), status
    return jsonify({**sub.to_dict(), "guardada": True, "email_cuenta": user.get("email"), "almacenamiento": "servidor"})


@bp.get("/imagen")
def imagen():
    """Miniatura WebP de una portada de Yahoo (ver ``images.py``)."""
    if current_user() is None:
        return jsonify({"error": "Inicia sesión para ver las imágenes."}), 401
    try:
        width = int(request.args.get("w", images.WIDTHS[0]))
        data = images.thumbnail(request.args.get("u", ""), width)
    except (ValueError, images.ImageError) as exc:
        return jsonify({"error": str(exc) or "Imagen no válida."}), 404
    response = Response(data, mimetype="image/webp")
    # Privada: la sirve una ruta con sesión. Un día de caché en el navegador.
    response.headers["Cache-Control"] = "private, max-age=86400, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
