"""Indicadores técnicos del Graficador (TA-Lib) y su API."""
import json

import numpy as np
import pytest

from app.core.api import ALLOWED_INTERVALS, ALLOWED_RANGES
from app.graficador import indicators
from app.graficador.indicators import CATEGORIES, INDICATORS, compute_series, parse_spec, warmup_range


def fake_candles(n=300, start=1_700_000_000, step=86_400, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return [
        {
            "time": start + step * i,
            "open": float(close[i] - 0.3),
            "high": float(close[i] + 1),
            "low": float(close[i] - 1),
            "close": float(close[i]),
            "volume": int(1_000_000 + rng.integers(0, 100_000)),
        }
        for i in range(n)
    ]


def rising(n=60):
    """Cierres 1, 2, 3...: la SMA y el RSI tienen valores conocidos."""
    return [
        {"time": 1_700_000_000 + 86_400 * i, "open": i + 1.0, "high": i + 1.5, "low": i + 0.5, "close": i + 1.0, "volume": 1000}
        for i in range(n)
    ]


# ───────────────────────── Catálogo ─────────────────────────


def test_catalog_ids_are_unique_and_categories_valid():
    ids = [i.id for i in INDICATORS]
    assert len(ids) == len(set(ids))
    assert {i.category for i in INDICATORS} <= set(CATEGORIES)
    # Hay indicadores de cada familia y también los clásicos de TradingView.
    assert {i.category for i in INDICATORS} == set(CATEGORIES)
    assert {"sma", "ema", "bbands", "rsi", "macd", "stoch", "atr", "obv"} <= set(ids)


@pytest.mark.parametrize("indicator", INDICATORS, ids=lambda i: i.id)
def test_every_indicator_computes_and_matches_its_declaration(indicator):
    result = compute_series(fake_candles(), [indicator.id])
    outputs = result["indicators"][0]["outputs"]
    # Las claves que devuelve TA-Lib son exactamente las que el catálogo declara.
    assert set(outputs) == {o.key for o in indicator.outputs}
    for values in outputs.values():
        assert len(values) == len(result["time"])
        assert any(v is not None for v in values)
    # Los parámetros por defecto caen dentro de sus propios límites.
    for param in indicator.params:
        assert param.parse(param.default) == param.default
    assert indicator.overlay or indicator.category != "Tendencia"
    if indicator.bounds:
        assert indicator.bounds[0] < indicator.bounds[1]


def test_catalog_is_json_serializable():
    data = json.loads(json.dumps(indicators.catalog()))
    assert data["palette"] and data["categories"] == list(CATEGORIES)
    assert len(data["indicators"]) == len(INDICATORS)
    macd = next(i for i in data["indicators"] if i["id"] == "macd")
    assert [p["key"] for p in macd["params"]] == ["fast", "slow", "signal"]
    assert [o["style"] for o in macd["outputs"]] == ["line", "line", "histogram"]


# ───────────────────────── Valores ─────────────────────────


def test_sma_matches_hand_computed_values_and_warms_up_with_none():
    sma = compute_series(rising(), ["sma:3"])["indicators"][0]["outputs"]["sma"]
    assert sma[:2] == [None, None]
    # Cierres 1, 2, 3, 4...: la media de 3 cierres es el cierre central.
    assert sma[2:6] == [2.0, 3.0, 4.0, 5.0]


def test_rsi_of_a_pure_uptrend_is_100():
    rsi = compute_series(rising(), ["rsi:14"])["indicators"][0]["outputs"]["rsi"]
    assert rsi[:14] == [None] * 14
    assert all(v == 100.0 for v in rsi[14:])


def test_macd_histogram_is_macd_minus_signal():
    out = compute_series(fake_candles(), ["macd:12,26,9"])["indicators"][0]["outputs"]
    pairs = [(m, s, h) for m, s, h in zip(out["macd"], out["signal"], out["hist"]) if h is not None]
    assert pairs
    for macd, signal, hist in pairs:
        assert hist == pytest.approx(macd - signal, abs=1e-6)


def test_bollinger_bands_surround_the_middle_band():
    out = compute_series(fake_candles(), ["bbands:20,2"])["indicators"][0]["outputs"]
    rows = [(u, m, l) for u, m, l in zip(out["upper"], out["middle"], out["lower"]) if m is not None]
    assert rows and all(u > m > l for u, m, l in rows)


def test_since_trims_the_result_and_the_warmup_is_already_done():
    candles = fake_candles(300)
    since = candles[200]["time"]
    result = compute_series(candles, ["sma:50"], since=since)
    assert result["time"][0] == since and len(result["time"]) == 100
    # Con 200 velas de calentamiento antes de ``since``, no queda ningún hueco.
    assert None not in result["indicators"][0]["outputs"]["sma"]
    # Sin ``since`` el mismo indicador empieza con huecos.
    assert None in compute_series(candles, ["sma:50"])["indicators"][0]["outputs"]["sma"]


def test_several_instances_of_the_same_indicator_keep_their_order():
    result = compute_series(fake_candles(), ["sma:10", "sma:50", "ema:20"])
    assert [r["spec"] for r in result["indicators"]] == ["sma:10", "sma:50", "ema:20"]
    first, second = (r["outputs"]["sma"] for r in result["indicators"][:2])
    assert first != second


def test_empty_candles_give_empty_series():
    result = compute_series([], ["rsi:14", "macd"])
    assert result["time"] == []
    assert result["indicators"][1]["outputs"] == {"macd": [], "signal": [], "hist": []}


def test_fewer_candles_than_the_period_gives_only_none():
    sma = compute_series(fake_candles(5), ["sma:20"])["indicators"][0]["outputs"]["sma"]
    assert sma == [None] * 5


def test_output_is_valid_strict_json():
    # Los NaN del calentamiento no pueden llegar como ``NaN`` (JSON inválido).
    text = json.dumps(compute_series(fake_candles(), [i.id for i in INDICATORS]), allow_nan=False)
    assert "NaN" not in text


# ───────────────────────── Validación ─────────────────────────


def test_parse_spec_defaults_and_partial_params():
    indicator, params = parse_spec("macd")
    assert indicator.id == "macd" and params == {"fast": 12, "slow": 26, "signal": 9}
    assert parse_spec("MACD:8,21")[1] == {"fast": 8, "slow": 21, "signal": 9}
    assert parse_spec(" sma : 50 ")[1] == {"period": 50}
    assert parse_spec("bbands:20,2.5")[1] == {"period": 20, "stddev": 2.5}
    assert parse_spec("obv")[1] == {}


@pytest.mark.parametrize(
    "spec, message",
    [
        ("nope:1", "desconocido"),
        ("", "desconocido"),
        ("sma:0", "entre"),
        ("sma:100000", "entre"),
        ("sma:abc", "número"),
        ("sma:nan", "número"),
        ("sma:2.5", "entero"),
        ("sma:20,30", "como máximo"),
        ("obv:5", "como máximo"),
        ("bbands:20,0", "entre"),
    ],
)
def test_parse_spec_rejects_invalid_input(spec, message):
    with pytest.raises(ValueError, match=message):
        parse_spec(spec)


def test_warmup_range_never_shrinks_and_respects_yahoo_limits():
    order = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
    for range_ in ALLOWED_RANGES:
        for interval in ALLOWED_INTERVALS:
            warm = warmup_range(range_, interval)
            assert warm in ALLOWED_RANGES
            # Nunca menos historia de la que se ve en el gráfico.
            assert order.index(warm) >= order.index(range_), (range_, interval, warm)
            # Y nunca más de lo que Yahoo da a ese intervalo (salvo que ya se pidiera más).
            limit = {"1m": "1d", "5m": "1mo", "15m": "1mo", "30m": "1mo", "1h": "1y"}.get(interval)
            if limit and order.index(range_) <= order.index(limit):
                assert order.index(warm) <= order.index(limit) or interval == "1m"
    assert warmup_range("6mo", "1d") == "5y"
    assert warmup_range("5y", "1wk") == "max"
    assert warmup_range("1d", "5m") == "1mo"
    assert warmup_range("1d", "1m") == "1d"
    assert warmup_range("5y", "1h") == "5y"  # ya pedía más que el calentamiento


# ───────────────────────── API ─────────────────────────


@pytest.fixture
def fake_get_candles(monkeypatch):
    """Simula yfinance: 400 velas diarias; el rango visible son las últimas 100."""
    calls = []
    history = fake_candles(400)

    def get_candles(ticker, range_="6mo", interval="1d"):
        calls.append((ticker, range_, interval))
        return history[-100:] if range_ == "6mo" else history

    monkeypatch.setattr("app.graficador.providers.market_data.get_candles", get_candles)
    return calls


def test_api_catalog(client):
    response = client.get("/api/graficador/indicators")
    assert response.status_code == 200
    data = response.get_json()
    assert {i["id"] for i in data["indicators"]} == {i.id for i in INDICATORS}
    assert data["categories"] == list(CATEGORIES)


def test_api_computes_several_indicators_aligned_with_the_visible_candles(client, fake_get_candles):
    response = client.get("/api/graficador/aapl/indicators?range=6mo&interval=1d&ind=sma:200&ind=rsi:14&ind=macd")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["time"]) == 100
    assert [i["spec"] for i in data["indicators"]] == ["sma:200", "rsi:14", "macd"]
    # La SMA(200) ya tiene valor en la primera vela visible gracias al calentamiento.
    sma = data["indicators"][0]["outputs"]["sma"]
    assert len(sma) == 100 and None not in sma
    # Se pidieron las velas visibles y el historial más largo, con el ticker normalizado.
    assert fake_get_candles == [("AAPL", "6mo", "1d"), ("AAPL", "5y", "1d")]


