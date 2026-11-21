"""Motor de métricas de Insights sobre ``quantstats``, sin Flask ni red.

Convenciones fijas para TODAS las métricas (y documentadas en pantalla):

- Retornos **simples** (``pct_change``), nunca logarítmicos.
- ``COMPOUNDED = True``: rentabilidad total y CAGR compuestas.
- ``rf`` es siempre una tasa **anual**. quantstats la desanualiza con
  ``(1 + rf) ** (1 / periodos) - 1`` cuando recibe ``periods``; aquí se le
  pasa siempre ``periods_per_year`` para que lo haga bien.
- ``periods_per_year`` es 252 (acciones) o 365 (cripto); una serie cripto
  frente a un benchmark bursátil se remuestrea al calendario bursátil
  *antes* de calcular retornos (``resample_prices``), nunca se mezclan.

Solo se usan funciones oficiales (``qs.stats.*`` y ``qs.reports.metrics``);
ninguna métrica se reimplementa. Cada llamada pasa por
``safe_stat``, que convierte un fallo de la librería (por ejemplo una
incompatibilidad con pandas) en ``None`` y un aviso, sin parchearla.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
import warnings
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
import quantstats as qs

log = logging.getLogger(__name__)

COMPOUNDED = True
RETURNS_KIND = "simple"
STOCK_PERIODS = 252
CRYPTO_PERIODS = 365

# Umbrales de las advertencias estadísticas.
SHORT_SAMPLE_DAYS = 365  # menos de 1 año de calendario...
# ...con una semana de margen: el rango "1 año" de Yahoo empieza en festivos o
# fines de semana y el primer cierre no tiene retorno, así que suele dar ~360 días.
SHORT_SAMPLE_TOLERANCE_DAYS = 7
MIN_PERIODS_FOR_TAIL_RATIOS = 30  # por debajo, Sortino/Calmar/tail ratio se atenúan
SUSPICIOUS_SHARPE = 3.0

# Pares cripto de Yahoo Finance: BTC-USD, ETH-EUR, SOL-USDT...
_CRYPTO_RE = re.compile(r"^[A-Z0-9]{2,10}-(USD|USDT|USDC|EUR|GBP|BTC|ETH)$")


def is_crypto(ticker: str) -> bool:
    return bool(_CRYPTO_RE.match(ticker))


def periods_per_year(ticker: str) -> int:
    return CRYPTO_PERIODS if is_crypto(ticker) else STOCK_PERIODS


# --------------------------------------------------------------------------
# Preparación de datos
# --------------------------------------------------------------------------


@dataclass(slots=True)
class ValidationReport:
    """Qué se ha limpiado de una serie, para mostrarlo y no esconderlo."""

    rows_in: int = 0
    duplicates_removed: int = 0
    invalid_prices_removed: int = 0  # NaN, infinitos o <= 0 en precios
    nan_removed: int = 0
    inf_removed: int = 0
    rows_out: int = 0

    @property
    def removed(self) -> int:
        return self.duplicates_removed + self.invalid_prices_removed + self.nan_removed + self.inf_removed


@dataclass(slots=True)
class ValidatedReturns:
    returns: pd.Series
    report: ValidationReport


def _clean_index(series: pd.Series) -> pd.Series:
    index = pd.DatetimeIndex(pd.to_datetime(series.index))
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    series = series.copy()
    series.index = index.normalize()  # frecuencia diaria: una fila por fecha
    return series


def validate_returns(
    data: pd.Series | pd.DataFrame,
    *,
    input_kind: Literal["prices", "returns"] = "prices",
    name: str | None = None,
) -> ValidatedReturns:
    """Convierte ``data`` en retornos simples diarios listos para quantstats.

    - Índice ``DatetimeIndex`` tz-naive, normalizado a fecha, ordenado y sin
      fechas duplicadas (se conserva la última observación del día).
    - Precios: se descartan los NaN, infinitos y no positivos *antes* de
      ``pct_change`` (así un hueco no inventa un retorno de 0 %) y se elimina
      la primera fila, que no tiene retorno (no cuenta como dato perdido).
    - Retornos: los infinitos y NaN se eliminan (nunca se rellenan con 0, que
      es lo que haría quantstats y sesgaría la volatilidad a la baja).
    """
    if isinstance(data, pd.DataFrame):
        data = data.iloc[:, 0] if data.shape[1] else pd.Series(dtype=float)
    series = pd.to_numeric(pd.Series(data), errors="coerce").astype(float)
    report = ValidationReport(rows_in=int(series.size))
    if series.empty:
        return ValidatedReturns(pd.Series(dtype=float, name=name, index=pd.DatetimeIndex([])), report)

    series = _clean_index(series).sort_index()
    duplicated = series.index.duplicated(keep="last")
    report.duplicates_removed = int(duplicated.sum())
    series = series[~duplicated]

    if input_kind == "prices":
        valid = np.isfinite(series.to_numpy()) & (series.to_numpy() > 0)
        report.invalid_prices_removed = int((~valid).sum())
        returns = series[valid].pct_change(fill_method=None).iloc[1:]
    else:
        returns = series

    infinite = np.isinf(returns.to_numpy())
    report.inf_removed = int(infinite.sum())
    returns = returns[~infinite]
    missing = returns.isna().to_numpy()
    report.nan_removed = int(missing.sum())
    returns = returns[~missing]

    returns = returns.rename(name if name is not None else series.name)
    returns.index.name = None
    report.rows_out = int(returns.size)
    return ValidatedReturns(returns, report)


def resample_prices(prices: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Precios de una serie de 365 días/año (cripto) llevados a otro calendario
    (bursátil): el último precio conocido en cada fecha del calendario."""
    prices = _clean_index(prices.dropna()).sort_index()
    prices = prices[~prices.index.duplicated(keep="last")]
    if prices.empty:
        return prices
    calendar = calendar[calendar >= prices.index[0]]
    return prices.reindex(prices.index.union(calendar)).ffill().reindex(calendar)


