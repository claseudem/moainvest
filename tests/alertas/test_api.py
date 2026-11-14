"""API de alertas y su interfaz: InsForge, Yahoo Finance y noticias simulados."""
import uuid

import pytest

from app import create_app
from app.alertas import service, store
from app.core import news
from app.core.market_data import Quote
from config import TestingConfig

USER = {"id": "u1", "email": "ana@example.com", "name": "Ana"}
UNIQUE = ("user_id", "ticker", "sesion", "direccion", "nivel")


class FakeDB:
    """Imita /api/database/records/<tabla> con filtros eq./in., order, limit y UNIQUE."""

    def __init__(self):
        # activos_favoritos: el sidebar de las páginas /app/ también la consulta.
        self.tables = {"alertas": [], "alertas_preferencias": [], "activos_favoritos": [], "suscripciones_noticias": []}
        self.calls = []

    @staticmethod
    def _match(row, params):
        for key, cond in (params or {}).items():
            if key in ("select", "order", "limit"):
                continue
            op, _, value = cond.partition(".")
            current = row.get(key)
            if op == "eq":
                if str(current).lower() != value.lower():
                    return False
            elif op == "in":
                options = [v.strip('"') for v in value.strip("()").split(",")]
                if str(current) not in options:
                    return False
        return True

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        table = url.rsplit("/", 1)[1]
        rows = self.tables[table]
        self.calls.append((method, table, params, json, headers))
        status, body = 200, None
        if method == "GET":
            body = [r for r in rows if self._match(r, params)]
            if params.get("order") == "created_at.desc":
                body = list(reversed(body))
        elif method == "POST":
            for new in json:
                if table == "alertas":
                    key = tuple(new[k] for k in UNIQUE)
                    if any(tuple(r.get(k) for k in UNIQUE) == key for r in rows):
                        status = 409
                        continue
                    new = {"id": str(uuid.uuid4()), "leida": False, "created_at": f"2026-11-14T10:{len(rows):02d}:00Z", **new}
                rows.append(new)
        elif method == "PATCH":
            for r in rows:
                if self._match(r, params):
                    r.update(json)

        class Resp:
            status_code = status

            def json(self):
                return body

        return Resp()


QUOTES = {
    "DELL": Quote("DELL", "Dell Technologies", 344.53, 379.45, -34.92, -9.2, "USD"),
    "BTC-USD": Quote("BTC-USD", "Bitcoin", 95000.0, 99000.0, -4000.0, -4.04, "USD"),
    "NTDOY": Quote("NTDOY", "Nintendo", 22.0, 20.0, 2.0, 10.0, "USD"),
}


@pytest.fixture()
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(store.requests, "request", fake)
    monkeypatch.setattr(
        service.market_data, "get_quote", lambda t: QUOTES.get(t) or Quote(t, t, 10.0, 10.0, 0.0, 0.0, "USD")
    )
    headline = news.Headline("n1", "Dell cae tras un trimestre por debajo de lo esperado", "Reuters", "https://example.com/dell", 1_794_596_612, ("DELL",))
    monkeypatch.setattr(news, "best_headline", lambda ticker, name=None, **k: headline if ticker == "DELL" else None)
    monkeypatch.setattr(news, "feed", lambda tickers, **k: [(headline, ["DELL"])])
    service._last_scan.clear()
    return fake


@pytest.fixture()
def logged(db):
    client = create_app(TestingConfig).test_client()
    with client.session_transaction() as s:
        s["user"] = USER
    return client


def test_api_requires_a_session(db):
    client = create_app(TestingConfig).test_client()
    assert client.get("/api/alertas").status_code == 401
    assert client.put("/api/alertas/preferencias", json={"umbral": 3}).status_code == 401


def test_first_request_scans_and_stores_hybrid_alerts(logged, db):
    data = logged.get("/api/alertas").get_json()
    # Umbral por defecto ±5 %: DELL (−9,2) y NTDOY (+10, nivel 2); BTC (−4) no llega.
    assert sorted(i["ticker"] for i in data["items"]) == ["DELL", "NTDOY"]
    assert data["no_leidas"] == 2
    dell = next(i for i in data["items"] if i["ticker"] == "DELL")
    assert dell["nombre"] == "Dell" and dell["direccion"] == "down" and dell["variacion"] == -9.2
    assert dell["noticia_titulo"].startswith("Dell cae") and dell["noticia_fuente"] == "Reuters"
    assert dell["watchlists"] == ["consumer-electronics"] and dell["sesion"] == "379.45"
    ntdoy = next(i for i in data["items"] if i["ticker"] == "NTDOY")
    assert ntdoy["nivel"] == 2 and ntdoy["noticia_titulo"] is None
    assert data["preferencias"]["umbral"] == 5 and data["preferencias"]["guardadas"] is False


