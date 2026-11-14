"""Rutas de la app "Graficador" y el contrato de datos que consume su JS."""
import re
from pathlib import Path

import pandas as pd
import pytest

from app.core import market_data
from app.core.api import ALLOWED_INTERVALS, ALLOWED_RANGES
from app.core.navigation import APPS
from app.core.watchlists import default_watchlist
from app.graficador.views import CHART_RANGES

ROOT = Path(__file__).resolve().parents[2]


def test_page_with_ticker(client):
    response = client.get("/app/graficador/?ticker=aapl")
    assert response.status_code == 200
    assert b'data-ticker="AAPL"' in response.data
    assert b'id="graficador-chart"' in response.data
    assert b'id="graficador-legend"' in response.data
    assert b"graficador.js" in response.data
    assert "Graficador · MoaiInvest".encode() in response.data
    # Selector de rangos y de tipo de serie.
    for label in ("1D", "5D", "1M", "6M", "1A", "5A", "Todo"):
        assert f">{label}</button>".encode() in response.data
    for series_type in ("candles", "line", "area"):
        assert f'data-series-type="{series_type}"'.encode() in response.data


def test_page_defaults_to_first_symbol_of_default_watchlist(client):
    ticker = default_watchlist().symbols[0].ticker
    response = client.get("/app/graficador/")
    assert response.status_code == 200
    assert f'data-ticker="{ticker}"'.encode() in response.data


@pytest.mark.parametrize("ticker", ["<script>", "AAPL MSFT", "X" * 21])
def test_invalid_ticker_shows_error(client, ticker):
    response = client.get("/app/graficador/", query_string={"ticker": ticker})
    assert response.status_code == 400
    assert b'id="graficador-error"' in response.data
    assert "no es un ticker válido".encode() in response.data
    assert b'data-ticker=""' in response.data
    assert b"graficador.js" not in response.data


def test_invalid_ticker_is_escaped(client):
    response = client.get("/app/graficador/", query_string={"ticker": "<script>"})
    assert b"<SCRIPT>" not in response.data
    assert b"&lt;SCRIPT&gt;" in response.data


def test_sidebar_marks_graficador_as_active(client):
    page = client.get("/app/graficador/").get_data(as_text=True)
    assert re.search(r'sidebar__app is-active">\s*<a class="sidebar__app-header" href="/app/graficador/"', page)


def test_graficador_replaces_graficas_in_sidebar():
    endpoints = [a.endpoint for a in APPS]
    assert "graficador.index" in endpoints
    assert "moainvest.graficas" not in endpoints


def test_graficador_tabs_share_the_ticker_with_quant_stats(client):
    page = client.get("/app/graficador/?ticker=msft").get_data(as_text=True)
    tabs = page.split('<nav class="app-tabs"', 1)[1].split("</nav>", 1)[0]
    assert 'aria-current="page">Gráfico</a>' in tabs
    assert 'href="/app/graficador/quant-stats/fundamentales?ticker=MSFT"' in tabs
    assert 'href="/app/graficador/quant-stats/revision?ticker=MSFT"' in tabs
    # Atajo bajo el gráfico al análisis del mismo activo.
    assert 'class="graficador__quant" href="/app/graficador/quant-stats/fundamentales?ticker=MSFT"' in page
    # El sidebar muestra las mismas subsecciones; Quant stats no es una app aparte.
    sidebar = page.split('<aside class="sidebar"', 1)[1].split("</aside>", 1)[0]
    assert '<span class="sidebar__section-name">Quant stats</span>' in sidebar
    assert '<span class="sidebar__app-name">Quant stats</span>' not in sidebar


def test_graficador_controls_are_grouped_with_labels(client):
    page = client.get("/app/graficador/?ticker=AAPL").get_data(as_text=True)
    toolbar = page.split('<div class="graficador__toolbar">', 1)[1].split('<div class="graficador__chart-wrap">', 1)[0]
    assert ">Período</span>" in toolbar and ">Vista</span>" in toolbar
    assert 'id="graficador-indicators-btn"' in toolbar and 'id="graficador-provider"' in toolbar


