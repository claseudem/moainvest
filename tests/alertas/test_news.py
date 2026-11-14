"""Titulares de contexto: normalización de formatos y elección por relevancia."""
import pytest

from app.core import news

NOW = 1_800_000_000


def search_item(uid, title, hours_ago, related=("DELL",)):
    return {
        "uuid": uid,
        "title": title,
        "publisher": "Wire",
        "link": f"https://example.com/{uid}",
        "providerPublishTime": NOW - hours_ago * 3600,
        "relatedTickers": list(related),
    }


@pytest.fixture(autouse=True)
def clear_cache():
    news._cache.clear()
    yield
    news._cache.clear()


def stub(monkeypatch, items_by_ticker):
    def fake_fetch(ticker):
        headlines = [news.normalize(i) for i in items_by_ticker.get(ticker, [])]
        return sorted([h for h in headlines if h], key=lambda h: h.published_at, reverse=True)

    monkeypatch.setattr(news, "_fetch", fake_fetch)


def test_normalizes_both_yfinance_formats():
    a = news.normalize(search_item("a", "Dell tumbles", 1))
    assert (a.id, a.publisher, a.url, a.related) == ("a", "Wire", "https://example.com/a", ("DELL",))
    b = news.normalize(
        {
            "id": "b",
            "content": {
                "title": "Dell beats",
                "pubDate": "2026-11-13T19:03:32Z",
                "provider": {"displayName": "Reuters"},
                "canonicalUrl": {"url": "https://example.com/b"},
            },
        }
    )
    assert (b.title, b.publisher, b.url) == ("Dell beats", "Reuters", "https://example.com/b")
    assert news.normalize({"title": "sin fecha"}) is None


def test_best_headline_prefers_titles_naming_the_asset(monkeypatch):
    stub(
        monkeypatch,
        {
            "DELL": [
                search_item("generic", "Tech stocks slide on AI fears", 1),
                search_item("named", "Dell plunges after weak guidance", 5),
            ]
        },
    )
    assert news.best_headline("DELL", "Dell", now=NOW).id == "named"


def test_best_headline_ignores_old_or_unrelated_news(monkeypatch):
    stub(
        monkeypatch,
        {
            "DELL": [
                search_item("old", "Dell plunges", 72),
                search_item("other", "Nvidia rallies", 1, related=("NVDA",)),
            ]
        },
    )
    assert news.best_headline("DELL", "Dell", now=NOW) is None


def test_feed_dedups_and_tags_watched_tickers(monkeypatch):
    shared = search_item("s", "Dell and HP fall", 2, related=("DELL", "HPQ"))
    stub(monkeypatch, {"DELL": [shared], "HPQ": [shared, search_item("h", "HP update", 1, related=("HPQ",))]})
    items = news.feed(["DELL", "HPQ"], now=NOW)
    assert [h.id for h, _ in items] == ["h", "s"]
    assert sorted(dict((h.id, t) for h, t in items)["s"]) == ["DELL", "HPQ"]
