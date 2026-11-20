"""Perfiles de comunidad, notas por activo y relaciones (seguir / conectar).

Tablas (``migrations/*_create-comunidad-perfiles-notas.sql``):

- ``perfiles_comunidad``: nombre visible, profesión, bio, perfil de interés,
  avatar y si el perfil es visible. Un perfil no visible nunca sale del
  servidor hacia otros usuarios: sus notas aparecen como "Miembro de la
  comunidad".
- ``notas_activos``: una nota (etiqueta rápida y/o texto corto) por usuario y
  activo: su tesis. Escribir otra la reemplaza.
- ``relaciones_comunidad``: ``seguir`` (unilateral) y ``conectar`` (la conexión
  queda hecha cuando ambos la piden).
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from app.favoritos import store as favorites_store
from app.personas import db, votes

PROFILES = "perfiles_comunidad"
NOTES = "notas_activos"
RELATIONS = "relaciones_comunidad"

# Reacciones rápidas: la misma lista en el servidor y en la página.
QUICK_TAGS: tuple[str, ...] = (
    "Alcista por resultados",
    "Cautela por volatilidad",
    "Soporte clave",
    "Resistencia cercana",
    "Esperando noticias",
    "Visión de largo plazo",
)

AVATAR_COLORS: tuple[str, ...] = ("#c8102e", "#171717", "#0f8a5f", "#1f5fbf", "#b25e09", "#6b3fa0")

MAX_NAME = 60
MAX_PROFESSION = 60
MAX_BIO = 280
MAX_NOTE = 140
MAX_AVATAR = 80000
ANONYMOUS = "Miembro de la comunidad"

_DATA_URL = re.compile(r"^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_INITIALS = re.compile(r"^iniciales:(#[0-9a-fA-F]{6})$")

_CACHE_TTL = 10
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, loader):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    value = loader()
    _cache[key] = (time.time(), value)
    return value


def clear_cache() -> None:
    _cache.clear()


def _rows(value: Any) -> list[dict]:
    return value if isinstance(value, list) else []


# ── Perfiles ──────────────────────────────────────────────────────


def _clean(value: Any, limit: int) -> str | None:
    text = " ".join(str(value or "").split())[:limit]
    return text or None


def valid_avatar(value: Any) -> str | None:
    """Foto reducida (data URL) o ``iniciales:<color>``; ``None`` si no es válido."""
    if not isinstance(value, str) or not value:
        return None
    if len(value) <= MAX_AVATAR and _DATA_URL.match(value):
        return value
    match = _INITIALS.match(value)
    if match and match.group(1).lower() in AVATAR_COLORS:
        return value
    return None


def get_profile(user_id: str) -> dict | None:
    rows = _rows(db.request(PROFILES, "GET", params={"user_id": f"eq.{user_id}", "limit": 1}))
    return rows[0] if rows else None


def save_profile(user_id: str, data: dict, *, valid_slugs: set[str]) -> dict:
    row = {
        "nombre": _clean(data.get("nombre"), MAX_NAME),
        "profesion": _clean(data.get("profesion"), MAX_PROFESSION),
        "bio": _clean(data.get("bio"), MAX_BIO),
        "perfil": data.get("perfil") if data.get("perfil") in valid_slugs else None,
        "avatar": valid_avatar(data.get("avatar")),
        "visible": bool(data.get("visible")),
    }
    if get_profile(user_id) is None:
        db.request(PROFILES, "POST", json=[{"user_id": user_id, **row}], prefer="return=minimal")
    else:
        updated = {**row, "updated_at": datetime.now(timezone.utc).isoformat()}
        db.request(PROFILES, "PATCH", params={"user_id": f"eq.{user_id}"}, json=updated, prefer="return=minimal")
    clear_cache()
    return {"user_id": user_id, **row}


def _visible_profiles() -> list[dict]:
    return _cached(
        "visible",
        lambda: _rows(db.request(PROFILES, "GET", params={"visible": "eq.true", "limit": 500, "order": "updated_at.desc"})),
    )


def public_card(profile: dict) -> dict:
    """Lo que otros ven de un perfil visible."""
    return {
        "id": profile["user_id"],
        "name": profile.get("nombre") or "Miembro",
        "profession": profile.get("profesion"),
        "bio": profile.get("bio"),
        "profile": profile.get("perfil"),
        "avatar": profile.get("avatar"),
    }


# ── Notas ─────────────────────────────────────────────────────────


def _all_notes() -> list[dict]:
    return _cached(
        "notes",
        lambda: _rows(
            db.request(
                NOTES,
                "GET",
                params={"select": "user_id,ticker,etiqueta,texto,created_at", "order": "created_at.desc", "limit": 1000},
            )
        ),
    )


def notes(viewer_id: str | None, *, ticker: str | None = None, author_id: str | None = None) -> list[dict]:
    """Notas más recientes primero, con autor (si su perfil es visible) y su voto."""
    authors = {p["user_id"]: public_card(p) for p in _visible_profiles()}
    vote_of = {(v["user_id"], v["ticker"]): v["voto"] for v in votes.all_rows()}
    rows = [
        row
        for row in _all_notes()
        if (not ticker or row["ticker"] == ticker) and (not author_id or row["user_id"] == author_id)
    ]
    # La propia foto se muestra aunque el perfil no sea visible (solo la ve su dueño).
    own_avatar = None
    if viewer_id and any(row["user_id"] == viewer_id for row in rows):
        own = authors.get(viewer_id) or get_profile(viewer_id)
        own_avatar = (own or {}).get("avatar")
    items = []
    for row in rows:
        mine = viewer_id is not None and row["user_id"] == viewer_id
        author = authors.get(row["user_id"])
        items.append(
            {
                "ticker": row["ticker"],
                "tag": row.get("etiqueta"),
                "text": row.get("texto"),
                "created": row.get("created_at"),
                "vote": vote_of.get((row["user_id"], row["ticker"])),
                "mine": mine,
                "author": {"name": "Tú", "avatar": own_avatar}
                if mine
                else {"name": author["name"], "avatar": author["avatar"]}
                if author
                else {"name": ANONYMOUS, "avatar": None},
                "authorId": author["id"] if author and not mine else None,
            }
        )
    return items


def save_note(user_id: str, ticker: str, tag: str | None, text: Any) -> None:
    tag = tag if tag in QUICK_TAGS else None
    text = _clean(text, MAX_NOTE)
    if not tag and not text:
        raise ValueError("Elige una reacción o escribe una nota.")
    db.request(NOTES, "DELETE", params={"user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}"})
    db.request(NOTES, "POST", json=[{"user_id": user_id, "ticker": ticker, "etiqueta": tag, "texto": text}], prefer="return=minimal")
    clear_cache()


def delete_note(user_id: str, ticker: str) -> None:
    db.request(NOTES, "DELETE", params={"user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}"})
    clear_cache()


# ── Relaciones y miembros ─────────────────────────────────────────


def _relations(user_id: str) -> list[dict]:
    return _rows(
        db.request(
            RELATIONS,
            "GET",
            params={"or": f"(user_id.eq.{user_id},objetivo_id.eq.{user_id})", "select": "user_id,objetivo_id,tipo", "limit": 2000},
        )
    )


def set_relation(user_id: str, target_id: str, kind: str, active: bool) -> None:
    if kind not in ("seguir", "conectar") or target_id == user_id or not _UUID.match(target_id):
        raise ValueError("Relación inválida.")
    if active and target_id not in {p["user_id"] for p in _visible_profiles()}:
        raise ValueError("Ese perfil no es público.")
    params = {"user_id": f"eq.{user_id}", "objetivo_id": f"eq.{target_id}", "tipo": f"eq.{kind}"}
    db.request(RELATIONS, "DELETE", params=params)
    if active:
        db.request(RELATIONS, "POST", json=[{"user_id": user_id, "objetivo_id": target_id, "tipo": kind}], prefer="return=minimal")


def _favorites_of(user_ids: list[str]) -> dict[str, list[str]]:
    if not user_ids:
        return {}
    rows = _rows(
        db.request(
            favorites_store.TABLE,
            "GET",
            params={"user_id": db.in_list(user_ids), "select": "user_id,ticker", "order": "created_at.asc", "limit": 2000},
        )
    )
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row["user_id"], []).append(row["ticker"])
    return out


def members(viewer_id: str) -> list[dict]:
    """Perfiles públicos (sin el propio), con sus activos, votos y la relación con quien mira."""
    profiles = [p for p in _visible_profiles() if p["user_id"] != viewer_id]
    ids = [p["user_id"] for p in profiles]
    favorites = _favorites_of(ids)
    member_votes: dict[str, dict[str, str]] = {}
    id_set = set(ids)
    for row in votes.all_rows():
        if row["user_id"] in id_set:
            member_votes.setdefault(row["user_id"], {})[row["ticker"]] = row["voto"]
    rel = _relations(viewer_id)
    mine = {(r["objetivo_id"], r["tipo"]) for r in rel if r["user_id"] == viewer_id}
    theirs = {(r["user_id"], r["tipo"]) for r in rel if r["objetivo_id"] == viewer_id}

    result = []
    for profile in profiles:
        uid = profile["user_id"]
        sent, received = (uid, "conectar") in mine, (uid, "conectar") in theirs
        connection = "conectados" if sent and received else "enviada" if sent else "recibida" if received else None
        result.append(
            {
                **public_card(profile),
                "assets": favorites.get(uid, []),
                "votes": member_votes.get(uid, {}),
                "following": (uid, "seguir") in mine,
                "followsYou": (uid, "seguir") in theirs,
                "connection": connection,
            }
        )
    return result


def social_counts(user_id: str) -> dict[str, int]:
    rel = _relations(user_id)
    connect_out = {r["objetivo_id"] for r in rel if r["user_id"] == user_id and r["tipo"] == "conectar"}
    connect_in = {r["user_id"] for r in rel if r["objetivo_id"] == user_id and r["tipo"] == "conectar"}
    return {
        "following": sum(1 for r in rel if r["user_id"] == user_id and r["tipo"] == "seguir"),
        "followers": sum(1 for r in rel if r["objetivo_id"] == user_id and r["tipo"] == "seguir"),
        "connections": len(connect_out & connect_in),
    }


# ── Comentarios públicos (carrusel «Comunidad» del inicio) ────────

# Etiquetas rápidas que implican una postura cuando la nota no tiene voto.
_TAG_STANCE = {"Alcista por resultados": "sube", "Soporte clave": "sube", "Visión de largo plazo": "sube",
               "Cautela por volatilidad": "baja", "Resistencia cercana": "baja"}

# DEMO: comentarios de ejemplo sobre los activos del resumen, para completar el
# carrusel cuando aún hay pocas notas reales. Se marcan con ``demo=True``.
# (ticker, postura, texto, nombre, horas atrás)
DEMO_COMMENTS: tuple[tuple[str, str, str, str, int], ...] = (
    ("^GSPC", "sube", "La amplitud del mercado mejora: más sectores acompañan a las tecnológicas.", "Laura M.", 2),
    ("BTC-USD", "baja", "Pierde el soporte de la media de 50 días; espero una corrección antes de seguir.", "Andrés P.", 3),
    ("^IXIC", "sube", "Los resultados de los semiconductores siguen sosteniendo al índice.", "Camila R.", 5),
    ("EURUSD=X", "baja", "Si la Fed mantiene tasas altas, el dólar debería seguir fuerte frente al euro.", "Santiago G.", 7),
    ("UEC", "sube", "Contratos de uranio a largo plazo y demanda nuclear: tesis de varios años.", "Valentina S.", 9),
    ("^DJI", "baja", "Industriales presionados por costos; prefiero esperar al próximo reporte.", "Mateo L.", 12),
)
MIN_COMMENTS = 6


def _initials(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w and w[0].isalnum()]
    parts = [w for w in words if not (len(w) <= 3 and w.islower())] or words  # sin «de», «la»…
    return "".join(p[0] for p in parts[:2]).upper() or "M"


def public_comments(limit: int = 12) -> tuple[list[dict], bool]:
    """Notas recientes con texto, para mostrarlas a cualquiera (sin sesión).

    Solo sale el nombre de los perfiles visibles (los demás son "Miembro de la
    comunidad") y nunca el id del autor ni su foto. Si hay menos de
    ``MIN_COMMENTS``, se completa con ``DEMO_COMMENTS``; el segundo valor dice
    si se usaron ejemplos.
    """
    items = []
    for note in notes(None):
        text = note["text"] or note["tag"]
        if not text:
            continue
        stance = note["vote"] or _TAG_STANCE.get(note["tag"] or "")
        name = note["author"]["name"]
        items.append({
            "ticker": note["ticker"], "stance": stance, "text": text, "tag": note["tag"] if note["text"] else None,
            "name": name, "initials": _initials(name), "created": note["created"], "demo": False,
        })
        if len(items) >= limit:
            break
    used_demo = len(items) < MIN_COMMENTS
    if used_demo:
        items += demo_comments(MIN_COMMENTS - len(items))
    return items, used_demo


def demo_comments(count: int = MIN_COMMENTS) -> list[dict]:
    now = datetime.now(timezone.utc).timestamp()
    return [
        {
            "ticker": ticker, "stance": stance, "text": text, "tag": None, "name": name, "initials": _initials(name),
            "created": datetime.fromtimestamp(now - hours * 3600, tz=timezone.utc).isoformat(), "demo": True,
        }
        for ticker, stance, text, name, hours in DEMO_COMMENTS[:count]
    ]
