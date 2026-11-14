"""Noticias: feed por filtro, sentimiento, suscripción, resumen por correo y campana."""
from datetime import datetime, timezone

import pytest

from app import create_app
from app.alertas import service
from app.core import news
from app.core.market_data import Quote
from app.favoritos import store as favorites_store
from app.noticias import digest, feed, sentiment
from config import TestingConfig
from tests.fakedb import FakeDB

USER = {"id": "u1", "email": "ana@example.com", "name": "Ana"}
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)

HEADLINES = {
    "AAPL": news.Headline("n1", "Apple shares surge to record high", "Reuters", "https://example.com/1", int(NOW.timestamp()) - 3600, ("AAPL",)),
    "BTC-USD": news.Headline("n2", "Bitcoin tumbles as crypto selloff deepens", "CoinDesk", "https://example.com/2", int(NOW.timestamp()) - 7200, ("BTC-USD",)),
    "^GSPC": news.Headline("n3", "What to watch in markets this week", "Barron's", None, int(NOW.timestamp()) - 90000, ("^GSPC",)),
}


@pytest.fixture()
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr("requests.request", fake)
    requested = []

    def fake_feed(tickers, **k):
        requested.append(list(tickers))
        return [(h, [t]) for t, h in HEADLINES.items() if t in tickers]

    monkeypatch.setattr(news, "feed", fake_feed)
    monkeypatch.setattr(service.market_data, "get_quote", lambda t: Quote(t, t, 100.0, 98.0, 2.0, 2.04, "USD"))
    favorites_store._cache.clear()
    fake.requested = requested
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


def add_favorite(db, ticker, nombre=None, user_id="u1"):
    db.rows("activos_favoritos").append({"user_id": user_id, "ticker": ticker, "nombre": nombre, "created_at": "2026-11-01"})
    favorites_store._cache.clear()  # como hace store.add_favorite


# ---- Sentimiento ----

@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Apple shares surge to record high", "alcista"),
        ("Dell tumbles 8% in AI hardware selloff", "bajista"),
        ("Nvidia sube tras superar previsiones", "alcista"),
        ("Bitcoin cae y se desploma por debajo de 90.000", "bajista"),
        ("What to watch in markets this week", "neutral"),
        ("Stocks rise early, then fall into the close", "neutral"),
        ("Dow Jones Futures: Market Rally Shaky As Nvidia Earnings Loom", "neutral"),
    ],
)
def test_sentiment_classifier(title, expected):
    assert sentiment.classify(title) == expected


# ---- Feed ----

def test_filters_choose_the_right_tickers():
    assert feed.tickers_for("cripto", []) == ["BTC-USD", "ETH-USD", "SOL-USD"]
    assert feed.tickers_for("mis-activos", ["TSLA"]) == ["TSLA"]
    todos = feed.tickers_for("todos", ["PLTR"])
    assert todos[0] == "PLTR" and "^GSPC" in todos and len(todos) <= feed.MAX_TICKERS
    assert feed.tickers_for_scope("favoritos", []) == feed.tickers_for("todos", [])  # sin favoritos: todos


def test_feed_endpoint_tags_tickers_and_sentiment(logged, db):
    data = logged.get("/api/noticias?filtro=cripto").get_json()
    assert data["tickers"] == ["BTC-USD", "ETH-USD", "SOL-USD"]
    [item] = data["items"]
    assert item["activos"] == [{"ticker": "BTC-USD", "nombre": "Bitcoin"}]
    assert item["sentimiento"] == "bajista" and item["publisher"] == "CoinDesk"


def test_my_assets_filter_uses_the_users_list(logged, db):
    assert logged.get("/api/noticias?filtro=mis-activos").get_json()["items"] == []
    add_favorite(db, "AAPL", "Apple Inc.")
    data = logged.get("/api/noticias?filtro=mis-activos").get_json()
    assert data["mis_activos"] == ["AAPL"] and data["items"][0]["activos"][0]["nombre"] == "Apple Inc."


def test_unknown_filter_is_a_400_not_a_404(logged, db):
    assert logged.get("/api/noticias?filtro=nada").status_code == 400


# ---- Suscripción ----

def test_default_subscription_is_off_with_the_account_email(logged, db):
    data = logged.get("/api/noticias/suscripcion").get_json()
    assert data["activa"] is False and data["guardada"] is False
    assert data["email"] == "ana@example.com" and data["alcance"] == "favoritos" and data["via_app"] is True


def test_subscribe_by_app_and_email_then_change_scope(logged, db):
    response = logged.put("/api/noticias/suscripcion", json={"activa": True, "via_email": True, "email": "otra@example.com"})
    assert response.status_code == 200
    [row] = db.rows("suscripciones_noticias")
    assert row == {"user_id": "u1", "activa": True, "via_app": True, "via_email": True, "email": "otra@example.com", "alcance": "favoritos", "created_at": row["created_at"]}

    logged.put("/api/noticias/suscripcion", json={"alcance": "todos"})
    assert db.rows("suscripciones_noticias")[0]["alcance"] == "todos"
    assert db.rows("suscripciones_noticias")[0]["email"] == "otra@example.com"  # se conserva