@dataclass(slots=True)
class Aligned:
    strategy: pd.Series
    benchmark: pd.Series
    strategy_dropped: int  # fechas de la estrategia sin benchmark
    benchmark_dropped: int
    leading_trimmed: int  # fechas iniciales sin movimiento en alguna de las dos


def align_with_benchmark(strategy: pd.Series, benchmark: pd.Series) -> Aligned:
    """Inner join exacto por fecha; después recorta el arranque igual que
    ``quantstats.reports._match_dates`` (hasta el primer día en que ambas
    series se mueven), para que las fechas coincidan con las de sus reportes."""
    joined = pd.concat([strategy.rename("s"), benchmark.rename("b")], axis=1, join="inner").sort_index()
    trimmed = 0
    if not joined.empty and joined["s"].ne(0).any() and joined["b"].ne(0).any():
        start = max(joined["s"].ne(0).idxmax(), joined["b"].ne(0).idxmax())
        trimmed = int((joined.index < start).sum())
        joined = joined.loc[start:]
    return Aligned(
        strategy=joined["s"].rename(strategy.name),
        benchmark=joined["b"].rename(benchmark.name),
        strategy_dropped=int(strategy.size - joined.shape[0] - trimmed),
        benchmark_dropped=int(benchmark.size - joined.shape[0] - trimmed),
        leading_trimmed=trimmed,
    )


