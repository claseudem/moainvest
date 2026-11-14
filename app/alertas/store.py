"""Almacén de las alertas en InsForge: preferencias y alertas de cada usuario.

Tablas (``migrations/20261114120000_create-alertas.sql``):

* ``alertas_preferencias``: una fila por usuario (umbral y watchlists silenciadas).
* ``alertas``: una fila por aviso, con el titular de contexto.

Se accede por la API REST de base de datos con la API key del proyecto (solo
servidor, ``INSFORGE_API_KEY``), igual que ``app/favoritos/store.py``. Esa
clave salta el RLS, así que **todas** las consultas filtran por ``user_id``.
"""
from __future__ import annotations

from typing import Any

import requests
from flask import current_app

from app.alertas.rules import DEFAULT_THRESHOLD, Settings, Trigger

PREFS_TABLE = "alertas_preferencias"
ALERTS_TABLE = "alertas"
TIMEOUT = 10
LIST_LIMIT = 30


class StoreError(Exception):
    """No se pudo hablar con InsForge (red, clave o tabla)."""


def _request(method: str, table: str, *, params: dict | None = None, json: Any = None, prefer: str | None = None) -> Any:
    base = current_app.config["INSFORGE_URL"].rstrip("/")
    key = current_app.config["INSFORGE_API_KEY"]
    if not base or not key:
        raise StoreError("Alertas no configuradas (INSFORGE_URL / INSFORGE_API_KEY).")
    headers = {"Authorization": f"Bearer {key}"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(
            method, f"{base}/api/database/records/{table}", params=params, json=json, headers=headers, timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        raise StoreError("No se pudo conectar con la base de datos.") from exc
    if response.status_code >= 400:
        raise StoreError(f"InsForge respondió {response.status_code}.")
    try:
        return response.json()
    except ValueError:
        return None


# ---- Preferencias ----

def get_settings(user_id: str) -> tuple[Settings, bool]:
    """Preferencias del usuario y si ya estaban guardadas (si no, valores por defecto)."""
    rows = _request("GET", PREFS_TABLE, params={"user_id": f"eq.{user_id}", "select": "umbral,silenciadas", "limit": 1})
    if not isinstance(rows, list) or not rows:
        return Settings(), False
    row = rows[0]
    return Settings(threshold=int(row.get("umbral") or DEFAULT_THRESHOLD), muted_watchlists=frozenset(row.get("silenciadas") or ())), True


def save_settings(user_id: str, settings: Settings) -> None:
    data = {"umbral": settings.threshold, "silenciadas": sorted(settings.muted_watchlists)}
    _, exists = get_settings(user_id)
    if exists:
        _request("PATCH", PREFS_TABLE, params={"user_id": f"eq.{user_id}"}, json=data, prefer="return=minimal")
    else:
        _request("POST", PREFS_TABLE, json=[{"user_id": user_id, **data}], prefer="return=minimal")


def users_with_settings() -> list[tuple[str, Settings]]:
    """Todos los usuarios que guardaron preferencias (para ``flask alertas-scan``)."""
    rows = _request("GET", PREFS_TABLE, params={"select": "user_id,umbral,silenciadas", "limit": 1000})
    return [
        (r["user_id"], Settings(threshold=int(r.get("umbral") or DEFAULT_THRESHOLD), muted_watchlists=frozenset(r.get("silenciadas") or ())))
        for r in (rows if isinstance(rows, list) else [])
    ]


# ---- Alertas ----

def list_alerts(user_id: str, limit: int = LIST_LIMIT) -> list[dict[str, Any]]:
    rows = _request(
        "GET",
        ALERTS_TABLE,
        params={"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc", "limit": limit},
    )
    return rows if isinstance(rows, list) else []


def sent_keys(user_id: str, sessions: set[str]) -> set[tuple[str, str, str, int]]:
    """Claves ``(ticker, sesión, dirección, nivel)`` ya notificadas en esas sesiones."""
    if not sessions:
        return set()
    rows = _request(
        "GET",
        ALERTS_TABLE,
        params={
            "user_id": f"eq.{user_id}",
            "sesion": "in.(" + ",".join(f'"{s}"' for s in sorted(sessions)) + ")",
            "select": "ticker,sesion,direccion,nivel",
            "limit": 1000,
        },
    )
    return {(r["ticker"], r["sesion"], r["direccion"], int(r["nivel"])) for r in (rows if isinstance(rows, list) else [])}


def insert_alert(user_id: str, trigger: Trigger, headline: dict[str, Any] | None) -> None:
    headline = headline or {}
    _request(
        "POST",
        ALERTS_TABLE,
        json=[
            {
                "user_id": user_id,
                "ticker": trigger.ticker,
                "nombre": trigger.name,
                "watchlists": list(trigger.watchlists),
                "variacion": round(trigger.change_percent, 4),
                "precio": trigger.price,
                "moneda": trigger.currency,
                "direccion": trigger.direction,
                "nivel": trigger.level,
                "umbral": trigger.threshold,
                "sesion": trigger.session,
                "noticia_titulo": headline.get("title"),
                "noticia_fuente": headline.get("publisher"),
                "noticia_url": headline.get("url"),
                "noticia_fecha": headline.get("published_at_iso"),
            }
        ],
        prefer="return=minimal",
    )


def mark_read(user_id: str, ids: list[str] | None = None) -> None:
    """Marca como leídas esas alertas (o todas las no leídas si ``ids`` es ``None``)."""
    params = {"user_id": f"eq.{user_id}", "leida": "eq.false"}
    if ids is not None:
        if not ids:
            return
        params["id"] = f"in.({','.join(ids)})"
    _request("PATCH", ALERTS_TABLE, params=params, json={"leida": True}, prefer="return=minimal")