@pytest.mark.parametrize(
    "body",
    [
        {"activa": True, "via_app": False, "via_email": False},
        {"activa": True, "via_email": True, "email": ""},
        {"email": "no-es-un-correo"},
        {"alcance": "algunos"},
        {"activa": "sí"},
    ],
)
def test_incoherent_subscriptions_are_rejected(logged, db, body):
    assert logged.put("/api/noticias/suscripcion", json=body).status_code == 400
    assert db.rows("suscripciones_noticias") == []


# ---- Campana ----

def test_bell_news_require_an_app_subscription(logged, db):
    assert logged.get("/api/alertas/noticias").get_json() == {"suscrito": False, "items": []}
    logged.put("/api/noticias/suscripcion", json={"activa": True, "alcance": "favoritos"})
    add_favorite(db, "AAPL")
    data = logged.get("/api/alertas/noticias").get_json()
    assert data["suscrito"] is True and db.requested[-1] == ["AAPL"]
    assert data["items"][0]["activos"][0] == {"ticker": "AAPL", "nombre": "Apple Inc.", "variacion": 2.04}


def test_email_only_subscription_does_not_feed_the_bell(logged, db):
    logged.put("/api/noticias/suscripcion", json={"activa": True, "via_app": False, "via_email": True})
    assert logged.get("/api/alertas/noticias").get_json()["suscrito"] is False


# ---- Resumen por correo ----

def test_digest_sends_only_new_headlines_and_remembers_the_send(db, monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "send_email", lambda to, subject, html: sent.append((to, subject, html)))
    db.rows("suscripciones_noticias").extend(
        [
            {"user_id": "u1", "activa": True, "via_app": False, "via_email": True, "email": "ana@example.com", "alcance": "favoritos", "ultimo_envio": None},
            {"user_id": "u2", "activa": True, "via_app": True, "via_email": False, "email": None, "alcance": "todos", "ultimo_envio": None},
        ]
    )
    add_favorite(db, "AAPL")
    app = create_app(TestingConfig)
    with app.app_context():
        first = digest.run(now=NOW)
        again = digest.run(now=NOW)
    assert (first.sent, first.skipped) == (1, 0)
    [(to, subject, html)] = sent
    assert to == "ana@example.com" and "1 noticia" in subject
    assert "Apple shares surge" in html and "Alcista" in html and "Bitcoin" not in html
    assert db.rows("suscripciones_noticias")[0]["ultimo_envio"] == NOW.isoformat()
    assert (again.sent, again.skipped) == (0, 1)  # nada nuevo desde el último envío


# ---- Página y seguridad ----

def test_api_requires_a_session(db):
    anon = client_for(None)
    assert anon.get("/api/noticias").status_code == 401
    assert anon.put("/api/noticias/suscripcion", json={"activa": True}).status_code == 401


def test_page_has_subscription_card_and_filters(logged, db):
    page = logged.get("/app/noticias/").get_data(as_text=True)
    assert "Noticias del <span class=\"accent\">mercado</span>" in page
    assert "Suscribirse a alertas de noticias" in page and 'role="switch"' in page
    assert "Campana de la app" in page and "Correo electrónico" in page and 'value="ana@example.com"' in page
    assert "Todos los activos" in page and "Solo mis favoritos" in page
    for label in ("Todos", "Mis activos", "Tecnología", "Cripto", "Índices"):
        assert f">{label}</button>" in page
    assert 'aria-current="page"' in page.split('href="/app/noticias/"', 1)[0][-400:] + page.split('href="/app/noticias/"', 1)[1][:200]


# ---- Tabla de suscripciones aún sin crear en InsForge ----

def test_without_the_subscriptions_table_the_defaults_load_in_local_mode(logged, db):
    db.missing.add("suscripciones_noticias")
    response = logged.get("/api/noticias/suscripcion")
    assert response.status_code == 200
    data = response.get_json()
    assert data["almacenamiento"] == "local" and data["guardada"] is False
    assert data["activa"] is False and data["email"] == "ana@example.com"


def test_without_the_table_changes_are_validated_and_returned_for_local_storage(logged, db):
    db.missing.add("suscripciones_noticias")
    response = logged.put("/api/noticias/suscripcion", json={"activa": True, "alcance": "todos"})
    assert response.status_code == 503
    body = response.get_json()
    assert body["codigo"] == "tabla_pendiente" and body["tabla"] == "suscripciones_noticias"
    assert body["suscripcion"]["activa"] is True and body["suscripcion"]["alcance"] == "todos"
    # Datos incoherentes: 400 como siempre (no se guardan en el navegador).
    assert logged.put("/api/noticias/suscripcion", json={"activa": True, "via_app": False, "via_email": False}).status_code == 400


def test_with_the_table_the_server_mode_is_reported(logged, db):
    assert logged.get("/api/noticias/suscripcion").get_json()["almacenamiento"] == "servidor"


def test_bell_treats_a_missing_subscriptions_table_as_not_subscribed(logged, db):
    db.missing.add("suscripciones_noticias")
    response = logged.get("/api/alertas/noticias")
    assert response.status_code == 200
    assert response.get_json() == {"suscrito": False, "pendiente": True, "items": []}


def test_the_page_includes_the_neutral_local_storage_notice(logged, db):
    page = logged.get("/app/noticias/").get_data(as_text=True)
    assert 'id="news-sub-notice" hidden' in page and "se guarda en este navegador" in page
