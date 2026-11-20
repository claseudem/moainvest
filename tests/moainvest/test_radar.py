"""Radar de noticias del Inicio: termómetro, noticias vs. precio y API /api/radar."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core import news
from app.core.watchlists import Symbol, Watchlist, get_watchlist
from app.moainvest import radar
from app.noticias import sentiment

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc).timestamp()
HOUR = 3600

WATCHLIST = Watchlist(
    slug="test",
    name="Test",
    icon="🧪",
    symbols=(Symbol("AAPL", "Apple"), Symbol("BTC-USD", "Bitcoin"), Symbol("^GSPC", "S&P 500")),
)


def _headline(uid, title, hours_ago, *related):
    return news.Headline(uid, title, "Reuters", f"https://example.com/{uid}", int(NOW - hours_ago * HOUR), related)


HEADLINES = [
    (_headline("n1", "Apple shares surge to record high", 1, "AAPL"), ["AAPL"]),
    (_headline("n2", "Apple beats estimates as iPhone demand rises", 3, "AAPL"), ["AAPL"]),
    (_headline("n3", "Bitcoin tumbles as crypto selloff deepens", 2, "BTC-USD"), ["BTC-USD"]),
    (_headline("n4", "What to watch in markets this week", 30, "^GSPC"), ["^GSPC"]),
]


def _quotes(changes):
    return lambda ticker: SimpleNamespace(change_percent=changes[ticker])


@pytest.fixture()
def fake_feed(monkeypatch):
    calls = []

    def feed(tickers, **kwargs):
        calls.append(list(tickers))
        return [(h, r) for h, r in HEADLINES if set(r) & set(tickers)]

    monkeypatch.setattr(news, "feed", feed)
    return calls


# ── Sentimiento explicable ──────────────────────────────────────


def test_signals_lists_the_words_behind_the_sentiment():
    found = sentiment.signals("Apple shares surge to record high")
    assert found == {"alcistas": ["surge", "record high"], "bajistas": []}
    assert sentiment.classify("Apple shares surge to record high") == "alcista"
    assert sentiment.signals("What to watch this week") == {"alcistas": [], "bajistas": []}


# ── Termómetro ──────────────────────────────────────────────────


def test_recency_weight_halves_every_half_life():
    assert radar.recency_weight(int(NOW), NOW) == 1
    assert radar.recency_weight(int(NOW - radar.HALF_LIFE_HOURS * HOUR), NOW) == pytest.approx(0.5)
    assert radar.recency_weight(int(NOW + HOUR), NOW) == 1  # fechas futuras no pesan más de 1


@pytest.mark.parametrize(
    ("sentiments", "value", "label"),
    [
        (["alcista", "alcista"], 100, "Euforia"),
        (["bajista", "bajista"], 0, "Miedo extremo"),
        (["alcista", "bajista"], 50, "Neutral"),
        (["alcista", "neutral"], 75, "Optimismo"),
    ],
)
def test_pulse_maps_tone_to_0_100_scale(sentiments, value, label):
    items = [{"sentimiento": s, "peso": 1} for s in sentiments]
    result = radar.pulse(items)
    assert (result["valor"], result["etiqueta"]) == (value, label)
    assert result["total"] == len(sentiments)


def test_recent_headlines_weigh_more_in_the_pulse():
    items = [{"sentimiento": "alcista", "peso": 1.0}, {"sentimiento": "bajista", "peso": 0.25}]
    assert radar.pulse(items)["valor"] == 80


def test_pulse_without_headlines_has_no_value():
    result = radar.pulse([])
    assert result["valor"] is None
    assert result["etiqueta"] == "Sin datos"


# ── Noticias vs. precio ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("tone", "change", "estado"),
    [
        (0.8, 1.5, "confirma"),
        (-0.8, -2.0, "confirma"),
        (0.8, -1.2, "divergencia"),
        (-0.6, 0.9, "divergencia"),
        (0.0, 3.0, "neutral"),
        (0.8, 0.05, "neutral"),
        (None, 1.0, "sin-noticias"),
        (0.5, None, "sin-precio"),
    ],
)
def test_asset_signal(tone, change, estado):
    assert radar.asset_signal(tone, change)["estado"] == estado


# ── build ───────────────────────────────────────────────────────


def test_build_combines_pulse_assets_and_headlines(fake_feed):
    data = radar.build(WATCHLIST, _quotes({"AAPL": -1.4, "BTC-USD": -3.0, "^GSPC": 0.4}), now=NOW)

    assert fake_feed == [["AAPL", "BTC-USD", "^GSPC"]]
    assert [n["id"] for n in data["noticias"]] == ["n1", "n2", "n3", "n4"]
    first = data["noticias"][0]
    assert first["sentimiento"] == "alcista"
    assert first["senales"]["alcistas"] == ["surge", "record high"]
    assert first["activos"] == [{"ticker": "AAPL", "nombre": "Apple"}]

    by_ticker = {a["ticker"]: a for a in data["activos"]}
    assert by_ticker["AAPL"]["estado"] == "divergencia"  # noticias buenas, precio cae
    assert by_ticker["AAPL"]["noticias"] == 2
    assert by_ticker["BTC-USD"]["estado"] == "confirma"  # noticias malas, precio cae
    assert by_ticker["^GSPC"]["estado"] == "neutral"
    assert data["pulso"]["conteo"] == {"alcista": 2, "bajista": 1, "neutral": 1}
    assert 50 < data["pulso"]["valor"] < 100


def test_build_survives_a_failing_quote(fake_feed):
    def boom(ticker):
        raise RuntimeError("Yahoo is down")

    data = radar.build(WATCHLIST, boom, now=NOW)
    assert {a["estado"] for a in data["activos"]} <= {"sin-precio", "sin-noticias"}


# ── API e Inicio ────────────────────────────────────────────────


def test_radar_api_is_public_and_uses_the_watchlist(client, monkeypatch):
    seen = []

    def fake_build(watchlist, quote_for):
        seen.append(watchlist.slug)
        return {"pulso": {}, "activos": [], "noticias": [], "actualizado": "x"}

    monkeypatch.setattr(radar, "build", fake_build)
    response = client.get("/api/radar")
    assert response.status_code == 200
    assert response.get_json()["noticias"] == []
    assert seen == ["overview"]
    assert "max-age=120" in response.headers["Cache-Control"]


def test_radar_api_unknown_watchlist_is_404(client):
    assert client.get("/api/radar?watchlist=no-existe").status_code == 404


def test_home_shows_the_news_radar(client):
    page = client.get("/").get_data(as_text=True)
    overview = get_watchlist("overview")
    assert f'data-news-radar="{overview.slug}"' in page
    assert "Termómetro del mercado" in page
    assert "Noticias vs. precio" in page
    assert "no es una recomendación de inversión" in page
