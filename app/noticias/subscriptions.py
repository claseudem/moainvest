"""Suscripción a alertas de noticias: tabla ``public.suscripciones_noticias``.

Una fila por usuario. Sin fila, el usuario no está suscrito y el formulario
propone su correo de cuenta y "Solo mis favoritos".
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Literal

from app.core import db

TABLE = "suscripciones_noticias"
SCOPES = ("todos", "favoritos")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIELDS = "activa,via_app,via_email,email,alcance,ultimo_envio"

Scope = Literal["todos", "favoritos"]


@dataclass(frozen=True, slots=True)
class Subscription:
    activa: bool = False
    via_app: bool = True
    via_email: bool = False
    email: str | None = None
    alcance: Scope = "favoritos"
    ultimo_envio: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class InvalidSubscription(ValueError):
    pass


def _from_row(row: dict) -> Subscription:
    return Subscription(
        activa=bool(row.get("activa")),
        via_app=bool(row.get("via_app")),
        via_email=bool(row.get("via_email")),
        email=row.get("email"),
        alcance=row.get("alcance") if row.get("alcance") in SCOPES else "favoritos",
        ultimo_envio=row.get("ultimo_envio"),
    )


def get(user_id: str, account_email: str | None = None) -> tuple[Subscription, bool]:
    """Suscripción del usuario y si ya existía (si no, valores por defecto con su correo)."""
    rows = db.request("GET", TABLE, params={"user_id": f"eq.{user_id}", "select": FIELDS, "limit": 1})
    if isinstance(rows, list) and rows:
        return _from_row(rows[0]), True
    return Subscription(email=account_email), False


def validate(data: dict, current: Subscription) -> Subscription:
    """Aplica los cambios de ``data`` sobre ``current`` y comprueba que sean coherentes."""
    changes = {}
    for field in ("activa", "via_app", "via_email"):
        if field in data:
            if not isinstance(data[field], bool):
                raise InvalidSubscription(f"'{field}' debe ser verdadero o falso.")
            changes[field] = data[field]
    if "alcance" in data:
        if data["alcance"] not in SCOPES:
            raise InvalidSubscription("El alcance debe ser 'todos' o 'favoritos'.")
        changes["alcance"] = data["alcance"]
    if "email" in data:
        email = (data["email"] or "").strip() or None
        if email is not None and (len(email) > 254 or not EMAIL_RE.match(email)):
            raise InvalidSubscription("Escribe un correo válido, por ejemplo nombre@dominio.com.")
        changes["email"] = email
    sub = replace(current, **changes)
    if sub.activa and not (sub.via_app or sub.via_email):
        raise InvalidSubscription("Elige al menos una vía: la campana de la app o el correo.")
    if sub.via_email and not sub.email:
        raise InvalidSubscription("Para recibirlas por correo, escribe una dirección.")
    return sub


def save(user_id: str, sub: Subscription, exists: bool) -> None:
    data = {k: v for k, v in sub.to_dict().items() if k != "ultimo_envio"}
    if exists:
        db.request("PATCH", TABLE, params={"user_id": f"eq.{user_id}"}, json=data, prefer="return=minimal")
    else:
        db.request("POST", TABLE, json=[{"user_id": user_id, **data}], prefer="return=minimal")


def email_subscribers() -> list[tuple[str, Subscription]]:
    rows = db.request(
        "GET",
        TABLE,
        params={"activa": "eq.true", "via_email": "eq.true", "select": f"user_id,{FIELDS}", "limit": 5000},
    )
    return [(r["user_id"], _from_row(r)) for r in (rows if isinstance(rows, list) else [])]


def mark_sent(user_id: str, when: datetime) -> None:
    db.request("PATCH", TABLE, params={"user_id": f"eq.{user_id}"}, json={"ultimo_envio": when.isoformat()}, prefer="return=minimal")
