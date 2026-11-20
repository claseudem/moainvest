"""COMUNIDAD (``/app/personas/``): noticias de activos y votos "Sube" / "Baja"."""
import json
import re
from pathlib import Path

import pytest

from app.core.watchlists import WATCHLISTS
from app.personas import news, votes

JS = Path(__file__).resolve().parents[2] / "app" / "personas" / "static" / "personas.js"
USER = {"id": "u1", "email": "ana@example.com", "name": "Ana"}


def _payload(page: str) -> dict:
    match = re.search(r'<script id="comunidad-data" type="application/json">(.*?)</script>', page, re.S)
    assert match, "falta el JSON de la comunidad"
    return json.loads(match.group(1))


@pytest.fixture(autouse=True)
def no_favorites(monkeypatch):
    monkeypatch.setattr("app.personas.views.store.list_favorites", lambda user_id: [])


class FakeVotesDB:
    """Imita /api/database/records/votos_activos."""

    def __init__(self):
        self.rows = []

    def __call__(self, method, *, params=None, json=None, prefer=None):
        if method == "GET":
            return list(self.rows)
        if method == "DELETE":
            uid, ticker = params["user_id"].removeprefix("eq."), params["ticker"].removeprefix("eq.")
            self.rows = [r for r in self.rows if not (r["user_id"] == uid and r["ticker"] == ticker)]
        if method == "POST":
            self.rows.extend(json)
        return None


@pytest.fixture
def db(monkeypatch):
    fake = FakeVotesDB()
    monkeypatch.setattr(votes, "_request", fake)
    votes._cache.clear()
    return fake


@pytest.fixture
def signed_in(client):
    with client.session_transaction() as session:
        session["user"] = USER
    return client


def test_page_is_the_community_view(client):
    response = client.get("/app/personas/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<title>Comunidad · MoaiInvest</title>" in page
    assert 'id="noticias"' in page
    assert 'id="sentimiento"' in page
    assert "data-votes-sort" in page
    assert 'id="directorio"' not in page


def test_sidebar_says_comunidad(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    assert 'class="sidebar__app-name">Comunidad</span>' in page
    assert 'class="sidebar__app-name">Personas</span>' not in page
    assert 'class="sidebar__app-name">Mi perfil</span>' in page


def test_assets_include_watchlists_and_my_assets_first(signed_in, monkeypatch):
    monkeypatch.setattr(
        "app.personas.views.store.list_favorites", lambda user_id: [{"ticker": "NVDA", "nombre": "NVIDIA"}]
    )
    assets = _payload(signed_in.get("/app/personas/").get_data(as_text=True))["assets"]
    tickers = [a["ticker"] for a in assets]
    assert tickers[0] == "NVDA" and assets[0]["mine"] is True
    expected = {s.ticker for w in WATCHLISTS for s in w.symbols}
    assert expected <= set(tickers)
    assert len(tickers) == len(set(tickers)), "un activo repetido en varias watchlists aparece una vez"


def test_legacy_urls_redirect_to_the_community(client):
    assert client.get("/personas/").headers["Location"].endswith("/app/personas/")
    response = client.get("/app/comunidad/")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("/app/personas/")


def test_news_are_merged_sorted_and_trend_tagged(client, monkeypatch):
    live = {
        "AAPL": [
            {"id": "n1", "title": "Apple shares jump after earnings beat", "summary": "Resumen", "source": "Reuters", "published": "2026-11-18T10:00:00+00:00", "url": "https://x/1", "related": ["AAPL"]},
            {"id": "n2", "title": "Big Tech stocks fall", "summary": None, "source": "WSJ", "published": "2026-11-19T10:00:00+00:00", "url": "https://x/2", "related": ["MSFT", "AAPL", "NVDA"]},
        ],
        "MSFT": [
            {"id": "n2", "title": "Big Tech stocks fall", "summary": None, "source": "WSJ", "published": "2026-11-19T10:00:00+00:00", "url": "https://x/2", "related": ["MSFT", "AAPL", "NVDA"]},
        ],
    }
    monkeypatch.setattr(news, "_fetch_live", lambda t: live.get(t, []))
    news._cache.clear()
    data = client.get("/api/comunidad/noticias?tickers=AAPL,MSFT").get_json()
    assert data["demo"] is False
    assert [n["id"] for n in data["items"]] == ["n2", "n1"]
    assert data["items"][0]["tickers"] == ["AAPL", "MSFT"]
    assert data["items"][0]["trend"] == "bajar"
    assert data["items"][1]["trend"] == "subir"
    assert all("relevance" not in n for n in data["items"])


def test_news_fall_back_to_marked_demo_data(client, monkeypatch):
    monkeypatch.setattr(news, "_fetch_live", lambda t: [])
    news._cache.clear()
    data = client.get("/api/comunidad/noticias?tickers=AAPL,BTC-USD").get_json()
    assert data["demo"] is True
    assert data["items"] and all(n["demo"] for n in data["items"])
    assert all(n["trend"] in ("subir", "bajar", "medio") for n in data["items"])
    assert {n["ticker"] for n in data["items"]} == {"AAPL", "BTC-USD"}


def test_news_ignore_invalid_tickers(client, monkeypatch):
    seen = []
    monkeypatch.setattr(news, "_fetch_live", lambda t: seen.append(t) or [])
    news._cache.clear()
    client.get("/api/comunidad/noticias?tickers=AAPL,<script>,msft")
    assert sorted(seen) == ["AAPL", "MSFT"]


def test_vote_change_and_withdraw(signed_in, db):
    data = signed_in.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "sube"}).get_json()
    assert data["counts"]["AAPL"] == {"sube": 1, "baja": 0} and data["mine"] == {"AAPL": "sube"}

    data = signed_in.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "baja"}).get_json()
    assert data["counts"]["AAPL"] == {"sube": 0, "baja": 1}, "cambiar el voto no lo duplica"

    data = signed_in.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": None}).get_json()
    assert "AAPL" not in data["counts"] and data["mine"] == {}


