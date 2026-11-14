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


def test_page_shows_only_saved_assets_with_universo_layout(logged, db):
    db.rows += [
        {"user_id": "u1", "ticker": "AAPL", "nombre": "Apple Inc.", "created_at": "2026-10-15T00:00:00Z"},
        {"user_id": "otro", "ticker": "TSLA", "nombre": "Tesla", "created_at": "2026-10-15T00:00:00Z"},
    ]
    html = logged.get("/app/favoritos/").get_data(as_text=True)
    assert "Mis activos · MoaiInvest" in html
    assert 'data-quote-url="/api/quote/__T__"' in html
    assert 'data-ticker="AAPL"' in html and "Apple Inc." in html
    assert "/app/graficador/?ticker=AAPL" in html
    assert "/app/quant-stats/fundamentales?ticker=AAPL" in html
    assert "favoritos.js" in html and "favoritos.css" in html
    assert "TSLA" not in html


def test_empty_list_shows_no_sample_data(logged, db):
    html = logged.get("/app/favoritos/").get_data(as_text=True)
    assert "Aún no tienes activos guardados" in html
    assert 'id="activos-table"' not in html and "data-ticker=" not in html


def test_anonymous_sees_no_assets_and_no_network(db):
    client = create_app(TestingConfig).test_client()
    html = client.get("/app/favoritos/").get_data(as_text=True)
    assert "Inicia sesión" in html and "data-ticker=" not in html
    assert db.calls == []


def test_old_universo_url_redirects_permanently(client):
    response = client.get("/app/universo/")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("/app/favoritos/")


def test_sidebar_has_single_mis_activos_entry():
    from app.core.navigation import APPS

    assert [a.name for a in APPS].count("Mis activos") == 1
    assert all("universo" not in a.slug for a in APPS)
