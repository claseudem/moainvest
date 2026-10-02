"""Modelo de análisis cuantitativo con ``quantstats``: métricas de rendimiento
y riesgo, drawdown, heatmap de retornos mensuales y comparación de los
últimos reportes de resultados (earnings).

También expone los 3 módulos principales de quantstats tal cual:

- ``stats``: catálogo agrupado de métricas (``stats_groups``).
- ``plots``: catálogo de gráficas nativas de quantstats (``PLOTS`` y
  ``render_qs_plot``), con benchmark y ventana móvil opcionales.
- ``reports``: tearsheet HTML completo (``tearsheet_html``).

Además, la simulación Monte Carlo de ``quantstats.stats.montecarlo``
(``montecarlo_summary`` / ``render_montecarlo_chart``) y la comparación de
métricas entre un activo y su benchmark (``compare_stats``). Todo funciona
con cualquier ticker de Yahoo Finance (``normalize_ticker``).

Igual que ``analysis``, reutiliza los datos ya descargados/cacheados por
``market_data`` y genera las gráficas en el servidor como PNG.
"""
from __future__ import annotations

import io
import os
import re
import tempfile
import threading
import time
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")  # backend sin display: obligatorio en un servidor

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import quantstats as qs
import seaborn as sns
from matplotlib.colors import TwoSlopeNorm

from app.models import market_data
from app.models.analysis import _PALETTE

UP_COLOR = "#0F8A5F"
DOWN_COLOR = "#D93025"
MONTH_LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# --------------------------------------------------------------------------
# Activos
# --------------------------------------------------------------------------

# Tickers de Yahoo Finance: letras, dígitos y los símbolos de índices (^GSPC),
# divisas (EURUSD=X), futuros (GC=F), clases de acciones (BRK-B) y mercados (.MX).
_TICKER_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,14}$")


def normalize_ticker(value: str | None) -> str | None:
    """Ticker en mayúsculas si tiene un formato válido; ``None`` si no."""
    ticker = (value or "").strip().upper()
    return ticker if _TICKER_RE.match(ticker) else None


def asset_name(ticker: str) -> str:
    """Nombre del activo: la etiqueta de las watchlists o, si no está, la de Yahoo Finance."""
    from app.models.watchlists import WATCHLISTS

    for watchlist in WATCHLISTS:
        for symbol in watchlist.symbols:
            if symbol.ticker == ticker and symbol.label:
                return symbol.label
    return market_data.get_display_name(ticker)


# --------------------------------------------------------------------------
# Series de precios / retornos
# --------------------------------------------------------------------------


def closing_prices(ticker: str, period: str = "2y") -> pd.Series:
    """Precios de cierre diarios de ``ticker``, indexados por fecha (sin hora)."""
    candles = market_data.get_candles(ticker, range_=period, interval="1d")
    if not candles:
        return pd.Series(dtype=float)
    df = pd.DataFrame(candles)
    index = pd.to_datetime(df["time"], unit="s").dt.normalize()
    prices = pd.Series(df["close"].to_numpy(), index=pd.DatetimeIndex(index), name=ticker)
    return prices.sort_index()


def daily_returns(ticker: str, period: str = "2y") -> pd.Series:
    """Retornos diarios simples de ``ticker`` en el período indicado."""
    return closing_prices(ticker, period).pct_change().dropna()


# --------------------------------------------------------------------------
# Métricas
# --------------------------------------------------------------------------


@dataclass(slots=True)
class PerformanceMetrics:
    """Métricas de rendimiento/riesgo calculadas con ``quantstats.stats``.

    Sharpe y Sortino se calculan con tasa libre de riesgo 0 y anualizados a
    252 sesiones (los valores por defecto de quantstats).
    """

    start: str
    end: str
    trading_days: int
    cumulative_return: float
    annual_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def performance_metrics(returns: pd.Series) -> PerformanceMetrics | None:
    if returns.empty:
        return None
    return PerformanceMetrics(
        start=returns.index[0].strftime("%Y-%m-%d"),
        end=returns.index[-1].strftime("%Y-%m-%d"),
        trading_days=int(returns.size),
        cumulative_return=float(qs.stats.comp(returns)),
        annual_volatility=float(qs.stats.volatility(returns)),
        sharpe=float(qs.stats.sharpe(returns)),
        sortino=float(qs.stats.sortino(returns)),
        max_drawdown=float(qs.stats.max_drawdown(returns)),
    )


