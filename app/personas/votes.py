"""Votos de sentimiento por activo ("sube" / "baja"): tabla ``public.votos_activos``.

Cada usuario tiene como mucho un voto por ticker (``UNIQUE (user_id, ticker)``):
votar de nuevo lo cambia y votar lo mismo lo retira. Igual que ``favoritos``,
se usa la API REST de InsForge con la API key del servidor, así que toda
escritura filtra por el ``user_id`` de la sesión. La migración está en
``migrations/*_create-votos-activos.sql``.
"""
from __future__ import annotations

import time
from typing import Any

from app.personas import db
from app.personas.db import DBError as VoteStoreError

TABLE = "votos_activos"
VOTES = ("sube", "baja")

# Caché corta del conteo global (lo piden todas las visitas a la página).
_CACHE_TTL = 10
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _request(method: str, *, params: dict | None = None, json: Any = None, prefer: str | None = None) -> Any:
    return db.request(TABLE, method, params=params, json=json, prefer=prefer)


def _all_rows(use_cache: bool = True) -> list[dict[str, Any]]:
    hit = _cache.get("all")
    if use_cache and hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    rows = _request("GET", params={"select": "user_id,ticker,voto", "limit": 10000})
    rows = rows if isinstance(rows, list) else []
    _cache["all"] = (time.time(), rows)
    return rows


def all_rows() -> list[dict[str, Any]]:
    """Todos los votos (``user_id``, ``ticker``, ``voto``). Uso interno del servidor."""
    return _all_rows()


def tally(user_id: str | None, *, use_cache: bool = True) -> dict[str, Any]:
    """``{"counts": {ticker: {"sube": n, "baja": n}}, "mine": {ticker: voto}}``."""
    counts: dict[str, dict[str, int]] = {}
    mine: dict[str, str] = {}
    for row in _all_rows(use_cache):
        vote = row.get("voto")
        if vote not in VOTES:
            continue
        counts.setdefault(row["ticker"], {"sube": 0, "baja": 0})[vote] += 1
        if user_id and row.get("user_id") == user_id:
            mine[row["ticker"]] = vote
    return {"counts": counts, "mine": mine}


def cast(user_id: str, ticker: str, vote: str | None) -> None:
    """Deja el voto del usuario en ``vote`` (``None`` lo retira)."""
    if vote is not None and vote not in VOTES:
        raise ValueError("Voto inválido.")
    _request("DELETE", params={"user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}"})
    if vote is not None:
        _request("POST", json=[{"user_id": user_id, "ticker": ticker, "voto": vote}], prefer="return=minimal")
    _cache.pop("all", None)