def test_invalid_ticker_tabs_do_not_carry_it(client):
    page = client.get("/app/graficador/", query_string={"ticker": "<script>"}).get_data(as_text=True)
    assert 'href="/app/graficador/quant-stats/fundamentales"' in page
    assert "graficador__quant" not in page


def test_chart_ranges_are_accepted_by_candles_api():
    for r in CHART_RANGES:
        assert r["range"] in ALLOWED_RANGES and r["interval"] in ALLOWED_INTERVALS


def test_candles_api_includes_volume(client, monkeypatch):
    market_data._cache.clear()
    index = pd.date_range("2026-01-01", periods=3, freq="D", tz="UTC")
    history = pd.DataFrame(
        {"Open": [1.0, 2.0, 3.0], "High": [2.0, 3.0, 4.0], "Low": [0.5, 1.5, 2.5], "Close": [1.5, 2.5, 3.5], "Volume": [10, 20, 30]},
        index=index,
    )

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, period, interval):
            return history

    monkeypatch.setattr("app.core.market_data.yf.Ticker", FakeTicker)
    response = client.get("/api/candles/AAPL?range=1mo&interval=1h")
    assert response.status_code == 200
    candles = response.get_json()
    assert [c["volume"] for c in candles] == [10, 20, 30]
    assert set(candles[0]) == {"time", "open", "high", "low", "close", "volume"}


def test_vendored_lightweight_charts_is_v5_and_js_uses_v5_api():
    vendor = ROOT / "app/core/static/js/vendor/lightweight-charts.standalone.production.js"
    assert "Lightweight Charts™ v5." in vendor.read_text(encoding="utf-8")[:300]
    v4_calls = re.compile(r"\.(addCandlestickSeries|addLineSeries|addAreaSeries|addHistogramSeries|addBarSeries|addBaselineSeries|setMarkers)\(")
    for js in (ROOT / "app").rglob("*.js"):
        if "vendor" in js.parts:
            continue
        assert not v4_calls.search(js.read_text(encoding="utf-8")), js


def test_page_has_brand_header(client):
    page = client.get("/app/graficador/?ticker=%5EGSPC").data
    # Eyebrow con el mercado (el JS le antepone la watchlist), nombre, precio y pill.
    assert b'id="graficador-eyebrow"' in page
    assert "Índice".encode() in page
    assert b'data-watchlists-url="/api/watchlists"' in page
    for element_id in ("graficador-name", "graficador-symbol", "graficador-price", "graficador-change"):
        assert f'id="{element_id}"'.encode() in page
    # Rangos en rojo de marca y tipo de serie en negro.
    assert b'class="graficador__group graficador__group--ink"' in page
    # Estados de carga, error y "sin datos" en una tarjeta sobre el gráfico.
    assert b'id="graficador-overlay" hidden' in page
    assert b'id="graficador-status" role="status"' in page


def test_invalid_ticker_keeps_search_form(client):
    response = client.get("/app/graficador/", query_string={"ticker": "AAPL MSFT"})
    assert b'id="graficador-search"' in response.data
    assert b'id="graficador-quote"' not in response.data
    assert b'id="graficador-ranges"' not in response.data


def test_js_fallbacks_use_brand_colors_not_old_dark_theme():
    js = (ROOT / "app/graficador/static/graficador.js").read_text(encoding="utf-8").lower()
    for old in ("#131a24", "#2962ff", "#26a69a", "#232c3a", "#7c8a9e", "#ef5350"):
        assert old not in js, old
    for brand in ("#ffffff", "#e6e4df", "#6b6b6b", "#171717", "#c8102e", "#fbeef0", "#0f8a5f"):
        assert brand in js, brand
    assert "geist mono" in js


def test_css_uses_brand_tokens():
    css = (ROOT / "app/graficador/static/graficador.css").read_text(encoding="utf-8")
    for token in ("var(--brand)", "var(--ink)", "var(--line)", "var(--paper)", "var(--radius-pill)", "var(--font-mono)"):
        assert token in css, token
    assert "rgba(19, 26, 36" not in css