def monthly_returns_table(returns: pd.Series) -> pd.DataFrame:
    """Tabla año x mes (en fracción) de ``quantstats.stats.monthly_returns``.

    quantstats rellena con 0 los meses sin datos; aquí se dejan como NaN
    los meses fuera del rango del histórico para no confundirlos con meses
    planos en el heatmap.
    """
    table = qs.stats.monthly_returns(returns, eoy=False).astype(float)
    table.index = table.index.astype(int)  # quantstats devuelve los años como texto
    first, last = returns.index[0].to_period("M"), returns.index[-1].to_period("M")
    for year in table.index:
        for month_number, column in enumerate(table.columns, start=1):
            if not first <= pd.Period(year=year, month=month_number, freq="M") <= last:
                table.loc[year, column] = np.nan
    return table


# --------------------------------------------------------------------------
# Earnings
# --------------------------------------------------------------------------


@dataclass(slots=True)
class EarningsReport:
    """Un reporte de resultados, comparado con el reporte anterior."""

    date: pd.Timestamp
    eps_estimate: float | None
    eps_reported: float
    surprise_percent: float | None
    close: float | None  # cierre de la primera sesión tras el reporte
    days_since_previous: int | None = None
    eps_change: float | None = None  # EPS reportado vs. el del reporte anterior
    price_change_percent: float | None = None  # cierre vs. el del reporte anterior

    @property
    def label(self) -> str:
        return f"{self.date.day:02d} {MONTH_LABELS[self.date.month - 1]} {self.date.year}"

    @property
    def eps_beat(self) -> bool | None:
        if self.eps_estimate is None:
            return None
        return self.eps_reported >= self.eps_estimate


def last_earnings(ticker: str, count: int = 4) -> list[EarningsReport]:
    """Los últimos ``count`` reportes ya publicados (con EPS real), en orden
    cronológico, con la distancia (días, EPS y precio) respecto al anterior.
    """
    now = time.time()
    published = [
        e for e in market_data.get_earnings(ticker) if e["eps_reported"] is not None and e["time"] <= now
    ][:count]
    published.reverse()  # del más antiguo al más reciente
    if not published:
        return []

    prices = closing_prices(ticker, "2y")
    reports: list[EarningsReport] = []
    for item in published:
        date = pd.Timestamp(item["time"], unit="s").normalize()
        reports.append(
            EarningsReport(
                date=date,
                eps_estimate=item["eps_estimate"],
                eps_reported=item["eps_reported"],
                surprise_percent=item["surprise_percent"],
                close=_close_on_or_after(prices, date),
            )
        )

    for previous, current in zip(reports, reports[1:]):
        current.days_since_previous = (current.date - previous.date).days
        current.eps_change = current.eps_reported - previous.eps_reported
        if previous.close and current.close is not None:
            current.price_change_percent = (current.close / previous.close - 1) * 100
    return reports


def _close_on_or_after(prices: pd.Series, date: pd.Timestamp) -> float | None:
    after = prices[prices.index >= date]
    return float(after.iloc[0]) if not after.empty else None


# --------------------------------------------------------------------------
# Gráficas (PNG)
# --------------------------------------------------------------------------


def render_drawdown_chart(ticker: str, period: str = "2y") -> bytes:
    returns = daily_returns(ticker, period)
    fig, ax = plt.subplots(figsize=(10, 3.6))
    if returns.empty:
        _no_data(ax, ticker)
    else:
        drawdown = qs.stats.to_drawdown_series(returns) * 100
        ax.fill_between(drawdown.index, drawdown.to_numpy(), 0, color=DOWN_COLOR, alpha=0.35)
        ax.plot(drawdown.index, drawdown.to_numpy(), color=DOWN_COLOR, linewidth=1)
        worst = drawdown.idxmin()
        ax.annotate(
            f"Máx. drawdown {drawdown.min():.1f}%",
            xy=(worst, drawdown.min()),
            xytext=(-10, -4),
            textcoords="offset points",
            ha="right",
            va="top",
            fontsize=9,
        )
        ax.set_ylabel("Drawdown (%)")
        ax.set_title(f"{ticker} · Drawdown desde máximos")
        ax.set_xlim(drawdown.index[0], drawdown.index[-1])
    return _to_png(fig)


