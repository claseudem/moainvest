"""Rutas de Insights con datos simulados (sin red)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.market_data import Quote
from app.insights import engine


def _candles(seed: int, n: int = 300):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-02", periods=n, tz="America/New_York")
    closes = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    return [{"time": int(ts.timestamp()), "open": c, "high": c, "low": c, "close": float(c), "volume": 0}
            for ts, c in zip(index, closes)]


@pytest.fixture(autouse=True)
def fake_market(monkeypatch):
    engine.clear_cache()
    monkeypatch.setattr(
        "app.insights.data.market_data.get_candles",
        lambda ticker, **k: [] if ticker == "NODATA" else _candles(sum(map(ord, ticker))),
    )
    monkeypatch.setattr(
        "app.insights.data.market_data.get_quote",
        lambda ticker: Quote(ticker, ticker, 4.2, 4.2, 0, 0),
    )
    yield
    engine.clear_cache()


def test_empty_state(client):
    response = client.get("/app/insights/")
    assert response.status_code == 200
    assert "Empieza por aquí".encode() in response.data
    assert "no constituye asesoría de inversión".encode() in response.data
    assert b"insights.css" in response.data and b'class="sidebar"' in response.data


def test_asset_analysis(client):
    response = client.get("/app/insights/?ticker=aapl")
    assert response.status_code == 200
    body = response.data
    for text in ("¿Cómo voy?", "¿Por qué?", "Modo experto", "por cada $100 llegaste a tener", "¿Qué significa?"):
        assert text.encode() in body
    assert b'id="insights-equity"' in body and b'id="insights-drawdown"' in body and b"insights-heatmap" in body
    assert b"4.2% anual" in body  # rf actual de ^IRX, visible
    assert b"Traceback" not in body


def test_portfolio_and_crypto(client):
    response = client.get("/app/insights/?ticker=SPY:60,TLT:40&benchmark=QQQ")
    assert response.status_code == 200
    assert "SPY 60% · TLT 40%".encode() in response.data
    response = client.get("/app/insights/?ticker=BTC-USD")
    assert response.status_code == 200
    assert "calendario bursátil".encode() in response.data


def test_friendly_errors(client):
    bad = client.get("/app/insights/?ticker=%24%24%24")
    assert bad.status_code == 400 and "No pudimos hacer el análisis".encode() in bad.data
    assert client.get("/app/insights/?ticker=AAPL&rf=abc").status_code == 400
    missing = client.get("/app/insights/?ticker=NODATA")
    assert missing.status_code == 200 and "no devolvió precios".encode() in missing.data