def test_rescanning_does_not_duplicate_alerts(logged, db):
    logged.get("/api/alertas")
    service._last_scan.clear()
    logged.get("/api/alertas")
    assert len(db.tables["alertas"]) == 2


def test_scans_are_throttled_per_user(logged, db):
    logged.get("/api/alertas")
    db.tables["alertas"].clear()
    logged.get("/api/alertas")  # dentro de SCAN_INTERVAL: no vuelve a evaluar
    assert db.tables["alertas"] == []


def test_lower_threshold_and_muting_change_what_triggers(logged, db):
    response = logged.put("/api/alertas/preferencias", json={"umbral": 3, "silenciadas": ["consumer-electronics"]})
    assert response.status_code == 200
    assert db.tables["alertas_preferencias"] == [{"user_id": "u1", "umbral": 3, "silenciadas": ["consumer-electronics"]}]
    tickers = sorted(i["ticker"] for i in logged.get("/api/alertas").get_json()["items"])
    assert tickers == ["BTC-USD", "NTDOY"]  # DELL silenciada; BTC ya supera ±3 %

    logged.put("/api/alertas/preferencias", json={"silenciadas": []})  # el umbral se conserva
    assert db.tables["alertas_preferencias"][0]["umbral"] == 3


def test_invalid_preferences_are_rejected(logged, db):
    assert logged.put("/api/alertas/preferencias", json={"umbral": 4}).status_code == 400
    assert logged.put("/api/alertas/preferencias", json={"silenciadas": ["no-existe"]}).status_code == 400
    assert db.tables["alertas_preferencias"] == []


def test_mark_one_or_all_as_read(logged, db):
    items = logged.get("/api/alertas").get_json()["items"]
    first = items[0]["id"]
    assert logged.post("/api/alertas/leidas", json={"ids": [first]}).status_code == 200
    unread = {r["id"] for r in db.tables["alertas"] if not r["leida"]}
    assert first not in unread and len(unread) == 1
    logged.post("/api/alertas/leidas", json={})
    assert all(r["leida"] for r in db.tables["alertas"])
    assert logged.post("/api/alertas/leidas", json={"ids": ["1; drop"]}).status_code == 400


def test_every_query_filters_by_the_session_user(logged, db):
    db.tables["alertas"].append({"id": str(uuid.uuid4()), "user_id": "otro", "ticker": "AAPL", "leida": False})
    items = logged.get("/api/alertas").get_json()["items"]
    assert "AAPL" not in [i["ticker"] for i in items]
    for method, _, params, _, headers in db.calls:
        assert headers["Authorization"] == "Bearer api-test"
        assert params is None or params.get("user_id") == "eq.u1"


def test_news_tab_needs_a_subscription_and_tags_the_assets_move(logged, db):
    assert logged.get("/api/alertas/noticias").get_json()["suscrito"] is False
    db.tables["suscripciones_noticias"].append(
        {"user_id": "u1", "activa": True, "via_app": True, "via_email": False, "email": None, "alcance": "favoritos"}
    )
    db.tables["activos_favoritos"].append({"user_id": "u1", "ticker": "DELL", "nombre": "Dell"})
    item = logged.get("/api/alertas/noticias").get_json()["items"][0]
    assert item["title"].startswith("Dell cae") and item["sentimiento"] == "bajista"
    assert item["activos"] == [{"ticker": "DELL", "nombre": "Dell", "variacion": -9.2}]


def test_database_down_returns_503_and_pages_still_render(logged, monkeypatch):
    def boom(*a, **k):
        raise store.requests.ConnectionError()

    monkeypatch.setattr(store.requests, "request", boom)
    assert logged.get("/api/alertas").status_code == 503
    assert logged.get("/app/noticias/").status_code == 200


def test_bell_renders_only_with_a_session(logged, db):
    page = logged.get("/app/noticias/").get_data(as_text=True)
    topbar = page.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]
    assert 'id="notif-btn"' in topbar and 'aria-controls="notif-panel"' in topbar
    assert 'role="tab"' in topbar and "Movimientos" in topbar and "Noticias" in topbar
    # Las watchlists se silencian desde el diálogo de la campana (Informes ya no existe).
    assert 'id="notif-settings"' in topbar and 'value="10"' in topbar and topbar.count('name="activas"') == 3
    assert "/app/alertas/static/js/alertas.js" in page

    anon = create_app(TestingConfig).test_client().get("/app/noticias/").get_data(as_text=True)
    assert 'id="notif-btn"' not in anon
