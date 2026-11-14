"""¿Qué piensas tú?: catálogo, votos (con cambio de opinión) y consenso de la comunidad."""
from datetime import datetime, timezone

import pytest

from app import create_app
from app.alertas import service
from app.comunidad import votes
from app.core import catalog
from app.core.market_data import Quote
from app.core.watchlists import WATCHLISTS
from app.favoritos import search
from app.favoritos import store as favorites_store
from config import TestingConfig
from tests.fakedb import FakeDB

USER = {"id": "u1", "email": "ana@example.com", "name": "Ana"}


@pytest.fixture()
def db(monkeypatch):
    fake = FakeDB(unique={"votos_activos": ("user_id", "ticker", "ronda")})
    monkeypatch.setattr("requests.request", fake)
    monkeypatch.setattr(service.market_data, "get_quote", lambda t: Quote(t, t, 230.0, 227.0, 3.0, 1.32, "USD") if t == "AAPL" else None)
    monkeypatch.setattr(
        search, "_remote", lambda q: [search.SymbolMatch("PLTR", "Palantir Technologies Inc.", "Acción", "NASDAQ")] if q.upper().startswith("PLTR") or q.lower() == "palantir" else []
    )
    favorites_store._cache.clear()
    search._cache.clear()
    return fake


@pytest.fixture()
def logged(db):
    client = create_app(TestingConfig).test_client()
    with client.session_transaction() as s:
        s["user"] = USER
    return client


def items_by_ticker(response):
    return {i["ticker"]: i for i in response.get_json()["items"]}


def test_catalog_covers_every_watchlist_symbol():
    missing = {s.ticker for w in WATCHLISTS for s in w.symbols} - set(catalog.BY_TICKER)
    assert missing == set()


def test_grid_lists_the_whole_catalog_with_the_users_assets_first(logged, db):
    db.rows("activos_favoritos").append({"user_id": "u1", "ticker": "PLTR", "nombre": "Palantir", "created_at": "2026-11-01"})
    data = logged.get("/api/comunidad/activos").get_json()
    tickers = [i["ticker"] for i in data["items"]]
    assert tickers[0] == "PLTR" and set(catalog.BY_TICKER) <= set(tickers)
    aapl = items_by_ticker(logged.get("/api/comunidad/activos"))["AAPL"]
    assert (aapl["nombre"], aapl["categoria_nombre"], aapl["precio"], aapl["variacion"]) == ("Apple Inc.", "Tecnología", 230.0, 1.32)
    assert aapl["total"] == 0 and aapl["mi_voto"] is None and aapl["pct_sube"] is None
    assert data["ronda"] == votes.current_round()


def test_voting_records_the_vote_and_returns_the_consensus(logged, db):
    ronda = votes.current_round()
    db.rows("votos_activos").extend(
        [{"user_id": f"u{i}", "ticker": "NVDA", "voto": "up", "ronda": ronda} for i in range(2, 9)]
        + [{"user_id": "u9", "ticker": "NVDA", "voto": "down", "ronda": ronda}, {"user_id": "u10", "ticker": "NVDA", "voto": "down", "ronda": "2020-W01"}]
    )
    response = logged.post("/api/comunidad/votos", json={"ticker": "NVDA", "voto": "down"})
    assert response.status_code == 201 and response.get_json()["resultado"] == "nuevo"
    item = response.get_json()["item"]
    # 7 sube + 2 baja (la de 2020 no cuenta) → 78 % / 22 %
    assert (item["sube"], item["baja"], item["total"], item["pct_sube"], item["pct_baja"], item["mi_voto"]) == (7, 2, 9, 78, 22, "down")


def test_users_can_change_their_vote_but_never_vote_twice(logged, db):
    assert logged.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "up"}).status_code == 201
    changed = logged.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "down"})
    assert changed.status_code == 200 and changed.get_json()["resultado"] == "cambiado"
    same = logged.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "down"})
    assert same.get_json()["resultado"] == "igual"
    mine = [v for v in db.rows("votos_activos") if v["user_id"] == "u1"]
    assert len(mine) == 1 and mine[0]["voto"] == "down"
    item = items_by_ticker(logged.get("/api/comunidad/activos"))["AAPL"]
    assert (item["sube"], item["baja"], item["mi_voto"]) == (0, 1, "down")


def test_a_concurrent_insert_becomes_a_change(logged, db, monkeypatch):
    """Si otra petición crea el voto entre la lectura y el POST (409), se cambia."""
    original = db.__call__
    raced = {"done": False}

    def racing(method, url, params=None, json=None, **k):
        if method == "POST" and url.endswith("votos_activos") and not raced["done"]:
            raced["done"] = True
            db.rows("votos_activos").append({**json[0], "voto": "up"})
        return original(method, url, params=params, json=json, **k)

    monkeypatch.setattr("requests.request", racing)
    response = logged.post("/api/comunidad/votos", json={"ticker": "TSLA", "voto": "down"})
    assert response.get_json()["resultado"] == "cambiado"
    assert [v["voto"] for v in db.rows("votos_activos")] == ["down"]