def render_monthly_heatmap(ticker: str, period: str = "2y") -> bytes:
    returns = daily_returns(ticker, period)
    if returns.empty:
        fig, ax = plt.subplots(figsize=(10, 3))
        _no_data(ax, ticker)
        return _to_png(fig)

    table = monthly_returns_table(returns) * 100
    table.columns = MONTH_LABELS
    fig, ax = plt.subplots(figsize=(10, 0.7 * len(table) + 1.4))
    limit = max(1.0, float(np.nanmax(np.abs(table.to_numpy()))))
    sns.heatmap(
        table,
        ax=ax,
        annot=True,
        fmt=".1f",
        cmap="RdYlGn",
        norm=TwoSlopeNorm(vcenter=0, vmin=-limit, vmax=limit),
        linewidths=0.5,
        cbar_kws={"label": "Retorno mensual (%)"},
    )
    ax.set_title(f"{ticker} · Retornos mensuales (%)")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="y", rotation=0)
    return _to_png(fig)


def render_earnings_chart(ticker: str, count: int = 4) -> bytes:
    """Dos paneles: (1) EPS estimado vs. reportado de cada reporte, con la
    variación de EPS entre reportes consecutivos; (2) precio de cierre con
    cada reporte marcado y la variación de precio y días entre uno y otro.
    """
    reports = last_earnings(ticker, count)
    fig, (ax_eps, ax_price) = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1, 1.4]})
    if not reports:
        _no_data(ax_eps, ticker)
        _no_data(ax_price, ticker)
        return _to_png(fig)

    _plot_eps(ax_eps, reports)
    _plot_price_between_earnings(ax_price, ticker, reports)
    fig.suptitle(f"{ticker} · Últimos {len(reports)} reportes de resultados")
    return _to_png(fig, rect=(0, 0, 1, 0.94))


def _plot_eps(ax, reports: list[EarningsReport]) -> None:
    x = np.arange(len(reports))
    width = 0.38
    estimates = [r.eps_estimate if r.eps_estimate is not None else np.nan for r in reports]
    reported = [r.eps_reported for r in reports]

    ax.bar(x - width / 2, estimates, width, label="EPS estimado", color=_PALETTE[4])
    ax.bar(
        x + width / 2,
        reported,
        width,
        label="EPS reportado",
        color=[UP_COLOR if r.eps_beat in (True, None) else DOWN_COLOR for r in reports],
    )
    ax.axhline(0, color="#555", linewidth=0.8)

    # Distancia entre un reporte y el siguiente: línea que une los EPS
    # reportados, anotada con la variación.
    ax.plot(x + width / 2, reported, color=_PALETTE[0], marker="o", linewidth=1.5, label="Evolución EPS")
    for i in range(1, len(reports)):
        change = reports[i].eps_change
        mid_x = (x[i - 1] + x[i]) / 2 + width / 2
        mid_y = (reported[i - 1] + reported[i]) / 2
        ax.annotate(
            f"{change:+.2f}",
            xy=(mid_x, mid_y),
            ha="center",
            va="bottom",
            fontsize=9,
            color=_PALETTE[0],
            fontweight="bold",
            xytext=(0, 6),
            textcoords="offset points",
        )

    tick_labels = [
        r.label if r.surprise_percent is None else f"{r.label}\nsorpresa {r.surprise_percent:+.0f}%" for r in reports
    ]
    ax.set_xticks(x, tick_labels, fontsize=8)
    ax.set_ylabel("EPS (USD)")
    ax.set_title("EPS estimado vs. reportado", fontsize=10)
    ax.legend(fontsize=8, loc="best")


