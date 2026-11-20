"""COMUNIDAD social: perfil de comunidad, notas por activo y seguir / conectar.

La API REST de base de datos de InsForge está simulada (``FakeDB``).
"""
import json

import pytest

from app.personas import db, members, votes

ME = {"id": "11111111-1111-4111-8111-111111111111", "email": "ana@example.com", "name": "Ana"}
OTHER = "22222222-2222-4222-8222-222222222222"
HIDDEN = "33333333-3333-4333-8333-333333333333"


class FakeDB:
    """Imita /api/database/records/<tabla> con filtros eq., in. y or=(…)."""

    def __init__(self):
        self.tables = {t: [] for t in ("perfiles_comunidad", "notas_activos", "relaciones_comunidad", "votos_activos", "activos_favoritos")}

    @staticmethod
    def _match(row, params):
        for key, cond in (params or {}).items():
            if key in ("select", "order", "limit"):
                continue
            if key == "or":
                options = cond.strip("()").split(",")
                if not any(str(row.get(o.split(".")[0])) == o.split(".", 2)[2] for o in options):
                    return False
            elif cond.startswith("eq."):
                value = cond[3:]
                if str(row.get(key)).lower() != value.lower():
                    return False
            elif cond.startswith("in."):
                values = [v.strip('"') for v in cond[4:-1].split(",")]
                if row.get(key) not in values:
                    return False
        return True

    def __call__(self, table, method, *, params=None, json=None, prefer=None):
        rows = self.tables[table]
        if method == "GET":
            found = [dict(r) for r in rows if self._match(r, params)]
            if (params or {}).get("order", "").endswith(".desc"):
                found.reverse()
            return found
        if method == "POST":
            rows.extend(dict(r, created_at=f"2026-11-19T10:{len(rows):02d}:00+00:00") for r in json)
        if method == "PATCH":
            for r in rows:
                if self._match(r, params):
                    r.update(json)
        if method == "DELETE":
            self.tables[table] = [r for r in rows if not self._match(r, params)]
        return None


@pytest.fixture
def fake(monkeypatch):
    f = FakeDB()
    monkeypatch.setattr(db, "request", f)
    members.clear_cache()
    votes._cache.clear()
    return f


@pytest.fixture
def me(client):
    with client.session_transaction() as session:
        session["user"] = ME
    return client


def test_profile_round_trip_and_validation(me, fake):
    body = {"nombre": "  Ana  Pérez ", "profesion": "Ingeniería", "bio": "Largo plazo.", "visible": True,
            "perfil": "inversionista", "avatar": "iniciales:#c8102e"}
    data = me.put("/api/comunidad/perfil", json=body).get_json()
    assert data["profile"]["nombre"] == "Ana Pérez"
    assert data["profile"]["visible"] is True and data["profile"]["perfil"] == "inversionista"

    data = me.put("/api/comunidad/perfil", json={**body, "perfil": "inventado", "profesion": "x" * 200}).get_json()
    assert data["profile"]["perfil"] is None
    assert len(data["profile"]["profesion"]) == members.MAX_PROFESSION
    assert len(fake.tables["perfiles_comunidad"]) == 1, "editar no crea otro perfil"


@pytest.mark.parametrize("avatar", ["javascript:alert(1)", "iniciales:#123456", "data:image/svg+xml;base64,PHN2Zz4=", "data:image/jpeg;base64," + "A" * 90000])
def test_bad_avatars_are_rejected(me, fake, avatar):
    assert me.put("/api/comunidad/perfil", json={"avatar": avatar}).status_code == 400