def test_assets_outside_the_catalog_can_be_found_and_voted(logged, db):
    data = items_by_ticker(logged.get("/api/comunidad/activos?extra=PLTR,FAKE1,<script>"))
    assert "PLTR" in data and data["PLTR"]["nombre"] == "Palantir Technologies Inc." and data["PLTR"]["categoria"] == "otros"
    assert "FAKE1" not in data and "<SCRIPT>" not in data
    assert logged.post("/api/comunidad/votos", json={"ticker": "PLTR", "voto": "up"}).status_code == 201
    assert logged.post("/api/comunidad/votos", json={"ticker": "FAKE1", "voto": "up"}).status_code == 400


@pytest.mark.parametrize("body", [{"ticker": "AAPL", "voto": "moon"}, {"ticker": "<x>", "voto": "up"}, {}])
def test_invalid_votes_are_rejected(logged, db, body):
    assert logged.post("/api/comunidad/votos", json=body).status_code == 400
    assert db.rows("votos_activos") == []


def test_round_is_the_iso_week_and_closes_next_monday():
    friday = datetime(2026, 11, 13, 18, tzinfo=timezone.utc)
    assert votes.current_round(friday) == "2026-W46"
    assert votes.round_closes_at(friday) == datetime(2026, 11, 16, tzinfo=timezone.utc)


def test_api_requires_a_session(db):
    anon = create_app(TestingConfig).test_client()
    assert anon.get("/api/comunidad/activos").status_code == 401
    assert anon.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "up"}).status_code == 401


def test_page_header_search_and_category_filters(logged, db):
    page = logged.get("/app/que-piensas-tu/").get_data(as_text=True)
    assert "¿Qué piensas <span class=\"accent\">tú</span>?" in page
    assert "Vota sobre la tendencia de los activos y descubre el sentimiento de la comunidad de MOAINVEST." in page
    assert 'id="vote-q"' in page and 'type="search"' in page
    for label in ("Todos", "Mis activos", "Índices", "Tecnología", "Cripto"):
        assert f">{label}</button>" in page


def test_sidebar_lists_the_two_new_apps_below_my_assets(logged, db):
    page = logged.get("/app/que-piensas-tu/").get_data(as_text=True)
    sidebar = page.split('<aside class="sidebar"', 1)[1].split("</aside>", 1)[0]
    positions = [sidebar.index(f'href="{href}"') for href in ("/app/favoritos/", "/app/noticias/", "/app/que-piensas-tu/")]
    assert positions == sorted(positions)
    assert "ui-icon--newspaper" in sidebar and "ui-icon--message-circle" in sidebar
    assert sidebar.count('aria-current="page"') == 1 and 'href="/app/que-piensas-tu/" title="¿Qué piensas tú?" aria-current="page"' in sidebar


# ---- Tabla de votos aún sin crear en InsForge ----

@pytest.fixture()
def no_votes_table(db):
    db.missing.add("votos_activos")
    return db


def test_without_the_votes_table_the_grid_loads_with_zero_votes(logged, no_votes_table):
    response = logged.get("/api/comunidad/activos")
    assert response.status_code == 200
    data = response.get_json()
    assert data["votos_disponibles"] is False
    assert set(catalog.BY_TICKER) <= {i["ticker"] for i in data["items"]}
    assert all(i["total"] == 0 and i["mi_voto"] is None for i in data["items"])


def test_without_the_votes_table_a_vote_is_validated_and_marked_pending(logged, no_votes_table):
    response = logged.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "up"})
    assert response.status_code == 503
    body = response.get_json()
    assert (body["codigo"], body["tabla"], body["ticker"], body["voto"]) == ("tabla_pendiente", "votos_activos", "AAPL", "up")
    assert body["ronda"] == votes.current_round()
    # Los votos inválidos siguen siendo 400 (el navegador no los guarda).
    assert logged.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "moon"}).status_code == 400


def test_other_database_errors_are_still_errors(logged, db, monkeypatch):
    def boom(*a, **k):
        raise __import__("requests").ConnectionError()

    monkeypatch.setattr("requests.request", boom)
    response = logged.get("/api/comunidad/activos")
    assert response.status_code == 503 and "codigo" not in response.get_json()


def test_the_page_includes_the_neutral_local_votes_notice(logged, db):
    page = logged.get("/app/que-piensas-tu/").get_data(as_text=True)
    assert 'id="vote-notice" hidden' in page and "se guardan en este navegador" in page