def test_tally_counts_everyone_but_mine_is_only_mine(signed_in, db):
    db.rows = [
        {"user_id": "otro", "ticker": "MSFT", "voto": "sube"},
        {"user_id": "otro2", "ticker": "MSFT", "voto": "baja"},
        {"user_id": "u1", "ticker": "MSFT", "voto": "sube"},
    ]
    data = signed_in.get("/api/comunidad/votos").get_json()
    assert data["counts"]["MSFT"] == {"sube": 2, "baja": 1}
    assert data["mine"] == {"MSFT": "sube"}
    assert "otro" not in json.dumps(data), "no se exponen los ids de otros usuarios"


def test_invalid_vote_is_rejected(signed_in, db):
    assert signed_in.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "quizas"}).status_code == 400
    assert signed_in.post("/api/comunidad/votos", json={"ticker": "<x>", "voto": "sube"}).status_code == 400
    assert db.rows == []


def test_voting_requires_a_session(client, db):
    response = client.post("/api/comunidad/votos", json={"ticker": "AAPL", "voto": "sube"})
    assert response.status_code == 401
    assert response.get_json()["mode"] == "local"


def test_store_failure_switches_to_local_mode(signed_in, monkeypatch):
    def broken(*a, **k):
        raise votes.VoteStoreError("InsForge respondió 404.")

    monkeypatch.setattr(votes, "_request", broken)
    votes._cache.clear()
    response = signed_in.get("/api/comunidad/votos")
    assert response.status_code == 503
    assert response.get_json()["mode"] == "local"


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Apple stock jumps after earnings beat", "subir"),
        ("Sony eleva su previsión anual", "subir"),
        ("Dow plunges 1,100 points", "bajar"),
        ("El bitcoin cae tras la decisión de la Fed", "bajar"),
        ("Trading Day: World's biggest IPO?", "medio"),
    ],
)
def test_trend_of_headlines(title, expected):
    assert news.trend_of(title) == expected


def test_news_block_has_more_and_less_buttons_and_no_relevance(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    assert "Ver más noticias" in page and "Ver menos noticias" in page
    assert "Relevancia" not in page
    source = JS.read_text(encoding="utf-8")
    assert "Tendencia: " in source and "relevance" not in source


def test_js_never_writes_html_from_data():
    for path in (JS, JS.with_name("community-shared.js"), JS.parents[2] / "mi_perfil" / "static" / "comunidad.js"):
        source = path.read_text(encoding="utf-8")
        assert ".innerHTML" not in source, path.name
    assert "localStorage" in JS.with_name("community-shared.js").read_text(encoding="utf-8")