def _plot_price_between_earnings(ax, ticker: str, reports: list[EarningsReport]) -> None:
    prices = closing_prices(ticker, "2y")
    window = prices[prices.index >= reports[0].date - pd.Timedelta(days=20)]
    ax.plot(window.index, window.to_numpy(), color=_PALETTE[0], linewidth=1.2)

    for r in reports:
        ax.axvline(r.date, color=_PALETTE[3], linestyle="--", linewidth=1)
        if r.close is not None:
            ax.scatter([r.date], [r.close], color=_PALETTE[3], zorder=3)

    # Tramo entre cada par de reportes: variación de precio y días.
    # Se deja un margen superior para las etiquetas, fuera de la línea de precio.
    low, high = (float(window.min()), float(window.max())) if not window.empty else (0.0, 1.0)
    top = high + (high - low) * 0.25
    ax.set_ylim(low - (high - low) * 0.05, top)
    for previous, current in zip(reports, reports[1:]):
        if current.price_change_percent is None:
            continue
        middle = previous.date + (current.date - previous.date) / 2
        color = UP_COLOR if current.price_change_percent >= 0 else DOWN_COLOR
        ax.annotate(
            f"{current.price_change_percent:+.1f}%\n{current.days_since_previous} días",
            xy=(middle, top),
            ha="center",
            va="top",
            fontsize=9,
            color=color,
            fontweight="bold",
        )

    ax.set_ylabel("Precio de cierre (USD)")
    ax.set_title("Precio entre reportes (variación y días entre uno y otro)", fontsize=10)
    if not window.empty:
        ax.set_xlim(window.index[0], window.index[-1])
    ax.tick_params(axis="x", labelsize=8)


# --------------------------------------------------------------------------
# Módulo quantstats.stats: catálogo agrupado de métricas
# --------------------------------------------------------------------------

StatKind = Literal["pct", "share", "ratio", "int"]  # share: porcentaje sin signo ni color


@dataclass(frozen=True, slots=True)
class StatMetric:
    label: str
    value: float | None
    kind: StatKind

    @property
    def display(self) -> str:
        if self.value is None:
            return "—"
        if self.kind == "pct":
            return f"{self.value * 100:+.2f}%"
        if self.kind == "share":
            return f"{self.value * 100:.2f}%"
        if self.kind == "int":
            return f"{self.value:.0f}"
        return f"{self.value:.2f}"

    @property
    def sign(self) -> str:
        """``is-up``/``is-down`` para colorear retornos; vacío para ratios."""
        if self.value is None or self.kind != "pct":
            return ""
        return "is-up" if self.value >= 0 else "is-down"


_StatSpec = tuple[str, Callable[[pd.Series], Any], StatKind]

STAT_GROUPS: tuple[tuple[str, tuple[_StatSpec, ...]], ...] = (
    (
        "Rendimiento",
        (
            ("CAGR", qs.stats.cagr, "pct"),
            ("Retorno diario esperado", qs.stats.expected_return, "pct"),
            ("Mejor día", qs.stats.best, "pct"),
            ("Peor día", qs.stats.worst, "pct"),
            ("Mejor mes", lambda r: qs.stats.best(r, aggregate="ME"), "pct"),
            ("Peor mes", lambda r: qs.stats.worst(r, aggregate="ME"), "pct"),
        ),
    ),
    (
        "Riesgo",
        (
            ("Value at Risk diario (95%)", qs.stats.value_at_risk, "pct"),
            ("Expected Shortfall (cVaR)", qs.stats.conditional_value_at_risk, "pct"),
            ("Ulcer index", qs.stats.ulcer_index, "ratio"),
            ("Asimetría (skew)", qs.stats.skew, "ratio"),
            ("Curtosis", qs.stats.kurtosis, "ratio"),
        ),
    ),
    (
        "Rendimiento ajustado por riesgo",
        (
            ("Smart Sharpe", qs.stats.smart_sharpe, "ratio"),
            ("Prob. Sharpe ratio", qs.stats.probabilistic_sharpe_ratio, "ratio"),
            ("Calmar", qs.stats.calmar, "ratio"),
            ("Omega", qs.stats.omega, "ratio"),
            ("Recovery factor", qs.stats.recovery_factor, "ratio"),
        ),
    ),
    (
        "Operativa diaria",
        (
            ("% días ganadores", qs.stats.win_rate, "share"),
            ("% meses ganadores", lambda r: qs.stats.win_rate(r, aggregate="ME"), "share"),
            ("Ganancia media", qs.stats.avg_win, "pct"),
            ("Pérdida media", qs.stats.avg_loss, "pct"),
            ("Payoff ratio", qs.stats.payoff_ratio, "ratio"),
            ("Profit factor", qs.stats.profit_factor, "ratio"),
            ("Tail ratio", qs.stats.tail_ratio, "ratio"),
            ("Kelly criterion", qs.stats.kelly_criterion, "pct"),
            ("Máx. días ganadores seguidos", qs.stats.consecutive_wins, "int"),
            ("Máx. días perdedores seguidos", qs.stats.consecutive_losses, "int"),
        ),
    ),
)