def test_photo_avatar_is_accepted(me, fake):
    response = me.put("/api/comunidad/perfil", json={"avatar": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="})
    assert response.status_code == 200


def test_notes_one_per_asset_with_tag_or_text(me, fake):
    assert me.post("/api/comunidad/notas", json={"ticker": "AAPL"}).status_code == 400
    me.post("/api/comunidad/notas", json={"ticker": "AAPL", "tag": "Soporte clave"})
    me.post("/api/comunidad/notas", json={"ticker": "aapl", "tag": "Inventada", "text": "Mejor espero resultados"})
    notes = me.get("/api/comunidad/notas?ticker=AAPL").get_json()["items"]
    assert len(notes) == 1, "una segunda nota reemplaza la anterior"
    assert notes[0]["tag"] is None and notes[0]["text"] == "Mejor espero resultados"
    assert notes[0]["mine"] is True and notes[0]["author"]["name"] == "Tú"

    me.delete("/api/comunidad/notas/AAPL")
    assert me.get("/api/comunidad/notas").get_json()["items"] == []


def test_note_authors_respect_visibility(me, fake):
    fake.tables["perfiles_comunidad"] += [
        {"user_id": OTHER, "nombre": "Luis", "visible": True, "avatar": None},
        {"user_id": HIDDEN, "nombre": "Secreto", "visible": False, "avatar": None},
    ]
    fake.tables["notas_activos"] += [
        {"user_id": OTHER, "ticker": "MSFT", "etiqueta": "Soporte clave", "texto": None, "created_at": "2026-11-19T09:00:00+00:00"},
        {"user_id": HIDDEN, "ticker": "MSFT", "etiqueta": None, "texto": "Hola", "created_at": "2026-11-19T09:01:00+00:00"},
    ]
    fake.tables["votos_activos"].append({"user_id": OTHER, "ticker": "MSFT", "voto": "sube"})
    payload = me.get("/api/comunidad/notas?ticker=MSFT").get_json()
    names = {n["author"]["name"] for n in payload["items"]}
    assert names == {"Luis", members.ANONYMOUS}
    assert "Secreto" not in json.dumps(payload) and HIDDEN not in json.dumps(payload)
    assert next(n for n in payload["items"] if n["author"]["name"] == "Luis")["vote"] == "sube"


def test_members_lists_only_public_profiles_with_assets_and_votes(me, fake):
    fake.tables["perfiles_comunidad"] += [
        {"user_id": OTHER, "nombre": "Luis", "profesion": "Finanzas", "visible": True},
        {"user_id": HIDDEN, "nombre": "Secreto", "visible": False},
        {"user_id": ME["id"], "nombre": "Ana", "visible": True},
    ]
    fake.tables["activos_favoritos"].append({"user_id": OTHER, "ticker": "NVDA", "created_at": "x"})
    fake.tables["votos_activos"].append({"user_id": OTHER, "ticker": "AAPL", "voto": "baja"})
    items = me.get("/api/comunidad/miembros").get_json()["items"]
    assert [m["name"] for m in items] == ["Luis"]
    assert items[0]["assets"] == ["NVDA"] and items[0]["votes"] == {"AAPL": "baja"}
    assert items[0]["following"] is False and items[0]["connection"] is None


def test_follow_and_mutual_connection(me, fake):
    fake.tables["perfiles_comunidad"].append({"user_id": OTHER, "nombre": "Luis", "visible": True})
    items = me.post("/api/comunidad/relaciones", json={"target": OTHER, "kind": "seguir", "active": True}).get_json()["items"]
    assert items[0]["following"] is True

    items = me.post("/api/comunidad/relaciones", json={"target": OTHER, "kind": "conectar", "active": True}).get_json()["items"]
    assert items[0]["connection"] == "enviada"
    fake.tables["relaciones_comunidad"].append({"user_id": OTHER, "objetivo_id": ME["id"], "tipo": "conectar"})
    members.clear_cache()
    assert me.get("/api/comunidad/miembros").get_json()["items"][0]["connection"] == "conectados"
    social = me.get("/api/comunidad/perfil").get_json()["social"]
    assert social == {"following": 1, "followers": 0, "connections": 1}

    me.post("/api/comunidad/relaciones", json={"target": OTHER, "kind": "seguir", "active": False})
    assert me.get("/api/comunidad/miembros").get_json()["items"][0]["following"] is False


def test_cannot_follow_private_or_invalid_profiles(me, fake):
    fake.tables["perfiles_comunidad"].append({"user_id": HIDDEN, "nombre": "Secreto", "visible": False})
    assert me.post("/api/comunidad/relaciones", json={"target": HIDDEN, "kind": "seguir", "active": True}).status_code == 400
    assert me.post("/api/comunidad/relaciones", json={"target": "x),(user_id.eq.y", "kind": "seguir", "active": True}).status_code == 400
    assert me.post("/api/comunidad/relaciones", json={"target": ME["id"], "kind": "seguir", "active": True}).status_code == 400
    assert fake.tables["relaciones_comunidad"] == []


def test_activity_counts_votes_and_notes(me, fake):
    fake.tables["votos_activos"] += [{"user_id": ME["id"], "ticker": "AAPL", "voto": "sube"}, {"user_id": OTHER, "ticker": "AAPL", "voto": "sube"}]
    me.post("/api/comunidad/notas", json={"ticker": "AAPL", "tag": "Soporte clave"})
    activity = me.get("/api/comunidad/perfil").get_json()["activity"]
    assert activity == {"votes": 1, "notes": 1}


def test_social_api_requires_session_and_reports_missing_db(client, me, monkeypatch):
    with client.session_transaction() as session:
        session.clear()
    response = client.get("/api/comunidad/perfil")
    assert response.status_code == 401 and response.get_json()["mode"] == "local"

    def broken(*a, **k):
        raise db.DBError("InsForge respondió 404.")

    monkeypatch.setattr(db, "request", broken)
    members.clear_cache()
    with client.session_transaction() as session:
        session["user"] = ME
    for url in ("/api/comunidad/perfil", "/api/comunidad/miembros", "/api/comunidad/notas"):
        response = client.get(url)
        assert response.status_code == 503 and response.get_json()["mode"] == "local", url


def test_mi_perfil_page_has_community_profile_and_interaction(me, monkeypatch):
    monkeypatch.setattr("app.personas.views.store.list_favorites", lambda user_id: [])
    page = me.get("/app/mi-perfil/").get_data(as_text=True)
    for marker in ('id="mp-interaccion"', "Comparar posturas", "Seguir y conectar", "Notas y reacciones",
                   "Foto de perfil", "Profesión", "Biografía / enfoque", "Perfil visible en la comunidad",
                   "Votos emitidos", "Notas dejadas", "Perfil seleccionado", "data-c-dialog"):
        assert marker in page, marker
    for tag in members.QUICK_TAGS:
        assert tag in page
    data = json.loads(page.split('<script id="mi-perfil-comunidad" type="application/json">')[1].split("</script>")[0])
    assert data["urls"]["profile"] == "/api/comunidad/perfil"
    assert {"AAPL", "MSFT"} <= {a["ticker"] for a in data["assets"]}
