import datetime

import pytest

from app.quant_stats import quant

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
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_candles", lambda *a, **k: [])
    assert quant.render_qs_plot("UEC", "2y", "snapshot").startswith(b"\x89PNG")


def test_tearsheet_html(fake_market):
    html = quant.tearsheet_html("UEC", "2y", benchmark="SPY")
    assert "UEC · Tearsheet" in html


def test_tearsheet_none_without_data(monkeypatch):
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_candles", lambda *a, **k: [])
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


# --------------------------------------------------------------------------
# Tema de marca MOAINVEST en las gráficas (app.core.charts)
# --------------------------------------------------------------------------


@pytest.fixture()
def captured_figures(monkeypatch):
    """Guarda las figuras que se convierten a PNG para inspeccionar sus colores."""
    figures = []
    original = quant._to_png

    def capture(fig, *args, **kwargs):
        figures.append(fig)
        return original(fig, *args, **kwargs)

    monkeypatch.setattr(quant, "_to_png", capture)
    return figures


@pytest.fixture()
def market_with_benchmark(monkeypatch):
    # Datos distintos para el benchmark (quantstats cachea por contenido).
    monkeypatch.setattr(
        quant.market_data, "get_candles", lambda ticker, **k: _fake_candles(400 if ticker == "SPY" else 420)
    )
    monkeypatch.setattr(quant.market_data, "get_earnings", lambda *a, **k: _fake_earnings())


def _hex(color) -> str:
    from matplotlib.colors import to_hex

    return to_hex(color)


def _line_colors(fig) -> set[str]:
    return {_hex(line.get_color()) for ax in fig.axes for line in ax.get_lines()}


@pytest.mark.parametrize(
    "render",
    [
        lambda: quant.render_qs_plot("UEC", "2y", "returns", benchmark="SPY"),
        lambda: quant.render_qs_plot("UEC", "2y", "snapshot"),
        lambda: quant.render_qs_plot("UEC", "2y", "drawdowns-periods"),
        lambda: quant.render_montecarlo_chart("UEC", "2y", sims=250),
        lambda: quant.render_drawdown_chart("UEC"),
        lambda: quant.render_monthly_heatmap("UEC"),
        lambda: quant.render_earnings_chart("UEC"),
    ],
)
def test_charts_use_the_light_brand_theme(market_with_benchmark, captured_figures, render):
    from app.core.charts import PAPER

    render()
    fig = captured_figures[-1]
    assert _hex(fig.get_facecolor()) == PAPER
    assert all(_hex(ax.get_facecolor()) == PAPER for ax in fig.axes)
    # Ninguna línea con los colores propios de quantstats (azul, amarillo, rojo puro).
    quantstats_colors = {"#fedd78", "#348dc1", "#ba516b", "#4fa487", "#003366", "#ff0000"}
    assert not _line_colors(fig) & quantstats_colors


def test_benchmark_plot_paints_asset_in_brand_red_and_benchmark_in_grey(market_with_benchmark, captured_figures):
    from app.core.charts import BRAND, MUTED

    quant.render_qs_plot("UEC", "2y", "returns", benchmark="SPY")
    # quantstats dibuja primero el benchmark y después el activo (las etiquetas
    # dependen de su caché interna, así que se comprueba el orden).
    benchmark, asset = [_hex(line.get_color()) for line in captured_figures[-1].axes[0].get_lines()][:2]
    assert benchmark == MUTED
    assert asset == BRAND


def test_montecarlo_replaces_quantstats_fixed_colors(fake_market, captured_figures):
    from app.core.charts import INK, UP

    quant.render_montecarlo_chart("FAKE", "2y", sims=250)
    lines = {line.get_label(): _hex(line.get_color()) for line in captured_figures[-1].axes[0].get_lines()}
    assert lines["Original"] == INK
    assert lines["Goal (50%)"] == UP


