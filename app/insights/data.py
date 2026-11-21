"""Adaptador de Insights sobre ``app.core.market_data`` (solo lectura).

Traduce la entrada del usuario (un ticker o un portafolio con pesos), baja
los cierres diarios con ``market_data.get_candles`` (que ya cachea), resuelve
la frecuencia (252 o 365) y la tasa libre de riesgo, y entrega al motor
(``engine``) series de retornos validadas. Sin Flask.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from app.core import market_data
from app.insights import engine

RANGES = {"6mo": "6 meses", "1y": "1 año", "2y": "2 años", "5y": "5 años", "max": "Todo"}
DEFAULT_RANGE = "1y"
DEFAULT_BENCHMARK = "SPY"
MAX_ASSETS = 10
# Letras de 13 semanas del Tesoro de EE. UU.: Yahoo publica el rendimiento anual en %.
RISK_FREE_TICKER = "^IRX"

_TICKER_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,14}$")


class InputError(ValueError):
    """Entrada inválida: el mensaje se muestra tal cual al usuario."""


def normalize_ticker(value: str | None) -> str | None:
    ticker = (value or "").strip().upper()
    return ticker if _TICKER_RE.match(ticker) else None


def parse_portfolio(text: str) -> dict[str, float]:
    """``"AAPL"`` -> {AAPL: 1}; ``"SPY:60, TLT:40"`` o ``"SPY 60, TLT 40"`` ->
    pesos normalizados a 1; sin pesos, a partes iguales."""
    parts = [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise InputError("Escribe un ticker (por ejemplo AAPL) o un portafolio como «SPY:60, TLT:40».")
    if len(parts) > MAX_ASSETS:
        raise InputError(f"Un portafolio puede tener como máximo {MAX_ASSETS} activos.")
    raw: dict[str, float | None] = {}
    for part in parts:
        bits = part.replace(":", " ").split()
        ticker = normalize_ticker(bits[0])
        if ticker is None or len(bits) > 2:
            raise InputError(f"«{part}» no parece un ticker válido de Yahoo Finance.")
        weight = None
        if len(bits) == 2:
            try:
                weight = float(bits[1].rstrip("%").replace(",", "."))
            except ValueError:
                raise InputError(f"El peso de «{part}» no es un número.") from None
            if weight <= 0:
                raise InputError(f"El peso de {ticker} debe ser mayor que 0.")
        raw[ticker] = (raw.get(ticker) or 0) + weight if weight is not None else raw.get(ticker)
    given = [w for w in raw.values() if w is not None]
    if given and len(given) != len(raw):
        raise InputError("Indica el peso de todos los activos o de ninguno.")
    if not given:
        return {t: 1 / len(raw) for t in raw}
    total = sum(given)
    return {t: float(w) / total for t, w in raw.items()}  # type: ignore[arg-type]


def portfolio_label(weights: dict[str, float]) -> str:
    if len(weights) == 1:
        return next(iter(weights))
    return " · ".join(f"{t} {w * 100:.0f}%" for t, w in weights.items())


def closing_prices(ticker: str, range_: str) -> pd.Series:
    """Cierres diarios. Las velas llegan con la medianoche local de la bolsa
    en UTC; redondear al día más cercano conserva la fecha de la sesión
    también en bolsas al este de UTC."""
    candles = market_data.get_candles(ticker, range_=range_, interval="1d")
    if not candles:
        return pd.Series(dtype=float, name=ticker)
    frame = pd.DataFrame(candles)
    index = pd.to_datetime(frame["time"], unit="s").dt.round("D")
    return pd.Series(frame["close"].to_numpy(dtype=float), index=pd.DatetimeIndex(index), name=ticker)


def risk_free_rate(periods: int, override_percent: float | None = None) -> engine.RiskFree:
    """Tasa anual: la que indique el usuario (en %) o la actual de ^IRX; si
    Yahoo no responde, 0 % (y se dice en pantalla)."""
    if override_percent is not None:
        return engine.RiskFree(override_percent / 100, periods, "indicada por ti")
    try:
        price = market_data.get_quote(RISK_FREE_TICKER).price
    except Exception:  # noqa: BLE001 - sin red o sin dato
        price = None
    if price is None or not 0 <= price < 50:
        return engine.RiskFree(0.0, periods, "no disponible (se usa 0 %)")
    return engine.RiskFree(price / 100, periods, "letras del Tesoro de EE. UU. a 13 semanas (^IRX)")


@dataclass(slots=True)
class PreparedData:
    strategy: pd.Series
    benchmark: pd.Series
    periods: int
    notes: list[str] = field(default_factory=list)


def prepare(weights: dict[str, float], benchmark: str, range_: str) -> PreparedData:
    """Retornos validados del portafolio y del benchmark, en la misma
    frecuencia. Si hay mezcla cripto/bolsa, se usa 252 y los precios cripto se
    remuestrean al calendario bursátil antes de calcular retornos."""
    tickers = list(weights)
    prices = {t: closing_prices(t, range_) for t in [*tickers, benchmark]}
    empty = [t for t, p in prices.items() if p.dropna().empty]
    if empty:
        raise engine.InsightError(f"Yahoo Finance no devolvió precios para {', '.join(empty)}. Revisa el ticker.")

    notes: list[str] = []
    crypto = {t for t in prices if engine.is_crypto(t)}
    periods = engine.CRYPTO_PERIODS if len(crypto) == len(prices) else engine.STOCK_PERIODS
    if crypto and periods == engine.STOCK_PERIODS:
        calendar_ticker = next(t for t in [benchmark, *tickers] if t not in crypto)
        calendar = pd.DatetimeIndex(prices[calendar_ticker].index).normalize()
        for t in crypto:
            prices[t] = engine.resample_prices(prices[t], calendar)
        notes.append(
            f"{', '.join(sorted(crypto))} cotiza 365 días al año: sus precios se llevaron al calendario "
            f"bursátil de {calendar_ticker} antes de calcular retornos (252 periodos por año)."
        )

    returns: dict[str, pd.Series] = {}
    for t, series in prices.items():
        validated = engine.validate_returns(series, input_kind="prices", name=t)
        if validated.report.removed:
            notes.append(f"{t}: se eliminaron {validated.report.removed} fila(s) con datos vacíos, inválidos o duplicados.")
        returns[t] = validated.returns

    if len(tickers) == 1:
        strategy = returns[tickers[0]]
    else:
        strategy = engine.portfolio_returns({t: returns[t] for t in tickers}, weights)
        notes.append("Portafolio con pesos fijos y rebalanceo diario, en las fechas comunes a todos sus activos.")
    return PreparedData(strategy.rename(portfolio_label(weights)), returns[benchmark], periods, notes)
