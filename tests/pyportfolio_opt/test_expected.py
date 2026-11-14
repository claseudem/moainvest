import datetime

import pytest

from app.pyportfolio_opt import expected


def _fake_candles(days=400, daily_return=0.001, start=datetime.datetime(2024, 1, 1)):
    """Cierres diarios sintéticos que crecen a un ritmo constante (sin Yahoo)."""
    candles = []
    price = 100.0
    date = start
    while len(candles) < days:
        date += datetime.timedelta(days=1)
        if date.weekday() >= 5:  # fin de semana: sin sesión
            continue
        candles.append(
            {"time": int(date.timestamp()), "open": price, "high": price, "low": price, "close": price, "volume": 1000}
        )
        price *= 1 + daily_return
    return candles


@pytest.fixture
def fake_prices(monkeypatch):
    data = {
        "UP": _fake_candles(daily_return=0.001),
        "DOWN": _fake_candles(daily_return=-0.0005),
        "SHORT": _fake_candles(days=120, daily_return=0.002, start=datetime.datetime(2025, 1, 1)),
    }
    monkeypatch.setattr(expected.market_data, "get_candles", lambda ticker, **k: data.get(ticker, []))
    return data


def test_load_prices_builds_one_column_per_ticker(fake_prices):
    prices = expected.load_prices(["UP", "SHORT", "NADA"])
    assert list(prices.columns) == ["UP", "SHORT"]
    assert prices.index.is_monotonic_increasing
    assert prices["UP"].count() == 400
    # El activo con menos historia queda con NaN al principio.
    assert prices["SHORT"].count() == 120


def test_historical_return_is_the_annualized_growth_rate(fake_prices):
    result = expected.compute_expected_returns(["UP", "DOWN"], methods=("historical",))
    returns = {a.ticker: a.returns["historical"] for a in result.assets}
    # Con capitalización: (1 + r) ** 252 - 1 para un retorno diario constante.
    assert returns["UP"] == pytest.approx(1.001**252 - 1, rel=1e-6)
    assert returns["DOWN"] == pytest.approx(0.9995**252 - 1, rel=1e-6)


def test_simple_mean_without_compounding(fake_prices):
    result = expected.compute_expected_returns(["UP"], methods=("historical",), compounding=False)
    assert result.assets[0].returns["historical"] == pytest.approx(0.001 * 252, rel=1e-6)


def test_ema_matches_constant_returns(fake_prices):
    result = expected.compute_expected_returns(["UP"], methods=("ema",), span=60)
    assert result.assets[0].returns == {"ema": pytest.approx(1.001**252 - 1, rel=1e-6)}


def test_both_methods_and_missing_tickers(fake_prices):
    result = expected.compute_expected_returns(["UP", "SHORT", "NADA"])
    assert result.methods == ("historical", "ema")
    assert [a.ticker for a in result.assets] == ["UP", "SHORT"]
    assert result.missing == ["NADA"]
    short = result.assets[1]
    assert short.observations == 120
    # Cada activo usa su propia historia, no la del más largo.
    assert short.returns["historical"] == pytest.approx(1.002**252 - 1, rel=1e-6)

    data = result.to_dict()
    assert data["frequency"] == 252
    assert data["methods"] == [{"id": "historical", "name": "Media histórica"}, {"id": "ema", "name": "EMA"}]
    assert set(data["assets"][0]) == {"ticker", "observations", "start", "end", "historical", "ema"}


def test_raises_when_no_ticker_has_prices(fake_prices):
    with pytest.raises(expected.ExpectedReturnsError):
        expected.compute_expected_returns(["NADA", "OTRO"])


def test_render_chart_returns_png_without_touching_global_theme(fake_prices):
    import matplotlib

    before = dict(matplotlib.rcParams)
    result = expected.compute_expected_returns(["UP", "DOWN"])
    png_bytes = expected.render_expected_returns_chart(result)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert dict(matplotlib.rcParams) == before
