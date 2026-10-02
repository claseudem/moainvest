import datetime

import pytest

from app.models import quant

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _fake_candles(days=420):
    """~14 meses de precios diarios sintéticos (sin llamar a Yahoo Finance)."""
    candles = []
    price = 10.0
    date = datetime.datetime(2025, 1, 1)
    for i in range(days):
        date += datetime.timedelta(days=1)
        if date.weekday() >= 5:  # fin de semana: sin sesión
            continue
        price *= 1 + (0.02 if i % 3 else -0.03)
        candles.append(
            {"time": int(date.timestamp()), "open": price, "high": price, "low": price, "close": price, "volume": 1000}
        )
    return candles


def _ts(year, month, day):
    return int(datetime.datetime(year, month, day, 10).timestamp())


def _fake_earnings():
    """Del más reciente al más antiguo, como ``market_data.get_earnings``;
    el primero es un reporte futuro todavía sin EPS."""
    return [
        {"time": _ts(2099, 1, 1), "eps_estimate": -0.01, "eps_reported": None, "surprise_percent": None},
        {"time": _ts(2026, 1, 20), "eps_estimate": -0.02, "eps_reported": -0.01, "surprise_percent": 50.0},
        {"time": _ts(2025, 10, 20), "eps_estimate": -0.02, "eps_reported": -0.04, "surprise_percent": -100.0},
        {"time": _ts(2025, 7, 21), "eps_estimate": None, "eps_reported": -0.03, "surprise_percent": None},
        {"time": _ts(2025, 4, 21), "eps_estimate": -0.01, "eps_reported": -0.02, "surprise_percent": -100.0},
        {"time": _ts(2025, 1, 21), "eps_estimate": -0.01, "eps_reported": -0.05, "surprise_percent": -400.0},
    ]


@pytest.fixture()
def fake_market(monkeypatch):
    monkeypatch.setattr(quant.market_data, "get_candles", lambda *a, **k: _fake_candles())
    monkeypatch.setattr(quant.market_data, "get_earnings", lambda *a, **k: _fake_earnings())


def test_performance_metrics(fake_market):
    metrics = quant.performance_metrics(quant.daily_returns("FAKE"))
    assert metrics is not None
    assert metrics.annual_volatility > 0
    assert -1 <= metrics.max_drawdown < 0
    prices = quant.closing_prices("FAKE")
    assert metrics.cumulative_return == pytest.approx(prices.iloc[-1] / prices.iloc[0] - 1)


def test_performance_metrics_none_without_data():
    import pandas as pd

    assert quant.performance_metrics(pd.Series(dtype=float)) is None


def test_monthly_returns_table_blanks_months_outside_history(fake_market):
    table = quant.monthly_returns_table(quant.daily_returns("FAKE"))
    assert list(table.columns)[:1] == ["JAN"]
    # El histórico sintético termina en febrero de 2026: de marzo en adelante no hay datos.
    assert table.loc[2026].iloc[2:].isna().all()
    assert table.loc[2025].notna().all()


def test_last_earnings_are_the_last_published_in_chronological_order(fake_market):
    reports = quant.last_earnings("FAKE", 4)
    assert [r.date.month for r in reports] == [4, 7, 10, 1]  # sin el futuro ni el más antiguo
    assert reports[0].days_since_previous is None
    assert reports[1].days_since_previous == 91
    assert reports[-1].eps_change == pytest.approx(0.03)
    assert all(r.close is not None for r in reports)
    assert all(r.price_change_percent is not None for r in reports[1:])
    assert reports[-1].eps_beat is True
    assert reports[1].eps_beat is None  # sin estimado


@pytest.mark.parametrize(
    "render",
    [quant.render_drawdown_chart, quant.render_monthly_heatmap, quant.render_earnings_chart],
)
def test_charts_return_png_bytes(fake_market, render):
    assert render("FAKE").startswith(PNG_SIGNATURE)


@pytest.mark.parametrize(
    "render",
    [quant.render_drawdown_chart, quant.render_monthly_heatmap, quant.render_earnings_chart],
)
def test_charts_render_without_data(monkeypatch, render):
    monkeypatch.setattr(quant.market_data, "get_candles", lambda *a, **k: [])
    monkeypatch.setattr(quant.market_data, "get_earnings", lambda *a, **k: [])
    assert render("FAKE").startswith(PNG_SIGNATURE)


def test_stats_groups_cover_the_catalog(fake_market):
    groups = quant.stats_groups(quant.daily_returns("UEC", "2y"))
    assert [title for title, _ in groups] == [title for title, _ in quant.STAT_GROUPS]
    metrics = {m.label: m for _, group in groups for m in group}
    # Las métricas de las tarjetas de resumen no se repiten en las tablas.
    assert not {label for label, _, _ in quant.SUMMARY_STATS} & metrics.keys()
    assert metrics["CAGR"].display.endswith("%")
    assert metrics["Máx. días ganadores seguidos"].display.isdigit()


