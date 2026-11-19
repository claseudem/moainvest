"""Acceso a las tablas de COMUNIDAD en InsForge (API REST de base de datos).

Se usa la API key del proyecto (solo servidor, ``INSFORGE_API_KEY``). Esa clave
salta el RLS, así que cada módulo filtra siempre por el ``user_id`` de la
sesión al escribir. Las tablas se crean con las migraciones de ``migrations/``.
"""
from __future__ import annotations

from typing import Any

import requests
from flask import current_app

TIMEOUT = 10


class DBError(Exception):
    """No se pudo hablar con InsForge (red, clave o tabla sin crear)."""


def request(table: str, method: str, *, params: dict | None = None, json: Any = None, prefer: str | None = None) -> Any:
    base = current_app.config["INSFORGE_URL"].rstrip("/")
    key = current_app.config["INSFORGE_API_KEY"]
    if not base or not key:
        raise DBError("Base de datos no configurada (INSFORGE_URL / INSFORGE_API_KEY).")
    headers = {"Authorization": f"Bearer {key}"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(
            method, f"{base}/api/database/records/{table}", params=params, json=json, headers=headers, timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        raise DBError("No se pudo conectar con la base de datos.") from exc
    if response.status_code >= 400:
        raise DBError(f"InsForge respondió {response.status_code}.")
    try:
        return response.json()
    except ValueError:
        return None


def in_list(values: list[str]) -> str:
    """Filtro ``in.(a,b)`` de PostgREST, con cada valor entre comillas."""
    return "in.(" + ",".join('"' + v.replace('"', "") + '"' for v in values) + ")"