def portfolio_returns(returns_by_asset: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    """Retornos de un portafolio con pesos fijos y rebalanceo diario: la suma
    ponderada de los retornos de sus activos en las fechas comunes."""
    frame = pd.concat(returns_by_asset, axis=1, join="inner").sort_index()
    w = pd.Series(weights, dtype=float).reindex(frame.columns)
    return (frame * w).sum(axis=1)


@dataclass(frozen=True, slots=True)
class RiskFree:
    """Tasa libre de riesgo: siempre anual; ``per_period`` es su equivalente
    compuesto en cada periodo (la misma conversión que hace quantstats)."""

    annual: float
    periods: int
    source: str

    @property
    def per_period(self) -> float:
        return (1 + self.annual) ** (1 / self.periods) - 1


# --------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------


def safe_stat(label: str, fn: Callable[..., Any], *args: Any, errors: list[str] | None = None, **kwargs: Any) -> float | None:
    """Llama a una función de quantstats y devuelve un ``float`` finito o
    ``None``. Si la librería falla, lo registra y añade un aviso amable a
    ``errors`` en vez de propagar el traceback."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            value = fn(*args, **kwargs)
        if isinstance(value, pd.Series):
            value = value.iloc[0] if value.size else None
        value = float(value)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de la librería
        log.warning("quantstats falló en %s: %s", label, exc)
        if errors is not None:
            errors.append(f"No se pudo calcular «{label}» con esta versión de quantstats.")
        return None
    return value if math.isfinite(value) else None


@dataclass(slots=True)
class SeriesStats:
    """Métricas de una serie (estrategia o benchmark), todas de qs.stats."""

    total_return: float | None
    cagr: float | None
    max_drawdown: float | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    tail_ratio: float | None
    volatility: float | None
    var: float | None
    cvar: float | None


def series_stats(returns: pd.Series, rf: RiskFree, errors: list[str]) -> SeriesStats:
    p = rf.periods
    return SeriesStats(
        total_return=safe_stat("Rentabilidad total", qs.stats.comp, returns, errors=errors),
        cagr=safe_stat("CAGR", qs.stats.cagr, returns, rf=rf.annual, compounded=COMPOUNDED, periods=p, errors=errors),
        max_drawdown=safe_stat("Max Drawdown", qs.stats.max_drawdown, returns, errors=errors),
        sharpe=safe_stat("Sharpe", qs.stats.sharpe, returns, rf=rf.annual, periods=p, annualize=True, errors=errors),
        sortino=safe_stat("Sortino", qs.stats.sortino, returns, rf=rf.annual, periods=p, annualize=True, errors=errors),
        calmar=safe_stat("Calmar", qs.stats.calmar, returns, periods=p, errors=errors),
        tail_ratio=safe_stat("Tail ratio", qs.stats.tail_ratio, returns, errors=errors),
        volatility=safe_stat("Volatilidad", qs.stats.volatility, returns, periods=p, annualize=True, errors=errors),
        var=safe_stat("VaR", qs.stats.value_at_risk, returns, errors=errors),
        cvar=safe_stat("CVaR", qs.stats.conditional_value_at_risk, returns, errors=errors),
    )


@dataclass(slots=True)
class Warning_:
    """Advertencia estadística visible en la interfaz."""

    level: Literal["info", "caution", "alert"]
    title: str
    text: str


@dataclass(slots=True)
class DrawdownEpisode:
    start: str
    valley: str
    end: str | None
    depth: float  # fracción negativa
    benchmark_change: float | None  # qué hizo el benchmark entre start y valley


@dataclass(slots=True)
class Insight:
    label: str
    benchmark_label: str
    rf: RiskFree
    start: str
    end: str
    periods: int  # número de observaciones
    span_days: int
    strategy: SeriesStats
    benchmark: SeriesStats
    beta: float | None
    alpha: float | None
    warnings: list[Warning_]
    errors: list[str]
    unreliable: set[str]  # métricas que se muestran atenuadas
    worst_drawdown: DrawdownEpisode | None
    full_table: list[tuple[str, str, str]]  # (métrica, estrategia, benchmark) tal cual quantstats
    returns: pd.Series = field(repr=False)
    benchmark_returns: pd.Series = field(repr=False)
    data_notes: list[str] = field(default_factory=list)

    @property
    def short_sample(self) -> bool:
        return self.span_days + SHORT_SAMPLE_TOLERANCE_DAYS < SHORT_SAMPLE_DAYS


class InsightError(ValueError):
    """Entrada sin datos suficientes: el mensaje es apto para el usuario."""


def _worst_drawdown(strategy: pd.Series, benchmark: pd.Series, errors: list[str]) -> DrawdownEpisode | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            details = qs.stats.drawdown_details(qs.stats.to_drawdown_series(strategy))
    except Exception as exc:  # noqa: BLE001
        log.warning("drawdown_details falló: %s", exc)
        errors.append("No se pudo detallar la peor caída.")
        return None
    if details is None or details.empty:
        return None
    row = details.sort_values("max drawdown").iloc[0]
    start, valley = pd.Timestamp(row["start"]), pd.Timestamp(row["valley"])
    # El drawdown empieza a contar el día ``start``: el pico es la sesión previa.
    window = benchmark[(benchmark.index >= start) & (benchmark.index <= valley)]
    bench_change = safe_stat("Caída del benchmark", qs.stats.comp, window, errors=errors) if window.size else None
    end = row.get("end")
    return DrawdownEpisode(
        start=start.strftime("%Y-%m-%d"),
        valley=valley.strftime("%Y-%m-%d"),
        end=pd.Timestamp(end).strftime("%Y-%m-%d") if pd.notna(end) and pd.Timestamp(end) < strategy.index[-1] else None,
        depth=float(row["max drawdown"]) / 100,  # quantstats la da en %
        benchmark_change=bench_change,
    )


def full_metrics_table(aligned: Aligned, rf: RiskFree, label: str, benchmark_label: str) -> list[tuple[str, str, str]]:
    """``qs.reports.metrics(mode="full")`` con sus propios formatos (los del
    tearsheet): una fila por métrica; los separadores salen como ``("", "", "")``."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = qs.reports.metrics(
            aligned.strategy,
            benchmark=aligned.benchmark,
            rf=rf.annual,
            mode="full",
            display=False,
            compounded=COMPOUNDED,
            periods_per_year=rf.periods,
            internal=True,
            strategy_title=label,
            benchmark_title=benchmark_label,
        )
    # Por nombre de columna: el orden de columnas de quantstats no es fiable.
    strategy_col = table.columns.get_loc(label)
    benchmark_col = table.columns.get_loc(benchmark_label)
    rows: list[tuple[str, str, str]] = []
    for metric, values in table.iterrows():
        metric = str(metric)
        if not metric.strip():
            rows.append(("", "", ""))
            continue
        rows.append((metric, str(values.iloc[strategy_col]), str(values.iloc[benchmark_col])))
    return rows


