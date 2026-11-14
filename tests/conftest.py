import pytest

from app import create_app
from config import TestingConfig


@pytest.fixture()
def app():
    return create_app(TestingConfig)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture
def fake_uec(monkeypatch):
    from tests.quant_stats.test_quant import _fake_candles, _fake_earnings

    # El benchmark necesita datos distintos: quantstats cachea resampleos por contenido.
    monkeypatch.setattr(
        "app.quant_stats.quant.market_data.get_candles",
        lambda ticker, **k: _fake_candles(400 if ticker != "UEC" else 420),
    )
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_earnings", lambda *a, **k: _fake_earnings())
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_display_name", lambda ticker: f"Nombre {ticker}")
