"""Mis activos: autocompletado y validación al agregar (noticias y votos tienen sus propios tests)."""
import pytest

from app import create_app
from app.favoritos import search, store
from config import TestingConfig

USER = {"id": "u1", "email": "ana@example.com", "name": "Ana"}


class FakeDB:
    """Imita /api/database/records/<tabla> con filtros eq./in. y UNIQUE de votos."""

    def __init__(self):
        self.tables = {"activos_favoritos": [], "votos_activos": [], "alertas": [], "alertas_preferencias": []}

    @staticmethod
    def _match(row, params):
        for key, cond in (params or {}).items():
            if key in ("select", "order", "limit"):
                continue
            op, _, value = cond.partition(".")
            if op == "eq" and str(row.get(key)) != value:
                return False
            if op == "in" and str(row.get(key)) not in [v.strip('"') for v in value.strip("()").split(",")]:
                return False
        return True

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        table = url.rsplit("/", 1)[1]
        rows = self.tables[table]
        status, body = 200, None
        if method == "GET":
            body = [r for r in rows if self._match(r, params)]
        elif method == "POST":
            for new in json:
                if table == "votos_activos" and any(
                    (r["user_id"], r["ticker"], r["ronda"]) == (new["user_id"], new["ticker"], new["ronda"]) for r in rows
                ):
                    status = 409
                    continue
                rows.append({"created_at": "2026-11-14T10:00:00Z", **new})
        elif method == "DELETE":
            self.tables[table] = [r for r in rows if not self._match(r, params)]

        class Resp:
            status_code = status

            def json(self):
                return body

        return Resp()


@pytest.fixture()
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(store.requests, "request", fake)
    monkeypatch.setattr(search, "_remote", lambda q: [search.SymbolMatch("AAPL", "Apple Inc.", "Acción", "NASDAQ")] if q.lower() in ("appl", "apple") else [])
    monkeypatch.setattr("app.favoritos.views.market_data.get_display_name", lambda t: t if t in ("APPL", "^GSPC") else f"Nombre {t}")
    store._cache.clear()
    search._cache.clear()
    return fake


def client_for(user=USER):
    client = create_app(TestingConfig).test_client()
    if user:
        with client.session_transaction() as s:
            s["user"] = user
    return client


@pytest.fixture()
def logged(db):
    return client_for()


# ---- Autocompletado ----

def test_search_without_query_returns_popular_assets(logged, db):
    data = logged.get("/api/favoritos/buscar").get_json()
    assert data["populares"] is True
    assert [i["ticker"] for i in data["items"]][:5] == ["AAPL", "BTC-USD", "^GSPC", "NVDA", "TSLA"]


def test_search_fixes_typos_and_matches_names(logged, db):
    assert logged.get("/api/favoritos/buscar?q=APPL").get_json()["items"][0]["ticker"] == "AAPL"
    # Sin Yahoo, la lista local busca por nombre: "tesla" → TSLA.
    assert [i["ticker"] for i in logged.get("/api/favoritos/buscar?q=tesla").get_json()["items"]] == ["TSLA"]


def test_search_flags_assets_already_in_the_list(logged, db):
    db.tables["activos_favoritos"].append({"user_id": "u1", "ticker": "AAPL", "nombre": "Apple Inc."})
    items = logged.get("/api/favoritos/buscar").get_json()["items"]
    assert next(i for i in items if i["ticker"] == "AAPL")["en_lista"] is True


def test_adding_from_the_dropdown_keeps_the_full_name(logged, db):
    logged.post("/app/favoritos/agregar", data={"ticker": "nvda", "nombre": "NVIDIA Corporation"})
    assert db.tables["activos_favoritos"][0]["nombre"] == "NVIDIA Corporation"


def test_typo_is_rejected_with_a_suggestion(logged, db):
    response = logged.post("/app/favoritos/agregar", data={"ticker": "APPL"}, follow_redirects=True)
    assert db.tables["activos_favoritos"] == []
    assert "No encontramos «APPL»" in response.get_data(as_text=True)
    assert "¿Quisiste decir AAPL?" in response.get_data(as_text=True)


def test_tickers_without_name_but_found_by_search_are_accepted(logged, db):
    logged.post("/app/favoritos/agregar", data={"ticker": "^GSPC"})
    assert db.tables["activos_favoritos"][0]["nombre"] == "S&P 500"


# ---- Seguridad y página ----

def test_api_requires_a_session(db):
    assert client_for(None).get("/api/favoritos/buscar").status_code == 401


def test_page_keeps_search_and_list_and_links_to_the_new_pages(logged, db):
    page = logged.get("/app/favoritos/").get_data(as_text=True)
    assert page.index('id="fav-add-title"') < page.index('id="fav-list-title"')
    assert 'role="combobox"' in page and 'aria-controls="fav-suggest"' in page
    assert 'href="/app/noticias/"' in page and 'href="/app/que-piensas-tu/"' in page
    assert "fav-news" not in page and "fav-vote" not in page
    assert "/app/favoritos/static/js/favoritos.js" in page and "/app/favoritos/static/css/favoritos.css" in page