def compute_insight(
    strategy: pd.Series,
    benchmark: pd.Series,
    rf: RiskFree,
    *,
    label: str,
    benchmark_label: str,
    data_notes: list[str] | None = None,
) -> Insight:
    """Métricas, advertencias y tabla completa de ``strategy`` frente a
    ``benchmark`` (ambas series de retornos ya validadas)."""
    aligned = align_with_benchmark(strategy, benchmark)
    s, b = aligned.strategy, aligned.benchmark
    if s.size < 2:
        raise InsightError(
            "No hay suficientes días en común con el benchmark para calcular nada (hacen falta al menos 2)."
        )

    errors: list[str] = []
    notes = list(data_notes or [])
    if aligned.strategy_dropped or aligned.benchmark_dropped:
        notes.append(
            f"Se alinearon las fechas con el benchmark: se descartaron {aligned.strategy_dropped} día(s) "
            f"del activo y {aligned.benchmark_dropped} del benchmark sin pareja."
        )
    if aligned.leading_trimmed:
        notes.append(f"Se omitieron {aligned.leading_trimmed} día(s) iniciales sin movimiento, igual que quantstats.")

    strat_stats = series_stats(s, rf, errors)
    bench_stats = series_stats(b, rf, errors)
    greeks = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            greeks = qs.stats.greeks(s, b, periods=rf.periods)
    except Exception as exc:  # noqa: BLE001
        log.warning("greeks falló: %s", exc)
        errors.append("No se pudieron calcular beta y alpha.")

    try:
        table = full_metrics_table(aligned, rf, label, benchmark_label)
    except Exception as exc:  # noqa: BLE001
        log.warning("reports.metrics falló: %s", exc)
        errors.append("La tabla completa de quantstats no está disponible para estos datos.")
        table = []

    span_days = int((s.index[-1] - s.index[0]).days)
    warns: list[Warning_] = []
    unreliable: set[str] = set()
    if span_days + SHORT_SAMPLE_TOLERANCE_DAYS < SHORT_SAMPLE_DAYS:
        warns.append(Warning_("caution", "Muestra corta, los ratios son poco fiables",
                              f"Solo hay {span_days} días de historia; con menos de un año, un par de días buenos o malos "
                              "cambian mucho los ratios anualizados."))
    if s.size < MIN_PERIODS_FOR_TAIL_RATIOS:
        unreliable |= {"sortino", "calmar", "tail_ratio"}
        warns.append(Warning_("caution", "Muy pocos periodos",
                              f"Con {s.size} observaciones (menos de {MIN_PERIODS_FOR_TAIL_RATIOS}) Sortino, Calmar y "
                              "tail ratio no son representativos: se muestran atenuados."))
    if strat_stats.sharpe is not None and strat_stats.sharpe > SUSPICIOUS_SHARPE:
        warns.append(Warning_("alert", "Sharpe sospechosamente alto",
                              f"Un Sharpe de {strat_stats.sharpe:.2f} (más de {SUSPICIOUS_SHARPE:g}) es muy raro en la "
                              "realidad: puede indicar sobreajuste, un periodo excepcional o un error en los datos."))
    if s.abs().sum() == 0:
        warns.append(Warning_("info", "Sin movimiento",
                              "El activo no ha variado en todo el periodo: los ratios de riesgo no tienen sentido."))

    return Insight(
        label=label,
        benchmark_label=benchmark_label,
        rf=rf,
        start=s.index[0].strftime("%Y-%m-%d"),
        end=s.index[-1].strftime("%Y-%m-%d"),
        periods=int(s.size),
        span_days=span_days,
        strategy=strat_stats,
        benchmark=bench_stats,
        beta=_finite(greeks.get("beta")) if greeks is not None else None,
        alpha=_finite(greeks.get("alpha")) if greeks is not None else None,
        warnings=warns,
        errors=errors,
        unreliable=unreliable,
        worst_drawdown=_worst_drawdown(s, b, errors),
        full_table=table,
        returns=s,
        benchmark_returns=b,
        data_notes=notes,
    )


