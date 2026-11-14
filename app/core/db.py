"""Cliente mínimo de la API REST de base de datos de InsForge (solo servidor).

Usa la API key del proyecto (``INSFORGE_API_KEY``), que salta el RLS: quien
lo use debe filtrar **siempre** por ``user_id`` en los datos de cada usuario.
Es el mismo patrón que ``favoritos/store.py`` y ``alertas/store.py``; las apps
nuevas (noticias, comunidad) lo usan directamente.
"""
from __future__ import annotations

from typing import Any

import requests
from flask import current_app

TIMEOUT = 10


class DBError(Exception):
    """No se pudo hablar con InsForge (red, clave o tabla)."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code  # código de Postgres, p. ej. "42P01"

    @property
    def missing_table(self) -> bool:
        """La tabla aún no existe (falta aplicar su migración). Una tabla vacía no es esto: devuelve []."""
        return self.status == 404 and self.code in (UNDEFINED_TABLE, None)


# Postgres: "relation ... does not exist". InsForge lo devuelve como HTTP 404.
UNDEFINED_TABLE = "42P01"


def request(method: str, table: str, *, params: dict | None = None, json: Any = None, prefer: str | None = None) -> Any:
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
        try:
            code = (response.json() or {}).get("code")
        except (ValueError, AttributeError):
            code = None
        if response.status_code == 404 and code == UNDEFINED_TABLE:
            raise DBError(f"La tabla «{table}» aún no existe en InsForge.", 404, code)
        raise DBError(f"InsForge respondió {response.status_code}.", response.status_code, code)
    try:
        return response.json()
    except ValueError:
        return None


def pending_table(table: str, **extra: Any) -> tuple[dict, int]:
    """Respuesta JSON para "falta crear la tabla": el frontend guarda en local y reintenta luego."""
    return {
        "error": f"La tabla «{table}» aún no existe en InsForge. Aplica su migración.",
        "codigo": "tabla_pendiente",
        "tabla": table,
        **extra,
    }, 503


def in_list(values: list[str]) -> str:
    """Filtro ``in.(...)`` con los valores entre comillas (admiten ``^ = . -``)."""
    return "in.(" + ",".join(f'"{v}"' for v in values) + ")"