# Las 5 métricas de ``PerformanceMetrics`` (las tarjetas de resumen) no se
# repiten en ``STAT_GROUPS``; ``SUMMARY_STATS`` las expone con el mismo
# formato para la comparación contra benchmark.
SUMMARY_STATS: tuple[_StatSpec, ...] = (
    ("Retorno acumulado", qs.stats.comp, "pct"),
    ("Volatilidad anualizada", qs.stats.volatility, "share"),
    ("Sharpe", qs.stats.sharpe, "ratio"),
    ("Sortino", qs.stats.sortino, "ratio"),
    ("Máximo drawdown", qs.stats.max_drawdown, "pct"),
)


def stats_groups(returns: pd.Series) -> list[tuple[str, list[StatMetric]]]:
    """Evalúa ``STAT_GROUPS`` sobre ``returns``. Una métrica que quantstats no
    puede calcular (p. ej. por falta de datos) queda como ``None``.
    """
    if returns.empty:
        return []
    groups = []
    for title, specs in STAT_GROUPS:
        metrics = [StatMetric(label, _safe_stat(fn, returns), kind) for label, fn, kind in specs]
        groups.append((title, metrics))
    return groups


@dataclass(frozen=True, slots=True)
class StatComparison:
    label: str
    asset: StatMetric
    benchmark: StatMetric


def compare_stats(
    returns: pd.Series, benchmark: pd.Series
) -> list[tuple[str, list[StatComparison]]]:
    """Todas las métricas (resumen + ``STAT_GROUPS``) del activo junto a las del
    benchmark, sobre las mismas fechas."""
    if returns.empty or benchmark.empty:
        return []
    groups = (("Resumen", SUMMARY_STATS), *STAT_GROUPS)
    return [
        (
            title,
            [
                StatComparison(
                    label,
                    StatMetric(label, _safe_stat(fn, returns), kind),
                    StatMetric(label, _safe_stat(fn, benchmark), kind),
                )
                for label, fn, kind in specs
            ],
        )
        for title, specs in groups
    ]


def _safe_stat(fn: Callable[[pd.Series], Any], returns: pd.Series) -> float | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            value = float(fn(returns))
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    return value if np.isfinite(value) else None


# --------------------------------------------------------------------------
# Módulo quantstats.plots: catálogo de gráficas nativas
# --------------------------------------------------------------------------

BENCHMARKS = {
    "SPY": "S&P 500 (SPY)",
    "URA": "Global X Uranium ETF (URA)",
    "QQQ": "Nasdaq 100 (QQQ)",
}
ROLLING_WINDOWS = {21: "1 mes", 63: "3 meses", 126: "6 meses", 252: "1 año"}
DEFAULT_ROLLING_WINDOW = 126
QS_FONT = "DejaVu Sans"  # la fuente por defecto de quantstats (Arial) no existe en el servidor


@dataclass(frozen=True, slots=True)
class PlotSpec:
    slug: str
    label: str
    description: str
    function: str  # nombre de la función en ``quantstats.plots``
    benchmark: bool = False  # acepta benchmark
    requires_benchmark: bool = False
    rolling: bool = False  # acepta ventana móvil (``period``)


