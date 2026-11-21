"""Tests del motor de Insights: validate_returns, alineación con el benchmark,
consistencia con qs.reports.metrics y casos límite."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
import quantstats as qs

from app.insights import engine


def _prices(seed: int, n: int = 600, start: str = "2022-01-03") -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=n)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.012, n)), index=index)


RF = engine.RiskFree(0.04, 252, "test")


# ---------------------------------------------------------------- validate_returns


def test_validate_returns_converts_prices_to_simple_returns():
    prices = pd.Series([100.0, 110.0, 99.0], index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))
    result = engine.validate_returns(prices, name="X")
    assert result.returns.tolist() == pytest.approx([0.10, -0.10])
    assert result.returns.name == "X"
    assert result.report.removed == 0 and result.report.rows_out == 2


def test_validate_returns_cleans_index_tz_order_and_duplicates():
    index = pd.DatetimeIndex(
        ["2024-01-04 05:00", "2024-01-02 05:00", "2024-01-03 05:00", "2024-01-03 05:00"], tz="UTC"
    ).tz_convert("America/New_York")
    prices = pd.Series([121.0, 100.0, 105.0, 110.0], index=index)
    result = engine.validate_returns(prices)
    r = result.returns
    assert r.index.tz is None
    assert r.index.is_monotonic_increasing and not r.index.has_duplicates
    assert result.report.duplicates_removed == 1
    # Se queda el último cierre del día duplicado (110): 100 -> 110 -> 121
    assert r.tolist() == pytest.approx([0.10, 0.10])


def test_validate_returns_drops_nan_inf_and_counts_them():
    idx = pd.bdate_range("2024-01-01", periods=6)
    prices = pd.Series([100, np.nan, 102, np.inf, 0, 104], index=idx, dtype=float)
    result = engine.validate_returns(prices)
    assert result.report.invalid_prices_removed == 3
    assert result.returns.tolist() == pytest.approx([0.02, 104 / 102 - 1])
    assert np.isfinite(result.returns).all()

    returns = pd.Series([0.01, np.nan, np.inf, -0.02], index=idx[:4])
    result = engine.validate_returns(returns, input_kind="returns")
    assert (result.report.nan_removed, result.report.inf_removed) == (1, 1)
    assert result.returns.tolist() == pytest.approx([0.01, -0.02])


# ---------------------------------------------------------------- benchmark


def test_align_with_benchmark_is_an_exact_inner_join():
    s = engine.validate_returns(_prices(1)).returns
    b = engine.validate_returns(_prices(2)).returns.drop(s.index[10:15])  # huecos en el benchmark
    b = pd.concat([b, pd.Series([0.01], index=[pd.Timestamp("2030-01-01")])])  # fecha sin pareja
    aligned = engine.align_with_benchmark(s, b)
    assert aligned.strategy.index.equals(aligned.benchmark.index)
    assert set(aligned.strategy.index) == set(s.index) & set(b.index)
    assert aligned.strategy_dropped == 5 and aligned.benchmark_dropped == 1


def test_align_trims_leading_zeros_like_quantstats():
    s = engine.validate_returns(_prices(1)).returns
    s.iloc[:3] = 0.0
    aligned = engine.align_with_benchmark(s, engine.validate_returns(_prices(2)).returns)
    assert aligned.leading_trimmed == 3
    assert aligned.strategy.index[0] == s.index[3]


def test_crypto_prices_are_resampled_to_the_stock_calendar():
    crypto = pd.Series(np.arange(1.0, 15.0), index=pd.date_range("2024-01-01", periods=14, freq="D"))
    calendar = pd.bdate_range("2024-01-01", periods=10)
    resampled = engine.resample_prices(crypto, calendar)
    assert resampled.index.equals(calendar)
    # El lunes 8 toma su propio precio (8), no el del viernes.
    assert resampled[pd.Timestamp("2024-01-08")] == 8.0
    assert engine.periods_per_year("BTC-USD") == 365 and engine.periods_per_year("AAPL") == 252


def test_risk_free_per_period_matches_quantstats_deannualization():
    assert RF.per_period == pytest.approx((1.04) ** (1 / 252) - 1)
    r = engine.validate_returns(_prices(3)).returns
    excess = qs.utils.to_excess_returns(r, RF.annual, nperiods=252)
    assert (r - excess).iloc[0] == pytest.approx(RF.per_period)


# ---------------------------------------------------------------- consistencia


def _parse(value: str) -> float:
    return float(value.replace("%", "").replace(",", ""))


def test_values_match_qs_reports_metrics_full():
    """quantstats redondea su tabla a 2 decimales (en % las métricas de
    porcentaje): se comparan nuestros valores con esa misma precisión, con
    tolerancia 1e-6."""
    s = engine.validate_returns(_prices(11), name="AAA").returns
    b = engine.validate_returns(_prices(12), name="SPY").returns
    insight = engine.compute_insight(s, b, RF, label="AAA", benchmark_label="SPY")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = qs.reports.metrics(s, benchmark=b, rf=0.04, mode="full", display=False, compounded=True,
                                   periods_per_year=252, internal=True, strategy_title="AAA", benchmark_title="SPY")

    checks = {
        "Cumulative Return": ("total_return", 100),
        "CAGR﹪": ("cagr", 100),
        "Sharpe": ("sharpe", 1),
        "Sortino": ("sortino", 1),
        "Max Drawdown": ("max_drawdown", 100),
        "Volatility (ann.)": ("volatility", 100),
        "Calmar": ("calmar", 1),
        "Tail Ratio": ("tail_ratio", 1),
    }
    for row, (attr, scale) in checks.items():
        for col, stats in (("AAA", insight.strategy), ("SPY", insight.benchmark)):
            ours = round(getattr(stats, attr) * scale, 2)
            assert abs(ours - _parse(table.loc[row, col])) <= 1e-6, (row, col, ours, table.loc[row, col])

    # VaR/CVaR: quantstats los muestra como -abs(valor).
    assert abs(round(-abs(insight.strategy.var) * 100, 2) - _parse(table.loc["Daily Value-at-Risk", "AAA"])) <= 1e-6
    assert abs(round(-abs(insight.strategy.cvar) * 100, 2) - _parse(table.loc["Expected Shortfall (cVaR)", "AAA"])) <= 1e-6
    # La tabla de la interfaz es la de quantstats, con cada columna en su sitio.
    rows = {m: (a, z) for m, a, z in insight.full_table}
    assert rows["Sharpe"] == (table.loc["Sharpe", "AAA"], table.loc["Sharpe", "SPY"])


# ---------------------------------------------------------------- casos límite


def test_empty_series():
    result = engine.validate_returns(pd.Series(dtype=float))
    assert result.returns.empty and result.report.rows_out == 0
    with pytest.raises(engine.InsightError):
        engine.compute_insight(result.returns, result.returns, RF, label="A", benchmark_label="B")


def test_single_day_has_no_returns():
    one = pd.Series([100.0], index=pd.to_datetime(["2024-01-02"]))
    result = engine.validate_returns(one)
    assert result.returns.empty
    with pytest.raises(engine.InsightError):
        engine.compute_insight(result.returns, engine.validate_returns(_prices(1)).returns, RF,
                               label="A", benchmark_label="B")


def test_all_zero_returns_do_not_crash():
    b = engine.validate_returns(_prices(4, n=40)).returns
    zeros = pd.Series(0.0, index=b.index)
    insight = engine.compute_insight(zeros, b, RF, label="CASH", benchmark_label="SPY")
    assert insight.strategy.total_return == 0
    assert insight.strategy.sharpe is None  # 0/0: sin dato, no un traceback
    assert any(w.title == "Sin movimiento" for w in insight.warnings)


def test_nan_only_series():
    idx = pd.bdate_range("2024-01-01", periods=5)
    result = engine.validate_returns(pd.Series(np.nan, index=idx))
    assert result.returns.empty and result.report.invalid_prices_removed == 5


def test_statistical_warnings():
    short = engine.validate_returns(_prices(5, n=25)).returns
    bench = engine.validate_returns(_prices(6, n=25)).returns
    insight = engine.compute_insight(short, bench, RF, label="A", benchmark_label="B")
    titles = {w.title for w in insight.warnings}
    assert "Muestra corta, los ratios son poco fiables" in titles
    assert {"sortino", "calmar", "tail_ratio"} <= insight.unreliable

    idx = pd.bdate_range("2022-01-03", periods=300)
    rng = np.random.default_rng(9)
    smooth = pd.Series(0.004 + rng.normal(0, 0.001, 300), index=idx)
    insight = engine.compute_insight(smooth, engine.validate_returns(_prices(7, n=301)).returns, RF,
                                     label="A", benchmark_label="B")
    assert insight.strategy.sharpe > 3
    assert any(w.level == "alert" for w in insight.warnings)


def test_cache_reuses_result_per_key():
    engine.clear_cache()
    calls = []
    for _ in range(2):
        engine.cached(("AAPL", "1y", "SPY", None), lambda: calls.append(1) or "ok")
    assert calls == [1]
    engine.clear_cache()
