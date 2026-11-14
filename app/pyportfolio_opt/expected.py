"""Modelo de retornos esperados con PyPortfolioOpt (``pypfopt.expected_returns``).

Calcula el retorno esperado anualizado de uno o varios activos con las dos
metodologías de la librería basadas en el histórico de precios:

- **Media histórica** (``mean_historical_return``): con capitalización es la
  tasa de crecimiento anual compuesta (CAGR) de los retornos diarios,
  ``(prod(1 + r_t)) ** (252 / N) - 1``; sin ella, la media aritmética de los
  retornos diarios por 252.
- **EMA** (``ema_historical_return``): media móvil exponencial de los retornos
  diarios con ventana ``span``, que da más peso a los datos recientes. Con
  capitalización, ``(1 + EMA) ** 252 - 1``; sin ella, ``EMA * 252``.

Los precios salen de ``market_data`` (ya cacheados), nunca de yfinance
directamente. La gráfica de barras se genera con matplotlib y los colores de
``app.core.charts``, sin tocar el estado global de matplotlib.
"""
from __future__ import annotations

import io
import math
import warnings
from dataclasses import dataclass, field
from typing import Any

import matplotlib

matplotlib.use("Agg")  # backend sin display: obligatorio en un servidor

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter
from pypfopt import expected_returns

from app.core import market_data
from app.core.charts import BRAND, INK, LINE, MPL_RC

# Metodologías disponibles (id -> nombre visible), en el orden en que se muestran.
METHODS: dict[str, str] = {
    "historical": "Media histórica",
    "ema": "EMA",
}

# Días de negociación por año: la ``frequency`` con la que se anualiza.
TRADING_DAYS_PER_YEAR = 252

# Ventana por defecto de la EMA: la misma que usa PyPortfolioOpt.
DEFAULT_SPAN = 500

# Color de cada metodología en la gráfica.
METHOD_COLORS = {"historical": BRAND, "ema": INK}


class ExpectedReturnsError(ValueError):
    """Ningún ticker tiene precios suficientes para calcular retornos."""


@dataclass(slots=True)
class AssetExpectedReturn:
    """Retornos esperados (en tanto por uno) de un activo por metodología."""

    ticker: str
    observations: int
    start: str
    end: str
    returns: dict[str, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "observations": self.observations,
            "start": self.start,
            "end": self.end,
            **self.returns,
        }


@dataclass(slots=True)
class ExpectedReturnsResult:
    period: str
    methods: tuple[str, ...]
    span: int
    compounding: bool
    log_returns: bool
    assets: list[AssetExpectedReturn]
    missing: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "methods": [{"id": m, "name": METHODS[m]} for m in self.methods],
            "span": self.span,
            "compounding": self.compounding,
            "log_returns": self.log_returns,
            "frequency": TRADING_DAYS_PER_YEAR,
            "assets": [asset.to_dict() for asset in self.assets],
            "missing": self.missing,
        }


def load_prices(tickers: list[str], period: str = "5y") -> pd.DataFrame:
    """Cierres diarios de ``tickers`` en un DataFrame (una columna por ticker),
    indexado por fecha. Los activos con historias de distinta longitud quedan
    con ``NaN`` al principio; los tickers sin datos no aparecen."""
    columns: dict[str, pd.Series] = {}
    for ticker in tickers:
        candles = market_data.get_candles(ticker, range_=period, interval="1d")
        if not candles:
            continue
        # La hora de la vela depende de la bolsa: se agrupa por día natural.
        dates = pd.to_datetime([c["time"] for c in candles], unit="s").normalize()
        closes = pd.Series([c["close"] for c in candles], index=dates, dtype=float)
        columns[ticker] = closes[~closes.index.duplicated(keep="last")]
    return pd.DataFrame(columns).sort_index()


def _clean(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _run_method(method: str, prices: pd.DataFrame, span: int, compounding: bool, log_returns: bool) -> pd.Series:
    kwargs = {
        "compounding": compounding,
        "frequency": TRADING_DAYS_PER_YEAR,
        "log_returns": log_returns,
    }
    # Activos con historias de distinta longitud dejan NaN al principio de sus
    # retornos: es lo esperado (cada uno usa su propia historia), no un error.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Some returns are NaN")
        if method == "ema":
            return expected_returns.ema_historical_return(prices, span=span, **kwargs)
        return expected_returns.mean_historical_return(prices, **kwargs)


def compute_expected_returns(
    tickers: list[str],
    period: str = "5y",
    methods: tuple[str, ...] = tuple(METHODS),
    span: int = DEFAULT_SPAN,
    compounding: bool = True,
    log_returns: bool = False,
) -> ExpectedReturnsResult:
    """Retorno esperado anualizado de cada ticker con las metodologías pedidas.

    Cada activo se calcula sobre toda su historia disponible en el período
    (PyPortfolioOpt ignora los ``NaN`` por columna). Los tickers sin al menos
    dos cierres se devuelven en ``missing``.
    """
    prices = load_prices(tickers, period)
    valid = [t for t in tickers if t in prices and prices[t].count() >= 2]
    missing = [t for t in tickers if t not in valid]
    if not valid:
        raise ExpectedReturnsError("No hay precios suficientes para ninguno de los tickers indicados")
    prices = prices[valid].dropna(how="all")

    by_method = {m: _run_method(m, prices, span, compounding, log_returns) for m in methods}

    assets = []
    for ticker in valid:
        series = prices[ticker].dropna()
        assets.append(
            AssetExpectedReturn(
                ticker=ticker,
                observations=int(series.size),
                start=series.index[0].date().isoformat(),
                end=series.index[-1].date().isoformat(),
                returns={m: _clean(by_method[m].get(ticker)) for m in methods},
            )
        )
    return ExpectedReturnsResult(
        period=period,
        methods=tuple(methods),
        span=span,
        compounding=compounding,
        log_returns=log_returns,
        assets=assets,
        missing=missing,
    )


def render_expected_returns_chart(result: ExpectedReturnsResult) -> bytes:
    """Barras agrupadas por ticker con el retorno esperado de cada metodología.
    Devuelve un PNG en bytes."""
    with plt.rc_context(MPL_RC):
        return _render_chart(result)


def _render_chart(result: ExpectedReturnsResult) -> bytes:
    tickers = [a.ticker for a in result.assets]
    n_methods = len(result.methods)
    width = 0.8 / n_methods
    x = np.arange(len(tickers))

    fig, ax = plt.subplots(figsize=(max(6.0, 1.3 * len(tickers) + 3), 4.2))
    for i, method in enumerate(result.methods):
        values = [(a.returns.get(method) or 0.0) * 100 for a in result.assets]
        offset = (i - (n_methods - 1) / 2) * width
        bars = ax.bar(x + offset, values, width, label=METHODS[method], color=METHOD_COLORS[method])
        ax.bar_label(bars, labels=[f"{v:.1f}%" for v in values], padding=3, fontsize=8)

    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xticks(x, tickers)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylabel("Retorno esperado anualizado")
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=LINE)
    ax.margins(y=0.15)
    if n_methods > 1:
        ax.legend(loc="upper left", ncols=n_methods)
    ax.set_title("Retornos esperados (PyPortfolioOpt)", loc="left")
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()