PLOTS: tuple[PlotSpec, ...] = (
    PlotSpec("snapshot", "Snapshot", "Retorno acumulado, drawdown y retornos diarios en una sola vista.", "snapshot"),
    PlotSpec("returns", "Retornos acumulados", "Evolución del retorno compuesto.", "returns", benchmark=True),
    PlotSpec(
        "log-returns", "Retornos acumulados (log)", "Retorno compuesto en escala logarítmica.", "log_returns",
        benchmark=True,
    ),
    PlotSpec("daily-returns", "Retornos diarios", "Retorno de cada sesión.", "daily_returns", benchmark=True),
    PlotSpec("yearly-returns", "Retornos anuales", "Retorno de cada año calendario.", "yearly_returns", benchmark=True),
    PlotSpec(
        "histogram", "Histograma mensual", "Distribución de los retornos mensuales.", "histogram", benchmark=True,
    ),
    PlotSpec(
        "distribution", "Distribución por horizonte", "Boxplots de retornos diarios, semanales, mensuales, "
        "trimestrales y anuales.", "distribution",
    ),
    PlotSpec(
        "monthly-heatmap", "Heatmap mensual", "Retorno de cada mes por año.", "monthly_heatmap", benchmark=True,
    ),
    PlotSpec("drawdown", "Drawdown (underwater)", "Caída desde el máximo previo.", "drawdown"),
    PlotSpec(
        "drawdowns-periods", "Peores 5 drawdowns", "Los 5 peores periodos de drawdown sobre el retorno acumulado.",
        "drawdowns_periods",
    ),
    PlotSpec(
        "rolling-volatility", "Volatilidad móvil", "Volatilidad anualizada en ventana móvil.", "rolling_volatility",
        benchmark=True, rolling=True,
    ),
    PlotSpec(
        "rolling-sharpe", "Sharpe móvil", "Sharpe anualizado en ventana móvil.", "rolling_sharpe",
        benchmark=True, rolling=True,
    ),
    PlotSpec(
        "rolling-sortino", "Sortino móvil", "Sortino anualizado en ventana móvil.", "rolling_sortino",
        benchmark=True, rolling=True,
    ),
    PlotSpec(
        "rolling-beta", "Beta móvil", "Beta frente al benchmark (usa SPY si no eliges otro).", "rolling_beta",
        benchmark=True, requires_benchmark=True,
    ),
    PlotSpec(
        "earnings", "Crecimiento de 100.000 USD", "Valor de una inversión inicial de 100.000 USD.", "earnings",
    ),
)
PLOTS_BY_SLUG = {p.slug: p for p in PLOTS}
# Gráficas del activo por sí solo (las que no necesitan benchmark).
ABSOLUTE_PLOTS = tuple(p for p in PLOTS if not p.requires_benchmark)
# Gráficas que se pueden superponer con un benchmark.
BENCHMARK_PLOTS = tuple(p for p in PLOTS if p.benchmark)

# quantstats dibuja sobre el estado global de pyplot: se serializa para que
# dos peticiones simultáneas no mezclen figuras.
_QS_PLOT_LOCK = threading.Lock()


def get_plot(slug: str) -> PlotSpec | None:
    return PLOTS_BY_SLUG.get(slug)


def render_qs_plot(
    ticker: str,
    period: str,
    slug: str,
    benchmark: str | None = None,
    window: int | None = None,
) -> bytes:
    """PNG de la gráfica ``slug`` de ``PLOTS`` generada por ``quantstats.plots``."""
    spec = PLOTS_BY_SLUG[slug]
    returns = daily_returns(ticker, period)
    if returns.size < 2:
        fig, ax = plt.subplots(figsize=(10, 3))
        _no_data(ax, ticker)
        return _to_png(fig)

    kwargs: dict[str, Any] = {"show": False, "fontname": QS_FONT}
    if spec.benchmark:
        symbol = benchmark or ("SPY" if spec.requires_benchmark else None)
        if symbol:
            kwargs["benchmark"] = benchmark_returns(symbol, period, returns.index)
        elif spec.function == "daily_returns":
            kwargs["benchmark"] = None  # argumento obligatorio en quantstats
    if spec.rolling:
        window = window or DEFAULT_ROLLING_WINDOW
        kwargs["period"] = window
        kwargs["period_label"] = ROLLING_WINDOWS.get(window, f"{window} sesiones")
    if spec.function in {"snapshot", "earnings"}:
        kwargs["title"] = ticker
    if spec.function == "monthly_heatmap":
        kwargs["returns_label"] = ticker

    with _QS_PLOT_LOCK, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = getattr(qs.plots, spec.function)(returns.rename(ticker), **kwargs)
        return _to_png(fig)