@pytest.mark.parametrize(
    "render",
    [
        lambda: quant.render_qs_plot("UEC", "2y", "monthly-heatmap"),
        lambda: quant.render_monthly_heatmap("UEC"),
    ],
)
def test_monthly_heatmaps_use_the_brand_diverging_map(fake_market, captured_figures, render):
    render()
    meshes = [c for ax in captured_figures[-1].axes if ax.texts for c in ax.collections]
    assert meshes and all(mesh.cmap is quant.HEATMAP_CMAP for mesh in meshes)


def test_brand_theme_restores_global_state(market_with_benchmark):
    import matplotlib
    import matplotlib.pyplot as plt

    facecolor = matplotlib.rcParams["axes.facecolor"]
    core_colors = list(quant._qs_core._FLATUI_COLORS)
    wrapper_colors = list(quant._qs_wrappers._FLATUI_COLORS)
    quant.render_qs_plot("UEC", "2y", "returns", benchmark="SPY")
    assert quant._qs_core._plt is plt and quant._qs_wrappers._plt is plt
    assert list(quant._qs_core._FLATUI_COLORS) == core_colors
    assert list(quant._qs_wrappers._FLATUI_COLORS) == wrapper_colors
    assert matplotlib.rcParams["axes.facecolor"] == facecolor


def test_concurrent_renders_do_not_mix_figures(market_with_benchmark):
    from concurrent.futures import ThreadPoolExecutor

    slugs = ["returns", "snapshot", "drawdown", "monthly-heatmap"] * 2
    with ThreadPoolExecutor(max_workers=4) as pool:
        pngs = list(pool.map(lambda slug: quant.render_qs_plot("UEC", "2y", slug, benchmark="SPY"), slugs))
    assert all(png.startswith(PNG_SIGNATURE) for png in pngs)
    assert pngs[:4] == pngs[4:]  # misma gráfica, mismos bytes: nada se ha cruzado


def test_tearsheet_gets_the_brand_css(fake_market):
    head = quant.tearsheet_html("UEC", "2y").split("</head>", 1)[0]
    assert 'id="moainvest-brand"' in head
    assert "Geist" in head
    assert quant.BRAND in head


def test_brand_tearsheet_without_head_is_unchanged():
    assert quant.brand_tearsheet("<p>x</p>") == "<p>x</p>"


def test_quant_stats_has_no_old_tradingview_colors():
    """Las gráficas usan los colores de app.core.charts, no el azul/verde de antes."""
    from pathlib import Path

    sources = [p for p in Path(quant.__file__).parent.rglob("*") if p.suffix in {".py", ".html", ".js", ".css"}]
    assert sources
    for path in sources:
        text = path.read_text(encoding="utf-8").lower()
        for old in ("#2962ff", "#26a69a", "#ef5350"):
            assert old not in text, f"{old} en {path}"


def test_asset_facts_summarise_the_returns(fake_market):
    returns = quant.daily_returns("FAKE")
    facts = quant.asset_facts("FAKE", returns, window=63)
    metrics = quant.performance_metrics(returns)
    assert facts.enough
    assert facts.ticker == "FAKE" and facts.trading_days == returns.size
    assert facts.cumulative_return == pytest.approx(metrics.cumulative_return)
    assert facts.max_drawdown == pytest.approx(metrics.max_drawdown)
    assert facts.drawdowns and facts.drawdowns[0].depth == pytest.approx(metrics.max_drawdown, abs=1e-3)
    assert facts.start == "enero de 2025" and facts.end == "febrero de 2026"
    assert facts.months_total == 14 and 0 <= facts.months_positive <= 14
    assert [year for year, _ in facts.yearly] == [2025, 2026]
    assert facts.rolling_window_label == "3 meses" and facts.rolling_sharpe is not None


def test_asset_facts_none_without_data():
    import pandas as pd

    assert quant.asset_facts("FAKE", pd.Series(dtype=float)) is None


def test_benchmark_facts_beta_and_correlation(fake_market):
    returns = quant.daily_returns("FAKE")
    bench = returns * 0.5
    relation = quant.benchmark_facts("SPY", returns, bench)
    assert relation.facts.ticker == "SPY"
    assert relation.beta == pytest.approx(2.0)
    assert relation.correlation == pytest.approx(1.0)
