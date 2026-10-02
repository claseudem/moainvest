"""Modelo de análisis cuantitativo con ``quantstats``: métricas de rendimiento
y riesgo, drawdown, heatmap de retornos mensuales y comparación de los
últimos reportes de resultados (earnings).

Igual que ``analysis``, reutiliza los datos ya descargados/cacheados por
``market_data`` y genera las gráficas en el servidor como PNG.
"""
from __future__ import annotations

import io
import time
from dataclasses import asdict, dataclass
from typing import Any

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


def _no_data(ax, ticker: str) -> None:
    ax.set_title(f"{ticker}: sin datos suficientes")
    ax.axis("off")


def _to_png(fig, rect=(0, 0, 1, 1)) -> bytes:
    fig.tight_layout(rect=rect)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110)
    plt.close(fig)
    return buffer.getvalue()