def benchmark_returns(symbol: str, period: str, index: pd.DatetimeIndex) -> pd.Series:
    """Retornos del benchmark alineados a las fechas de ``index`` (0 donde falten)."""
    bench = daily_returns(symbol, period).rename(symbol)
    return bench.reindex(index).fillna(0.0)


# --------------------------------------------------------------------------
# Simulación Monte Carlo (quantstats.stats.montecarlo)
# --------------------------------------------------------------------------

MONTECARLO_SIMS = (250, 500, 1000, 2000)
DEFAULT_MONTECARLO_SIMS = 1000
DEFAULT_BUST = -0.20
DEFAULT_GOAL = 0.50
# Semilla fija: la página (probabilidades) y la gráfica deben ver las mismas simulaciones.
MONTECARLO_SEED = 42


@dataclass(frozen=True, slots=True)
class MonteCarloSummary:
    sims: int
    bust: float
    goal: float
    bust_probability: float
    goal_probability: float
    terminal: dict[str, float]  # retorno acumulado final: min/median/max/percentiles
    max_drawdown: dict[str, float]  # máximo drawdown de cada camino


def _montecarlo(returns: pd.Series, sims: int, bust: float, goal: float):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return qs.stats.montecarlo(returns, sims=sims, bust=bust, goal=goal, seed=MONTECARLO_SEED)


def montecarlo_summary(
    returns: pd.Series,
    sims: int = DEFAULT_MONTECARLO_SIMS,
    bust: float = DEFAULT_BUST,
    goal: float = DEFAULT_GOAL,
) -> MonteCarloSummary | None:
    """Probabilidad de "bust" (drawdown peor que ``bust``) y de "goal" (retorno
    final de al menos ``goal``) barajando ``sims`` veces los retornos históricos.
    """
    if returns.size < 2:
        return None
    mc = _montecarlo(returns, sims, bust, goal)
    return MonteCarloSummary(
        sims=sims,
        bust=bust,
        goal=goal,
        bust_probability=float(mc.bust_probability),
        goal_probability=float(mc.goal_probability),
        terminal={k: float(v) for k, v in mc.stats.items()},
        max_drawdown={k: float(v) for k, v in mc.maxdd.items()},
    )


def render_montecarlo_chart(
    ticker: str,
    period: str,
    sims: int = DEFAULT_MONTECARLO_SIMS,
    bust: float = DEFAULT_BUST,
    goal: float = DEFAULT_GOAL,
) -> bytes:
    """PNG de ``MonteCarloResult.plot()``: caminos simulados, banda de
    confianza y umbrales de bust/goal."""
    returns = daily_returns(ticker, period)
    if returns.size < 2:
        fig, ax = plt.subplots(figsize=(10, 3))
        _no_data(ax, ticker)
        return _to_png(fig)
    with _QS_PLOT_LOCK:
        mc = _montecarlo(returns.rename(ticker), sims, bust, goal)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fig = mc.plot(show=False, fontname=QS_FONT, title=f"{ticker} · Monte Carlo ({sims} simulaciones)")
        return _to_png(fig)


# --------------------------------------------------------------------------
# Módulo quantstats.reports: tearsheet HTML
# --------------------------------------------------------------------------


def tearsheet_html(ticker: str, period: str, benchmark: str | None = None) -> str | None:
    """Tearsheet HTML completo de ``quantstats.reports.html`` (``None`` sin datos)."""
    returns = daily_returns(ticker, period)
    if returns.size < 2:
        return None

    kwargs: dict[str, Any] = {"title": f"{ticker} · Tearsheet", "figfmt": "svg"}
    if benchmark:
        kwargs["benchmark"] = benchmark_returns(benchmark, period, returns.index)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tearsheet.html")
        with _QS_PLOT_LOCK, warnings.catch_warnings():
            warnings.simplefilter("ignore")
            qs.reports.html(returns.rename(ticker), output=path, **kwargs)
        with open(path, encoding="utf-8") as fh:
            return fh.read()


def _no_data(ax, ticker: str) -> None:
    ax.set_title(f"{ticker}: sin datos suficientes")
    ax.axis("off")


def _to_png(fig, rect=(0, 0, 1, 1)) -> bytes:
    fig.tight_layout(rect=rect)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110)
    plt.close(fig)
    return buffer.getvalue()
