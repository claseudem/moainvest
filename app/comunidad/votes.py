"""Votos de la comunidad: ¿el activo sube o baja esta semana?

Tabla ``public.votos_activos`` (``migrations/20261114130000_create-votos-activos.sql``).
Cada voto pertenece a una **ronda semanal** (semana ISO en UTC: "2026-W46").
Un usuario tiene **un** voto por activo y ronda (restricción UNIQUE), y puede
cambiarlo mientras la ronda siga abierta. La ronda siguiente empieza de cero.

Los recuentos agregan los votos de todos los usuarios, pero la API solo
publica totales: nunca quién votó qué.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.core import db

TABLE = "votos_activos"
MAX_VOTE_ROWS = 20000

Vote = Literal["up", "down"]
VOTES = ("up", "down")


@dataclass(slots=True)
class Tally:
    ticker: str
    up: int = 0
    down: int = 0
    mine: Vote | None = None

    @property
    def total(self) -> int:
        return self.up + self.down

    def to_dict(self) -> dict:
        pct_up = round(self.up * 100 / self.total) if self.total else None
        return {
            "ticker": self.ticker,
            "sube": self.up,
            "baja": self.down,
            "total": self.total,
            "pct_sube": pct_up,
            "pct_baja": None if pct_up is None else 100 - pct_up,
            "mi_voto": self.mine,
        }


def current_round(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def round_closes_at(now: datetime | None = None) -> datetime:
    """Final de la ronda: el lunes siguiente a las 00:00 UTC."""
    now = now or datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday + timedelta(days=7)


def tallies(user_id: str, tickers: list[str], ronda: str | None = None) -> dict[str, Tally]:
    ronda = ronda or current_round()
    result = {t: Tally(ticker=t) for t in tickers}
    if not tickers:
        return result
    rows = db.request(
        "GET",
        TABLE,
        params={"ronda": f"eq.{ronda}", "ticker": db.in_list(tickers), "select": "ticker,voto,user_id", "limit": MAX_VOTE_ROWS},
    )
    for row in rows if isinstance(rows, list) else []:
        tally = result.get(row.get("ticker"))
        if tally is None or row.get("voto") not in VOTES:
            continue
        if row["voto"] == "up":
            tally.up += 1
        else:
            tally.down += 1
        if row.get("user_id") == user_id:
            tally.mine = row["voto"]
    return result


def cast(user_id: str, ticker: str, vote: Vote, ronda: str | None = None) -> str:
    """Registra o cambia el voto. Devuelve ``"nuevo"``, ``"cambiado"`` o ``"igual"``."""
    ronda = ronda or current_round()
    key = {"user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}", "ronda": f"eq.{ronda}"}
    existing = db.request("GET", TABLE, params={**key, "select": "voto", "limit": 1})
    if isinstance(existing, list) and existing:
        if existing[0].get("voto") == vote:
            return "igual"
        db.request("PATCH", TABLE, params=key, json={"voto": vote}, prefer="return=minimal")
        return "cambiado"
    try:
        db.request("POST", TABLE, json=[{"user_id": user_id, "ticker": ticker, "voto": vote, "ronda": ronda}], prefer="return=minimal")
    except db.DBError as exc:
        if exc.status != 409:
            raise
        # Otra petición simultánea creó el voto: se convierte en un cambio.
        db.request("PATCH", TABLE, params=key, json={"voto": vote}, prefer="return=minimal")
        return "cambiado"
    return "nuevo"