def test_stats_groups_empty_without_data():
    import pandas as pd

    assert quant.stats_groups(pd.Series(dtype=float)) == []


def test_stat_metric_display_handles_missing_values():
    assert quant.StatMetric("x", None, "pct").display == "—"
    assert quant.StatMetric("x", None, "pct").sign == ""
    assert quant.StatMetric("x", -0.1234, "pct").display == "-12.34%"
    assert quant.StatMetric("x", -0.1234, "pct").sign == "is-down"


@pytest.mark.parametrize("slug", [p.slug for p in quant.PLOTS])
def test_every_qs_plot_renders_png(monkeypatch, slug):
    # El benchmark necesita datos distintos: quantstats cachea los resampleos
    # por contenido y dos series idénticas colisionan al unirlas.
    monkeypatch.setattr(
        quant.market_data, "get_candles", lambda ticker, **k: _fake_candles(400 if ticker == "SPY" else 420)
    )
    png = quant.render_qs_plot("UEC", "2y", slug, benchmark="SPY", window=63)
    assert png.startswith(b"\x89PNG")


def test_qs_plot_renders_without_data(monkeypatch):
    monkeypatch.setattr("app.models.quant.market_data.get_candles", lambda *a, **k: [])
    assert quant.render_qs_plot("UEC", "2y", "snapshot").startswith(b"\x89PNG")


def test_tearsheet_html(fake_market):
    html = quant.tearsheet_html("UEC", "2y", benchmark="SPY")
    assert "UEC · Tearsheet" in html


def test_tearsheet_none_without_data(monkeypatch):
    monkeypatch.setattr("app.models.quant.market_data.get_candles", lambda *a, **k: [])
    assert quant.tearsheet_html("UEC", "2y") is None


def test_normalize_ticker():
    assert quant.normalize_ticker(" aapl ") == "AAPL"
    for ticker in ("^GSPC", "BTC-USD", "EURUSD=X", "GC=F", "BRK-B", "WALMEX.MX"):
        assert quant.normalize_ticker(ticker) == ticker
    for bad in (None, "", "<script>", "A B", "X" * 20):
        assert quant.normalize_ticker(bad) is None


def test_asset_name_prefers_watchlist_label(monkeypatch):
    monkeypatch.setattr(quant.market_data, "get_display_name", lambda ticker: f"yahoo {ticker}")
    assert quant.asset_name("UEC") == "Uranium Energy Corp"
    assert quant.asset_name("ZZZZ") == "yahoo ZZZZ"


def test_montecarlo_summary(fake_market):
    returns = quant.daily_returns("FAKE", "2y")
    summary = quant.montecarlo_summary(returns, sims=250, bust=-0.2, goal=0.5)
    assert summary.sims == 250
    assert 0 <= summary.bust_probability <= 1
    # Barajar no cambia el retorno final: goal es 0% o 100%.
    assert summary.goal_probability in (0.0, 1.0)
    assert summary.terminal["median"] == pytest.approx(quant.performance_metrics(returns).cumulative_return)
    assert summary.max_drawdown["percentile_5"] <= summary.max_drawdown["median"] <= 0
    # Semilla fija: mismas simulaciones en la página y en la gráfica.
    assert quant.montecarlo_summary(returns, sims=250) == quant.montecarlo_summary(returns, sims=250)


def test_montecarlo_summary_none_without_data():
    import pandas as pd

    assert quant.montecarlo_summary(pd.Series(dtype=float)) is None


def test_montecarlo_chart_is_png(fake_market):
    assert quant.render_montecarlo_chart("FAKE", "2y", sims=250).startswith(b"\x89PNG")


def test_compare_stats_puts_asset_and_benchmark_side_by_side(monkeypatch):
    monkeypatch.setattr(
        quant.market_data, "get_candles", lambda ticker, **k: _fake_candles(400 if ticker == "SPY" else 420)
    )
    returns = quant.daily_returns("UEC", "2y")
    groups = quant.compare_stats(returns, quant.benchmark_returns("SPY", "2y", returns.index))
    assert groups[0][0] == "Resumen"
    first = groups[0][1][0]
    assert first.label == "Retorno acumulado"
    assert first.asset.value != first.benchmark.value


def test_absolute_plots_exclude_benchmark_only_plots():
    assert all(not p.requires_benchmark for p in quant.ABSOLUTE_PLOTS)
    assert "rolling-beta" in {p.slug for p in quant.BENCHMARK_PLOTS}
