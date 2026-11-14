"""API de "¿Qué piensas tú?".

    GET  /api/comunidad/activos?extra=PLTR,AMD   catálogo + tu lista (+ extra) con precio, votos y tu voto
    POST /api/comunidad/votos                    {"ticker": "AAPL", "voto": "up" | "down"}  (crea o cambia)

Todas exigen sesión (401 si no la hay).
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify, request

from app.alertas.service import fetch_quotes
from app.comunidad import votes
from app.core import catalog, db
from app.cuentas.views import current_user
from app.favoritos import search
from app.favoritos.views import TICKER_RE
from app.noticias.api import favorites_of

bp = Blueprint("comunidad_api", __name__, url_prefix="/api/comunidad")

MAX_EXTRA = 5


def _requires_user(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Inicia sesión para votar."}), 401
        try:
            return view(user["id"], *args, **kwargs)
        except db.DBError as exc:
            return jsonify({"error": str(exc)}), 503

    return wrapper


def _exists(ticker: str) -> tuple[bool, str | None]:
    """¿Es un símbolo real de Yahoo? Para votar activos fuera del catálogo."""
    match = next((m for m in search.search(ticker) if m.ticker == ticker), None)
    return match is not None, match.nombre if match else None


def _universe(favorites: list[dict], extra: list[str]) -> tuple[list[str], dict[str, str]]:
    """Tickers de la cuadrícula (tu lista primero, luego el catálogo, luego los buscados) y sus nombres."""
    names = {a.ticker: a.nombre for a in catalog.ASSETS}
    names.update({f["ticker"]: f["nombre"] for f in favorites if f.get("nombre")})
    tickers = [f["ticker"] for f in favorites] + [a.ticker for a in catalog.ASSETS]
    for ticker in extra:
        if ticker in names:
            tickers.append(ticker)
            continue
        ok, name = _exists(ticker)
        if ok:
            tickers.append(ticker)
            names[ticker] = name or ticker
    return list(dict.fromkeys(tickers)), names


def _items(user_id: str, tickers: list[str], names: dict[str, str], favorites: list[dict]) -> tuple[list[dict], bool]:
    """Tarjetas de ``tickers`` y si la votación está disponible.

    Si la tabla de votos aún no existe, la cuadrícula se carga igual con 0
    votos (``False``): el frontend guarda los votos en el navegador mientras tanto.
    """
    mine = {f["ticker"] for f in favorites}
    quotes = fetch_quotes(tickers)
    available = True
    try:
        counts = votes.tallies(user_id, tickers)
    except db.DBError as exc:
        if not exc.missing_table:
            raise
        available = False
        counts = {t: votes.Tally(ticker=t) for t in tickers}
    items = []
    for ticker in tickers:
        asset = catalog.get(ticker)
        quote = quotes.get(ticker)
        category = asset.categoria if asset else "otros"
        items.append(
            {
                **counts[ticker].to_dict(),
                "nombre": names.get(ticker, ticker),
                "categoria": category,
                "categoria_nombre": catalog.CATEGORY_NAMES.get(category, "Otros"),
                "en_lista": ticker in mine,
                "precio": quote.price if quote else None,
                "moneda": quote.currency if quote else None,
                "variacion": quote.change_percent if quote else None,
            }
        )
    return items, available


def _round() -> dict:
    return {"ronda": votes.current_round(), "cierra": votes.round_closes_at().isoformat()}


@bp.get("/activos")
@_requires_user
def activos(user_id: str):
    extra = [t.strip().upper() for t in (request.args.get("extra") or "").split(",") if t.strip()]
    extra = [t for t in extra if TICKER_RE.match(t)][:MAX_EXTRA]
    favorites = favorites_of(user_id)
    tickers, names = _universe(favorites, extra)
    items, available = _items(user_id, tickers, names, favorites)
    return jsonify(
        {
            **_round(),
            "categorias": [{"slug": c.slug, "nombre": c.name} for c in catalog.CATEGORIES],
            "votos_disponibles": available,
            "items": items,
        }
    )


@bp.post("/votos")
@_requires_user
def votar(user_id: str):
    data = request.get_json(silent=True) or {}
    ticker = str(data.get("ticker") or "").strip().upper()
    vote = data.get("voto")
    if vote not in votes.VOTES:
        return jsonify({"error": "El voto debe ser 'up' (sube) o 'down' (baja)."}), 400
    if not TICKER_RE.match(ticker):
        return jsonify({"error": "Ese ticker no es válido."}), 400
    favorites = favorites_of(user_id)
    known = catalog.get(ticker) is not None or any(f["ticker"] == ticker for f in favorites)
    if not known and not _exists(ticker)[0]:
        return jsonify({"error": f"No encontramos «{ticker}» en Yahoo Finance."}), 400
    try:
        result = votes.cast(user_id, ticker, vote)
    except db.DBError as exc:
        if not exc.missing_table:
            raise
        # El voto es válido, pero aún no hay dónde guardarlo: el navegador lo conserva.
        body, status = db.pending_table(votes.TABLE, ticker=ticker, voto=vote, **_round())
        return jsonify(body), status
    _, names = _universe(favorites, [ticker])
    item = _items(user_id, [ticker], names, favorites)[0][0]
    return jsonify({**_round(), "resultado": result, "item": item}), 201 if result == "nuevo" else 200