def _finite(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# --------------------------------------------------------------------------
# Series para los gráficos (capas 2 y 3)
# --------------------------------------------------------------------------


def _points(series: pd.Series) -> list[dict[str, Any]]:
    series = series.replace([np.inf, -np.inf], np.nan).dropna()
    return [{"time": ts.strftime("%Y-%m-%d"), "value": round(float(v), 6)} for ts, v in series.items()]


def chart_series(insight: Insight) -> dict[str, Any]:
    """Curva de capital (crecimiento de $100) y drawdown (en %) de la
    estrategia y del benchmark, en el formato de lightweight-charts."""
    pairs = (("strategy", insight.returns), ("benchmark", insight.benchmark_returns))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        equity = {k: _points(100 * (1 + qs.stats.compsum(r))) for k, r in pairs}
        drawdown = {k: _points(100 * qs.stats.to_drawdown_series(r)) for k, r in pairs}
    return {"equity": equity, "drawdown": drawdown}


MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def monthly_heatmap(returns: pd.Series) -> list[dict[str, Any]]:
    """Filas por año con los 12 meses y el total (EOY) de
    ``qs.stats.monthly_returns``; los meses fuera del histórico son ``None``
    (quantstats los rellena con 0 y se confundirían con meses planos)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = qs.stats.monthly_returns(returns, eoy=True, compounded=COMPOUNDED)
    first, last = returns.index[0].to_period("M"), returns.index[-1].to_period("M")
    rows = []
    for year, values in table.iterrows():
        months = []
        for number, column in enumerate(table.columns[:12], start=1):
            inside = first <= pd.Period(year=int(year), month=number, freq="M") <= last
            months.append(_finite(values[column]) if inside else None)
        rows.append({"year": int(year), "months": months, "total": _finite(values.get("EOY"))})
    return rows


# --------------------------------------------------------------------------
# Caché de resultados
# --------------------------------------------------------------------------

CACHE_TTL = 300  # segundos
_cache: dict[Hashable, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def cached(key: Hashable, loader: Callable[[], Any], ttl: int = CACHE_TTL) -> Any:
    """Memoriza el resultado por clave, p. ej. (activo, rango, benchmark, rf).
    Los errores no se cachean."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
