"""Activos favoritos: la API de base de datos de InsForge está simulada."""
import pytest

from app import create_app
from app.favoritos import store
from app.favoritos.store import StoreError
from config import TestingConfig

USER = {"id": "u1", "email": "ana@example.com", "name": "Ana"}


class FakeDB:
    """Imita /api/database/records/activos_favoritos."""

    def __init__(self):
        self.rows = []
        self.calls = []

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append((method, params, json, headers))
        db = self

        class Resp:
            status_code = 200

            def json(self):
                if method == "GET":
                    uid = params["user_id"].removeprefix("eq.")
                    return [r for r in db.rows if r["user_id"] == uid]
                return None

        if method == "POST":
            self.rows += [{**r, "created_at": "2026-10-15T00:00:00Z"} for r in json]
        if method == "DELETE":
            uid, t = params["user_id"][3:], params["ticker"][3:]
            self.rows = [r for r in self.rows if not (r["user_id"] == uid and r["ticker"] == t)]
        return Resp()


@pytest.fixture()
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(store.requests, "request", fake)
    monkeypatch.setattr("app.favoritos.views.market_data.get_display_name", lambda t: f"Nombre {t}")
    store._cache.clear()
    return fake


@pytest.fixture()
def logged(db):
    client = create_app(TestingConfig).test_client()
    with client.session_transaction() as s:
        s["user"] = USER
    return client


def test_add_list_remove_roundtrip(logged, db):
    assert logged.post("/app/favoritos/agregar", data={"ticker": "aapl"}).status_code == 302
    logged.post("/app/favoritos/agregar", data={"ticker": "AAPL"})  # duplicado
    logged.post("/app/favoritos/agregar", data={"ticker": "BTC-USD"})
    assert [r["ticker"] for r in db.rows] == ["AAPL", "BTC-USD"]
    assert db.rows[0]["user_id"] == "u1" and db.rows[0]["nombre"] == "Nombre AAPL"

    page = logged.get("/app/favoritos/").get_data(as_text=True)
    assert "AAPL" in page and "BTC-USD" in page and "Nombre AAPL" in page

    logged.post("/app/favoritos/quitar", data={"ticker": "AAPL"})
    assert [r["ticker"] for r in db.rows] == ["BTC-USD"]


def test_every_request_uses_api_key_and_filters_by_user(logged, db):
    logged.get("/app/favoritos/")
    method, params, _, headers = db.calls[0]
    assert params["user_id"] == "eq.u1" and headers["Authorization"] == "Bearer api-test"


def test_users_only_see_their_own_assets(logged, db):
    db.rows.append({"user_id": "otro", "ticker": "TSLA", "nombre": None, "created_at": "2026-10-15"})
    assert "TSLA" not in logged.get("/app/favoritos/").get_data(as_text=True)


def test_sidebar_shows_favorites_on_app_pages(logged, db):
    logged.post("/app/favoritos/agregar", data={"ticker": "NVDA"})
    page = logged.get("/app/pyportfolio-opt/").get_data(as_text=True)
    assert 'aria-label="Mis activos"' in page
    assert 'href="/app/graficador/?ticker=NVDA"' in page


def test_invalid_ticker_is_rejected(logged, db):
    logged.post("/app/favoritos/agregar", data={"ticker": "<script>"})
    assert db.rows == []


def test_anonymous_cannot_write(db):
    client = create_app(TestingConfig).test_client()
    response = client.post("/app/favoritos/agregar", data={"ticker": "AAPL"})
    assert response.status_code == 302 and "/ingresar" in response.headers["Location"]
    assert db.rows == []


def test_database_failure_does_not_break_pages(logged, monkeypatch):
    def boom(*a, **k):
        raise store.requests.ConnectionError()

    monkeypatch.setattr(store.requests, "request", boom)
    assert logged.get("/app/pyportfolio-opt/").status_code == 200  # sidebar vacío
    page = logged.get("/app/favoritos/").get_data(as_text=True)
    assert "No se pudo conectar" in page


def test_max_favorites(logged, db, monkeypatch):
    monkeypatch.setattr(store, "MAX_FAVORITES", 1)
    logged.post("/app/favoritos/agregar", data={"ticker": "AAPL"})
    logged.post("/app/favoritos/agregar", data={"ticker": "MSFT"})
    assert [r["ticker"] for r in db.rows] == ["AAPL"]
