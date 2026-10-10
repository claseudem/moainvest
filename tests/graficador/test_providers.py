"""Proveedores de precios del Graficador: Alpha Vantage (HTTP simulado) y API."""
import pytest
import requests

from app.core import market_data
from app.graficador import providers
from app.graficador.providers import AlphaVantageProvider, ProviderError
from config import Config

INTRADAY = {
    "Meta Data": {},
    "Time Series (5min)": {
        "2026-01-05 10:05:00": {"1. open": "11", "2. high": "12", "3. low": "10", "4. close": "11.5", "5. volume": "200"},
        "2026-01-05 10:00:00": {"1. open": "10", "2. high": "11", "3. low": "9", "4. close": "11", "5. volume": "100"},
    },
}
DAILY = {
    "Time Series (Daily)": {
        f"2025-{m:02d}-01": {"1. open": "1", "2. high": "2", "3. low": "0.5", "4. close": "1.5", "5. volume": "10"}
        for m in range(1, 13)
    },
}


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload, self.error = payload, error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def av_key(monkeypatch):
    monkeypatch.setattr(Config, "ALPHAVANTAGE_API_KEY", "clave-de-test")
    monkeypatch.setattr(Config, "ALPHAVANTAGE_CACHE_TTL", 0)
    market_data._cache.clear()


def provider_with(*responses):
    calls = []
    queue = list(responses)

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResponse) else FakeResponse(item)

    return AlphaVantageProvider(get=fake_get), calls


def test_intraday_normalizes_to_ohlcv_ascending_utc():
    provider, calls = provider_with(INTRADAY)
    candles = provider.get_candles("AAPL", "1d", "5m")
    assert calls[0]["function"] == "TIME_SERIES_INTRADAY" and calls[0]["interval"] == "5min"
    assert [c["close"] for c in candles] == [11.0, 11.5]
    assert set(candles[0]) == {"time", "open", "high", "low", "close", "volume"}
    # 10:00 de Nueva York en enero (UTC-5) = 15:00 UTC.
    assert candles[0]["time"] == 1767625200
    assert candles[0]["volume"] == 100


def test_daily_uses_daily_function_and_slices_range():
    provider, calls = provider_with(DAILY)
    assert len(provider.get_candles("AAPL", "max", "1d")) == 12
    assert calls[0]["function"] == "TIME_SERIES_DAILY" and "interval" not in calls[0]
    provider, _ = provider_with(DAILY)
    assert len(provider.get_candles("AAPL", "3mo", "1d")) == 4  # sep (a 91 días de la última vela), oct, nov y dic


def test_daily_falls_back_to_compact_when_full_is_premium():
    premium = {"Information": "This is a premium feature, outputsize=full ..."}
    provider, calls = provider_with(premium, DAILY)
    assert provider.get_candles("AAPL", "max", "1d")
    assert [c["outputsize"] for c in calls] == ["full", "compact"]


def test_rate_limit_note_and_information_raise_429():
    for key in ("Note", "Information"):
        provider, _ = provider_with({key: "Our standard API rate limit is 25 requests per day."})
        with pytest.raises(ProviderError) as error:
            provider.get_candles("AAPL", "1d", "5m")
        assert error.value.status == 429 and "límite" in error.value.message


def test_unknown_symbol_and_unsupported_input():
    provider, _ = provider_with({"Error Message": "Invalid API call"})
    with pytest.raises(ProviderError) as error:
        provider.get_candles("ZZZZ", "1d", "1d")
    assert error.value.status == 404
    with pytest.raises(ProviderError) as error:
        provider.get_candles("^GSPC", "1d", "1d")
    assert error.value.status == 422


