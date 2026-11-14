"""Controlador de la app "Mis activos": activos favoritos de cada usuario.

La página lista los favoritos en una tabla con su precio y permite agregar o
quitar; además, ``inject_favorites`` los expone al sidebar de toda el área App.
"""
from __future__ import annotations

import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.core import market_data
from app.core.navigation import get_app
from app.cuentas.views import current_user
from app.favoritos import store
from app.favoritos.store import StoreError

bp = Blueprint(
    "favoritos",
    __name__,
    url_prefix="/app/favoritos",
    template_folder="templates",
    static_folder="static",
)

# Tickers de Yahoo: letras, números y ``^ = . -`` (igual que el Graficador).
TICKER_RE = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")
MAX_NAME = 120


def _resolve_name(ticker: str, proposed: str) -> tuple[str | None, str | None]:
    """Nombre del activo y, si el ticker no existe, una sugerencia.

    Devuelve ``(nombre, None)`` si el ticker es válido o ``(None, sugerencia)``
    si Yahoo no lo conoce (p. ej. "APPL" → sugiere "AAPL"). El nombre que llega
    del autocompletado se usa tal cual para ahorrar una consulta.
    """
    from app.favoritos import search

    if proposed:
        return proposed[:MAX_NAME], None
    name = market_data.get_display_name(ticker)
    if name != ticker:
        return name, None
    # Yahoo no tiene nombre: puede ser un ticker sin "info" (índices, divisas)
    # o una errata. La búsqueda lo distingue.
    matches = search.search(ticker)
    if any(m.ticker == ticker for m in matches):
        return next(m.nombre for m in matches if m.ticker == ticker), None
    return None, (matches[0].ticker if matches else None)


@bp.app_context_processor
def inject_favorites() -> dict:
    """Favoritos del usuario para el sidebar (vacío si no hay sesión o falla InsForge)."""
    user = current_user()
    if user is None or not request.path.startswith("/app/"):
        return {"favorite_assets": []}
    try:
        return {"favorite_assets": store.list_favorites(user["id"])}
    except StoreError:
        return {"favorite_assets": []}


@bp.get("/")
def index():
    user = current_user()
    error = None
    rows: list[dict] = []
    if user is not None:
        try:
            rows = store.list_favorites(user["id"], use_cache=False)
        except StoreError as exc:
            error = str(exc)
    return render_template(
        "favoritos/index.html",
        active_app=get_app("favoritos"),
        favorites=rows,
        error=error,
        max_favorites=store.MAX_FAVORITES,
    )


@bp.post("/agregar")
def agregar():
    user = current_user()
    ticker = (request.form.get("ticker") or "").strip().upper()
    if user is None:
        return redirect(url_for("cuentas.ingresar", next=url_for("favoritos.index")))
    if not TICKER_RE.match(ticker):
        flash(f"«{ticker}» no es un ticker válido de Yahoo Finance.", "error")
    else:
        try:
            name, suggestion = _resolve_name(ticker, (request.form.get("nombre") or "").strip())
            if name is None:
                hint = f" ¿Quisiste decir {suggestion}?" if suggestion else " Prueba a buscarlo por nombre."
                flash(f"No encontramos «{ticker}» en Yahoo Finance.{hint}", "error")
            elif store.add_favorite(user["id"], ticker, name):
                flash(f"{ticker} agregado a tus activos.", "info")
            else:
                flash(f"{ticker} ya está en tus activos (o llegaste al máximo de {store.MAX_FAVORITES}).", "info")
        except StoreError as exc:
            flash(str(exc), "error")
    return redirect(url_for("favoritos.index"))


@bp.post("/quitar")
def quitar():
    user = current_user()
    ticker = (request.form.get("ticker") or "").strip().upper()
    if user is None:
        return redirect(url_for("cuentas.ingresar", next=url_for("favoritos.index")))
    if TICKER_RE.match(ticker):
        try:
            store.remove_favorite(user["id"], ticker)
            flash(f"{ticker} quitado de tus activos.", "info")
        except StoreError as exc:
            flash(str(exc), "error")
    return redirect(url_for("favoritos.index"))