def test_api_skips_the_extra_download_when_the_range_is_already_the_warmup(client, fake_get_candles):
    client.get("/api/graficador/AAPL/indicators?range=max&interval=1mo&ind=sma:20")
    assert fake_get_candles == [("AAPL", "max", "1mo")]


def test_api_with_no_data_returns_empty_series(client, monkeypatch):
    monkeypatch.setattr("app.graficador.providers.market_data.get_candles", lambda *a, **k: [])
    response = client.get("/api/graficador/ZZZZ/indicators?ind=rsi:14")
    assert response.status_code == 200
    assert response.get_json() == {"time": [], "indicators": [{"spec": "rsi:14", "outputs": {"rsi": []}}]}


@pytest.mark.parametrize(
    "url, message",
    [
        ("/api/graficador/AAPL/indicators", "al menos un indicador"),
        ("/api/graficador/AAPL/indicators?ind=nope", "desconocido"),
        ("/api/graficador/AAPL/indicators?ind=sma:0", "entre"),
        ("/api/graficador/AAPL/indicators?ind=sma:20&range=7y", "inválidos"),
        ("/api/graficador/AAPL/indicators?ind=sma:20&interval=2d", "inválidos"),
        ("/api/graficador/%3Cscript%3E/indicators?ind=sma:20", "ticker"),
        ("/api/graficador/AAPL/indicators?" + "&".join(["ind=sma:20"] * 26), "Máximo"),
    ],
)
def test_api_rejects_invalid_requests_without_downloading_anything(client, monkeypatch, url, message):
    def boom(*a, **k):
        raise AssertionError("no debe descargar datos con una petición inválida")

    monkeypatch.setattr("app.graficador.providers.market_data.get_candles", boom)
    response = client.get(url)
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_warmup_range_for_dukascopy_intervals():
    assert indicators.warmup_range("1d", "1s") == "1d"
    assert indicators.warmup_range("5d", "30s") == "5d"
    assert indicators.warmup_range("5d", "10m") == "1mo"
    assert indicators.warmup_range("1mo", "4h") == "2y"
