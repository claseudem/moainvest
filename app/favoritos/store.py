"""Almacén de activos favoritos: tabla ``public.activos_favoritos`` de InsForge.

Se accede por la API REST de base de datos con la API key del proyecto (solo
servidor, ``INSFORGE_API_KEY``). Como esa clave salta el RLS, **todas** las
consultas filtran por ``user_id`` (el de la sesión). La tabla además tiene RLS
(cada usuario solo ve lo suyo) para cualquier acceso directo con su JWT.
"""
from __future__ import annotations

import time
from typing import Any

import requests
from flask import current_app

TABLE = "activos_favoritos"
TIMEOUT = 10
MAX_FAVORITES = 50

# Caché por usuario del sidebar (se pinta en cada página de /app/): evita una
# petición a InsForge por vista. Se invalida al escribir.
_CACHE_TTL = 30
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class StoreError(Exception):
    """No se pudo hablar con InsForge (red, clave o tabla)."""


def _request(method: str, *, params: dict | None = None, json: Any = None, prefer: str | None = None) -> Any:
    base = current_app.config["INSFORGE_URL"].rstrip("/")
    key = current_app.config["INSFORGE_API_KEY"]
    if not base or not key:
        raise StoreError("Favoritos no configurado (INSFORGE_URL / INSFORGE_API_KEY).")
    headers = {"Authorization": f"Bearer {key}"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(
            method, f"{base}/api/database/records/{TABLE}", params=params, json=json, headers=headers, timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        raise StoreError("No se pudo conectar con la base de datos.") from exc
    if response.status_code >= 400:
        raise StoreError(f"InsForge respondió {response.status_code}.")
    try:
        return response.json()
    except ValueError:
        return None


def list_favorites(user_id: str, *, use_cache: bool = True) -> list[dict[str, Any]]:
    hit = _cache.get(user_id)
    if use_cache and hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    rows = _request(
        "GET",
        params={"user_id": f"eq.{user_id}", "select": "ticker,nombre,created_at", "order": "created_at.asc", "limit": MAX_FAVORITES},
    )
    rows = rows if isinstance(rows, list) else []
    _cache[user_id] = (time.time(), rows)
    return rows


def add_favorite(user_id: str, ticker: str, nombre: str | None = None) -> bool:
    """Agrega un favorito. Devuelve ``False`` si ya estaba o se alcanzó el máximo."""
    current = list_favorites(user_id, use_cache=False)
    if len(current) >= MAX_FAVORITES or any(r["ticker"] == ticker for r in current):
        return False
    _request("POST", json=[{"user_id": user_id, "ticker": ticker, "nombre": nombre}], prefer="return=minimal")
    _cache.pop(user_id, None)
    return True


def remove_favorite(user_id: str, ticker: str) -> None:
    _request("DELETE", params={"user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}"})
    _cache.pop(user_id, None)
