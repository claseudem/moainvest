"""Proveedor Dukascopy del Graficador (HTTP simulado) y su uso desde la API."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from app.core import market_data
from app.graficador import providers
from app.graficador.providers import DukascopyProvider, ProviderError, dukascopy_instrument
from config import Config

NOW = datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc)
MS = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731


def row(dt, price=1.0, volume=10.5):
    return [MS(dt), price, price + 1, price - 1, price + 0.5, volume]


class FakeResponse:
    def __init__(self, rows, status_code=200):
        self.text = "_callback(" + json.dumps(rows) + ");"
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def provider_with(handler):
    """``handler(params)`` devuelve las filas (o una excepción / FakeResponse) de cada petición."""
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(dict(params))
        result = handler(params)
        if isinstance(result, Exception):
            raise result
        return result if isinstance(result, FakeResponse) else FakeResponse(result)

    return DukascopyProvider(get=fake_get, now=lambda: NOW), calls


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(Config, "DUKASCOPY_CACHE_TTL", 0)
    market_data._cache.clear()


@pytest.mark.parametrize(
    "ticker,instrument",
    [
        ("AAPL", "AAPL.US/USD"),
        ("BRK-B", "BRKB.US/USD"),
        ("EURUSD=X", "EUR/USD"),
        ("BTC-USD", "BTC/USD"),
        ("^GSPC", "USA500.IDX/USD"),
        ("GC=F", "XAU/USD"),
        ("SAN.MC", "SAN.ES/EUR"),
    ],
)
def test_yahoo_tickers_map_to_dukascopy_instruments(ticker, instrument):
    assert dukascopy_instrument(ticker) == instrument


@pytest.mark.parametrize("ticker", ["^IXIC", "ES=F", "005930.KS"])
def test_tickers_without_equivalent_raise_422(ticker):
    with pytest.raises(ProviderError) as error:
        dukascopy_instrument(ticker)
    assert error.value.status == 422


def test_intraday_candles_are_normalized_ascending_and_deduplicated():
    a, b = NOW - timedelta(minutes=10), NOW - timedelta(minutes=5)
    provider, calls = provider_with(lambda p: [row(b, 2.0), row(a, 1.0), row(b, 2.0), [MS(a)]])
    candles = provider.get_candles("AAPL", "1d", "5m")
    assert [c["time"] for c in candles] == [int(a.timestamp()), int(b.timestamp())]
    assert candles[0] == {"time": int(a.timestamp()), "open": 1.0, "high": 2.0, "low": 0.0, "close": 1.5, "volume": 10.5}
    assert calls[0]["instrument"] == "AAPL.US/USD" and calls[0]["interval"] == "5MIN"
    assert calls[0]["offer_side"] == "B"


def test_intraday_range_is_split_in_parallel_windows():
    # Cada ventana devuelve una vela en su inicio y otra en su final: así no pagina.
    provider, calls = provider_with(
        lambda p: [[int(p["last_update"]), 1, 2, 0, 1, 1], [int(p["last_update"]) + 28 * 86_400_000, 1, 2, 0, 1, 1]]
    )
    provider.get_candles("EURUSD=X", "1y", "5m")
    # 366 días + margen, en ventanas de 28 días.
    assert len(calls) == 14
    assert len({c["last_update"] for c in calls}) == 14


def test_window_paginates_until_reaching_its_end():
    start = NOW - timedelta(days=36)  # 1 mes (31) + margen (5)
    pages = iter([[row(start + timedelta(days=d)) for d in range(3)], [row(NOW)]])
    provider, calls = provider_with(lambda p: next(pages))
    candles = provider.get_candles("EURUSD=X", "1mo", "1h")
    assert len(calls) == 2
    assert int(calls[1]["last_update"]) == MS(start + timedelta(days=2))
    assert candles[-1]["time"] == int(NOW.timestamp())


def test_range_is_sliced_from_the_last_candle():
    # Fin de semana: la última vela es del viernes y «1d» muestra ese día, no 24 h vacías.
    friday = NOW - timedelta(days=1)
    rows = [row(friday - timedelta(hours=h)) for h in (30, 20, 0)]
    provider, _ = provider_with(lambda p: rows)
    candles = provider.get_candles("AAPL", "1d", "1h")
    assert len(candles) == 2


def test_long_intraday_ranges_are_capped():
    provider, calls = provider_with(lambda p: [row(NOW)])
    provider.get_candles("EURUSD=X", "max", "1m")
    first = min(int(c["last_update"]) for c in calls)
    assert first == MS(NOW - timedelta(days=31 + 5))


def test_daily_max_starts_at_dukascopy_history():
    provider, calls = provider_with(lambda p: [row(NOW)])
    provider.get_candles("BTC-USD", "max", "1d")
    assert len(calls) == 1 and calls[0]["interval"] == "1DAY"
    assert int(calls[0]["last_update"]) == MS(providers.DK_EPOCH)


def test_unknown_instrument_and_empty_data_raise_404():
    provider, _ = provider_with(lambda p: [None])
    with pytest.raises(ProviderError) as error:
        provider.get_candles("ZZZZQ", "1d", "5m")
    assert error.value.status == 404 and "ZZZZQ.US/USD" in error.value.message

    provider, _ = provider_with(lambda p: [])
    with pytest.raises(ProviderError) as error:
        provider.get_candles("AAPL", "1d", "5m")
    assert error.value.status == 404


@pytest.mark.parametrize(
    "result,status",
    [
        (requests.Timeout(), 504),
        (requests.ConnectionError(), 502),
        (FakeResponse([], status_code=429), 429),
        (FakeResponse([], status_code=500), 502),
    ],
)
def test_network_failures_become_provider_errors(result, status):
    provider, _ = provider_with(lambda p: result)
    with pytest.raises(ProviderError) as error:
        provider.get_candles("AAPL", "1d", "5m")
    assert error.value.status == status


def test_garbage_response_is_a_provider_error():
    provider = DukascopyProvider(get=lambda *a, **k: type("R", (), {"status_code": 200, "text": "<html>", "raise_for_status": lambda s: None})())
    with pytest.raises(ProviderError):
        provider.get_candles("AAPL", "1d", "5m")


def test_response_is_cached(monkeypatch):
    monkeypatch.setattr(Config, "DUKASCOPY_CACHE_TTL", 60)
    provider, calls = provider_with(lambda p: [row(NOW)])
    provider.get_candles("AAPL", "6mo", "1d")
    provider.get_candles("AAPL", "6mo", "1d")
    assert len(calls) == 1


# ───────────────────────── API ─────────────────────────

def test_dukascopy_is_listed_and_available(client):
    data = client.get("/api/graficador/providers").get_json()
    dukascopy = next(p for p in data["providers"] if p["id"] == "dukascopy")
    assert dukascopy["available"] is True and dukascopy["name"] == "Dukascopy"


def test_candles_and_indicators_endpoints_with_dukascopy(client, monkeypatch):
    rows = [row(NOW - timedelta(minutes=5 * i), 100.0 + i) for i in range(40)]
    fake, _ = provider_with(lambda p: rows)
    monkeypatch.setitem(providers.PROVIDERS, "dukascopy", fake)

    response = client.get("/api/graficador/EURUSD=X/candles?provider=dukascopy&range=1d&interval=5m")
    assert response.status_code == 200 and len(response.get_json()) == 40

    response = client.get("/api/graficador/EURUSD=X/indicators?provider=dukascopy&range=1d&interval=5m&ind=sma:5")
    assert response.status_code == 200
    assert len(response.get_json()["time"]) == 40


def test_candles_endpoint_reports_unsupported_ticker(client):
    response = client.get("/api/graficador/%5EIXIC/candles?provider=dukascopy&range=1d&interval=5m")
    assert response.status_code == 422 and "Yahoo" in response.get_json()["error"]


# ───────────────────────── Periodicidades ─────────────────────────

def test_dukascopy_offers_grouped_intervals_with_history_limits(client):
    data = client.get("/api/graficador/providers").get_json()
    by_id = {p["id"]: p for p in data["providers"]}
    assert by_id["yahoo"]["intervals"] == []
    choices = {c["value"]: c for c in by_id["dukascopy"]["intervals"]}
    assert list(choices) == ["1s", "10s", "30s", "1m", "5m", "10m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]
    assert choices["1s"]["group"] == "Segundos" and choices["1s"]["max_days"] == 1
    assert choices["4h"]["group"] == "Horas" and choices["4h"]["max_days"] is None


@pytest.mark.parametrize("interval,dk", [("1s", "1SEC"), ("10s", "10SEC"), ("30s", "30SEC"), ("10m", "10MIN"), ("4h", "4HOUR")])
def test_extra_intervals_map_to_dukascopy(interval, dk):
    provider, calls = provider_with(lambda p: [row(NOW)])
    provider.get_candles("EURUSD=X", "1d", interval)
    assert {c["interval"] for c in calls} == {dk}


def test_seconds_are_capped_and_split_in_daily_windows():
    provider, calls = provider_with(lambda p: [row(NOW)])
    provider.get_candles("EURUSD=X", "1y", "1s")
    # 1 día como mucho, más el margen de fin de semana, en ventanas de 12 horas.
    assert len(calls) == 2 * (1 + providers.DK_PADDING_DAYS_SECONDS)
    assert min(int(c["last_update"]) for c in calls) == MS(NOW - timedelta(days=1 + providers.DK_PADDING_DAYS_SECONDS))


def test_seconds_endpoint_with_dukascopy(client, monkeypatch):
    rows = [row(NOW - timedelta(seconds=i), 1.1) for i in range(30)]
    fake, _ = provider_with(lambda p: rows)
    monkeypatch.setitem(providers.PROVIDERS, "dukascopy", fake)
    response = client.get("/api/graficador/EURUSD=X/candles?provider=dukascopy&range=1d&interval=1s")
    assert response.status_code == 200 and len(response.get_json()) == 30
    response = client.get("/api/graficador/EURUSD=X/indicators?provider=dukascopy&range=1d&interval=1s&ind=sma:5")
    assert response.status_code == 200 and len(response.get_json()["time"]) == 30


def test_other_providers_reject_dukascopy_only_intervals(client):
    response = client.get("/api/graficador/AAPL/candles?provider=yahoo&range=1d&interval=1s")
    assert response.status_code == 422 and "Yahoo Finance" in response.get_json()["error"]
    assert client.get("/api/graficador/AAPL/candles?provider=dukascopy&interval=7s").status_code == 400


def test_page_has_interval_selector(client):
    html = client.get("/app/graficador/?ticker=AAPL").data
    assert b'id="graficador-interval"' in html