def test_network_failures_become_provider_errors():
    for failure, status in ((requests.Timeout(), 504), (requests.ConnectionError(), 502)):
        provider, _ = provider_with(failure)
        with pytest.raises(ProviderError) as error:
            provider.get_candles("AAPL", "1d", "5m")
        assert error.value.status == status


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(Config, "ALPHAVANTAGE_API_KEY", "")
    info = {p["id"]: p for p in providers.catalog()}
    assert info["yahoo"]["available"] is True
    assert info["alphavantage"]["available"] is False
    assert "ALPHAVANTAGE_API_KEY" in info["alphavantage"]["reason"]
    with pytest.raises(ProviderError) as error:
        AlphaVantageProvider(get=lambda *a, **k: 1 / 0).get_candles("AAPL", "1d", "1d")
    assert error.value.status == 503


def test_response_is_cached_across_ranges(monkeypatch):
    monkeypatch.setattr(Config, "ALPHAVANTAGE_CACHE_TTL", 300)
    provider, calls = provider_with(DAILY)
    provider.get_candles("AAPL", "max", "1d")
    provider.get_candles("AAPL", "6mo", "1d")  # una segunda llamada HTTP agotaría la cola
    assert len(calls) == 1


# ───────────────────────── API ─────────────────────────

def test_providers_endpoint(client, monkeypatch):
    monkeypatch.setattr(Config, "ALPHAVANTAGE_API_KEY", "")
    data = client.get("/api/graficador/providers").get_json()
    assert data["default"] == "yahoo"
    assert [p["id"] for p in data["providers"]] == ["yahoo", "alphavantage", "dukascopy"]
    assert data["providers"][1]["available"] is False


def test_candles_endpoint_uses_chosen_provider(client, monkeypatch):
    fake, _ = provider_with(INTRADAY)
    monkeypatch.setitem(providers.PROVIDERS, "alphavantage", fake)
    response = client.get("/api/graficador/aapl/candles?provider=alphavantage&range=1d&interval=5m")
    assert response.status_code == 200
    assert len(response.get_json()) == 2


def test_candles_endpoint_defaults_to_yahoo(client, monkeypatch):
    monkeypatch.setattr("app.graficador.providers.market_data.get_candles", lambda *a: [{"time": 1}])
    assert client.get("/api/graficador/AAPL/candles").get_json() == [{"time": 1}]


@pytest.mark.parametrize(
    "url,status",
    [
        ("/api/graficador/AAPL/candles?provider=nope", 400),
        ("/api/graficador/AAPL/candles?range=7y", 400),
        ("/api/graficador/%3Cb%3E/candles", 400),
    ],
)
def test_candles_endpoint_validation(client, url, status):
    response = client.get(url)
    assert response.status_code == status and "error" in response.get_json()


def test_candles_endpoint_reports_provider_errors(client, monkeypatch):
    monkeypatch.setattr(Config, "ALPHAVANTAGE_API_KEY", "")
    response = client.get("/api/graficador/AAPL/candles?provider=alphavantage")
    assert response.status_code == 503 and "ALPHAVANTAGE_API_KEY" in response.get_json()["error"]

    limited, _ = provider_with({"Note": "rate limit"})
    monkeypatch.setattr(Config, "ALPHAVANTAGE_API_KEY", "x")
    monkeypatch.setitem(providers.PROVIDERS, "alphavantage", limited)
    response = client.get("/api/graficador/AAPL/candles?provider=alphavantage")
    assert response.status_code == 429


def test_indicators_endpoint_with_alphavantage(client, monkeypatch):
    fake, _ = provider_with(DAILY)
    monkeypatch.setitem(providers.PROVIDERS, "alphavantage", fake)
    response = client.get("/api/graficador/AAPL/indicators?provider=alphavantage&range=max&interval=1d&ind=sma:3")
    assert response.status_code == 200
    assert len(response.get_json()["time"]) == 12


def test_indicators_endpoint_propagates_provider_error(client, monkeypatch):
    monkeypatch.setattr(Config, "ALPHAVANTAGE_API_KEY", "")
    response = client.get("/api/graficador/AAPL/indicators?provider=alphavantage&ind=sma:3")
    assert response.status_code == 503


def test_page_has_provider_selector(client):
    html = client.get("/app/graficador/?ticker=AAPL").data
    assert b'id="graficador-provider"' in html
    assert b"/api/graficador/providers" in html
