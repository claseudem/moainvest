"""Catálogo y cálculo de los indicadores técnicos del Graficador (TA-Lib).

Lógica de dominio sin Flask. Cada ``Indicator`` declara sus parámetros (con
límites, para validar lo que llega por la API), sus salidas (líneas o
histogramas) y la función que las calcula con TA-Lib sobre las velas de
``app.core.market_data.get_candles``.

Para añadir un indicador basta con una entrada más en ``INDICATORS``: aparece
solo en el diálogo "Indicadores" del Graficador y en la API.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np
import talib

# Paleta para las líneas de los indicadores: el JS asigna la siguiente libre a
# cada indicador de una sola línea, para que dos medias móviles no se confundan.
PALETTE = ["#2962ff", "#ff6d00", "#8e24aa", "#00897b", "#f9a825", "#6d4c41", "#171717", "#d81b60"]

CATEGORIES = ("Tendencia", "Momentum", "Volatilidad", "Volumen")

# Tope de indicadores por petición a la API.
MAX_INDICATORS = 25


# Nombres cortos que no salen del paréntesis del nombre largo.
_SHORT = {"bbands": "BB", "stoch": "Stoch", "stochrsi": "Stoch RSI", "mom": "MOM", "sar": "SAR"}


@dataclass(frozen=True, slots=True)
class Bars:
    """Velas como arrays de float64 (lo que espera TA-Lib)."""

    time: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    @classmethod
    def from_candles(cls, candles: Sequence[dict[str, Any]]) -> Bars:
        def column(key: str) -> np.ndarray:
            return np.array([c[key] for c in candles], dtype=np.float64)

        return cls(*(column(k) for k in ("time", "open", "high", "low", "close", "volume")))

    def __len__(self) -> int:
        return len(self.time)


@dataclass(frozen=True, slots=True)
class Param:
    key: str
    label: str
    default: float
    min: float
    max: float
    step: float = 1
    kind: str = "int"  # "int" o "float"

    def parse(self, raw: Any) -> int | float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"«{self.label}» debe ser un número") from None
        if not math.isfinite(value):
            raise ValueError(f"«{self.label}» debe ser un número")
        if self.kind == "int":
            if value != int(value):
                raise ValueError(f"«{self.label}» debe ser un entero")
            value = int(value)
        if not self.min <= value <= self.max:
            raise ValueError(f"«{self.label}» debe estar entre {self.min:g} y {self.max:g}")
        return value


@dataclass(frozen=True, slots=True)
class Output:
    key: str
    label: str
    color: str
    # "line", "dashed", "dots" (puntos sueltos, como el SAR) o "histogram".
    style: str = "line"


@dataclass(frozen=True, slots=True)
class Indicator:
    id: str
    name: str
    description: str
    category: str
    overlay: bool  # True: se dibuja sobre el precio; False: en su propio panel
    params: tuple[Param, ...]
    outputs: tuple[Output, ...]
    compute: Callable[[Bars, dict[str, Any]], dict[str, np.ndarray]]
    # Líneas horizontales de referencia (p. ej. 30 y 70 en el RSI).
    levels: tuple[float, ...] = ()
    # Rango fijo de la escala para osciladores acotados (p. ej. 0-100).
    bounds: tuple[float, float] | None = None

    @property
    def short(self) -> str:
        """Nombre corto para la leyenda del gráfico: ``SMA``, ``BB``, ``RSI``..."""
        if self.id in _SHORT:
            return _SHORT[self.id]
        match = re.search(r"\(([^)]+)\)$", self.name)
        return match.group(1) if match else self.name

    def defaults(self) -> dict[str, Any]:
        return {p.key: (int(p.default) if p.kind == "int" else p.default) for p in self.params}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "short": self.short,
            "description": self.description,
            "category": self.category,
            "overlay": self.overlay,
            "params": [
                {"key": p.key, "label": p.label, "default": p.default, "min": p.min, "max": p.max, "step": p.step, "kind": p.kind}
                for p in self.params
            ],
            "outputs": [{"key": o.key, "label": o.label, "color": o.color, "style": o.style} for o in self.outputs],
            "levels": list(self.levels),
            "bounds": list(self.bounds) if self.bounds else None,
        }


def _period(default: int, label: str = "Periodo", max_: int = 500, key: str = "period") -> Param:
    return Param(key, label, default, 1, max_)


def _single(fn: Callable[..., np.ndarray], *columns: str, key: str, **mapping: str) -> Callable:
    """Adapta una función de TA-Lib de una sola salida: ``fn(*columnas, **params)``."""

    def compute(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
        args = [getattr(bars, c) for c in columns]
        kwargs = {talib_name: p[param_key] for talib_name, param_key in mapping.items()}
        return {key: fn(*args, **kwargs)}

    return compute


def _bbands(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    upper, middle, lower = talib.BBANDS(bars.close, timeperiod=p["period"], nbdevup=p["stddev"], nbdevdn=p["stddev"])
    return {"upper": upper, "middle": middle, "lower": lower}


def _macd(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    macd, signal, hist = talib.MACD(bars.close, fastperiod=p["fast"], slowperiod=p["slow"], signalperiod=p["signal"])
    return {"macd": macd, "signal": signal, "hist": hist}


def _stoch(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    k, d = talib.STOCH(
        bars.high, bars.low, bars.close, fastk_period=p["k"], slowk_period=p["smooth"], slowd_period=p["d"]
    )
    return {"k": k, "d": d}


def _stochrsi(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    k, d = talib.STOCHRSI(bars.close, timeperiod=p["rsi"], fastk_period=p["k"], fastd_period=p["d"])
    return {"k": k, "d": d}


def _adx(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    n = p["period"]
    return {
        "adx": talib.ADX(bars.high, bars.low, bars.close, timeperiod=n),
        "plus": talib.PLUS_DI(bars.high, bars.low, bars.close, timeperiod=n),
        "minus": talib.MINUS_DI(bars.high, bars.low, bars.close, timeperiod=n),
    }


def _aroon(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    down, up = talib.AROON(bars.high, bars.low, timeperiod=p["period"])
    return {"up": up, "down": down}


def _sar(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    return {"sar": talib.SAR(bars.high, bars.low, acceleration=p["step"], maximum=p["max"])}


def _ppo(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
    return {"ppo": talib.PPO(bars.close, fastperiod=p["fast"], slowperiod=p["slow"])}


def _no_params(fn: Callable[..., np.ndarray], *columns: str, key: str) -> Callable:
    def compute(bars: Bars, p: dict[str, Any]) -> dict[str, np.ndarray]:
        return {key: fn(*(getattr(bars, c) for c in columns))}

    return compute


def _ma(fn: Callable[..., np.ndarray], key: str) -> Callable:
    return _single(fn, "close", key=key, timeperiod="period")


_P = _period

INDICATORS: tuple[Indicator, ...] = (
    # ───────────── Tendencia (sobre el precio) ─────────────
    Indicator("sma", "Media móvil simple (SMA)", "Media aritmética de los últimos N cierres.", "Tendencia", True,
              (_P(20),), (Output("sma", "SMA", PALETTE[0]),), _ma(talib.SMA, "sma")),
    Indicator("ema", "Media móvil exponencial (EMA)", "Media que pesa más los cierres recientes.", "Tendencia", True,
              (_P(20),), (Output("ema", "EMA", PALETTE[1]),), _ma(talib.EMA, "ema")),
    Indicator("wma", "Media móvil ponderada (WMA)", "Media con pesos lineales decrecientes.", "Tendencia", True,
              (_P(20),), (Output("wma", "WMA", PALETTE[2]),), _ma(talib.WMA, "wma")),
    Indicator("dema", "Media móvil doble exponencial (DEMA)", "EMA con menos retraso.", "Tendencia", True,
              (_P(20),), (Output("dema", "DEMA", PALETTE[3]),), _ma(talib.DEMA, "dema")),
    Indicator("tema", "Media móvil triple exponencial (TEMA)", "EMA triple, aún más reactiva.", "Tendencia", True,
              (_P(20),), (Output("tema", "TEMA", PALETTE[4]),), _ma(talib.TEMA, "tema")),
    Indicator("kama", "Media adaptativa de Kaufman (KAMA)", "Se suaviza cuando hay ruido y reacciona en tendencia.", "Tendencia", True,
              (_P(30),), (Output("kama", "KAMA", PALETTE[5]),), _ma(talib.KAMA, "kama")),
    Indicator("bbands", "Bandas de Bollinger", "Media móvil y bandas a N desviaciones estándar.", "Volatilidad", True,
              (_P(20), Param("stddev", "Desviaciones", 2, 0.1, 10, 0.1, "float")),
              (Output("upper", "Superior", PALETTE[0]), Output("middle", "Media", PALETTE[1], "dashed"),
               Output("lower", "Inferior", PALETTE[0])),
              _bbands),
    Indicator("sar", "SAR parabólico", "Puntos de parada y reversión de la tendencia.", "Tendencia", True,
              (Param("step", "Paso", 0.02, 0.001, 1, 0.01, "float"), Param("max", "Máximo", 0.2, 0.01, 1, 0.01, "float")),
              (Output("sar", "SAR", PALETTE[0], "dots"),), _sar),
    # ───────────── Momentum (panel propio) ─────────────
    Indicator("rsi", "Índice de fuerza relativa (RSI)", "Oscilador 0-100: sobrecompra sobre 70, sobreventa bajo 30.", "Momentum", False,
              (_P(14),), (Output("rsi", "RSI", PALETTE[2]),), _single(talib.RSI, "close", key="rsi", timeperiod="period"),
              levels=(30, 70), bounds=(0, 100)),
    Indicator("macd", "MACD", "Diferencia de medias exponenciales, su señal e histograma.", "Momentum", False,
              (Param("fast", "Rápida", 12, 2, 200), Param("slow", "Lenta", 26, 2, 400), Param("signal", "Señal", 9, 1, 200)),
              (Output("macd", "MACD", PALETTE[0]), Output("signal", "Señal", PALETTE[1]), Output("hist", "Histograma", "#171717", "histogram")),
              _macd, levels=(0,)),
    Indicator("stoch", "Estocástico", "Posición del cierre dentro del rango de N velas (%K y %D).", "Momentum", False,
              (Param("k", "%K", 14, 1, 200), Param("smooth", "Suavizado %K", 3, 1, 50), Param("d", "%D", 3, 1, 50)),
              (Output("k", "%K", PALETTE[0]), Output("d", "%D", PALETTE[1])), _stoch,
              levels=(20, 80), bounds=(0, 100)),
    Indicator("stochrsi", "RSI estocástico", "Estocástico aplicado al RSI.", "Momentum", False,
              (Param("rsi", "Periodo RSI", 14, 2, 200), Param("k", "%K", 14, 1, 200), Param("d", "%D", 3, 1, 50)),
              (Output("k", "%K", PALETTE[0]), Output("d", "%D", PALETTE[1])), _stochrsi,
              levels=(20, 80), bounds=(0, 100)),
    Indicator("cci", "Índice del canal de materias primas (CCI)", "Desviación del precio típico respecto a su media.", "Momentum", False,
              (_P(20),), (Output("cci", "CCI", PALETTE[3]),), _single(talib.CCI, "high", "low", "close", key="cci", timeperiod="period"),
              levels=(-100, 100)),
    Indicator("adx", "Índice direccional medio (ADX)", "Fuerza de la tendencia (ADX) y sus direccionales +DI/-DI.", "Momentum", False,
              (_P(14),), (Output("adx", "ADX", PALETTE[6]), Output("plus", "+DI", "#0f8a5f"), Output("minus", "-DI", "#c8102e")), _adx,
              levels=(25,), bounds=(0, 100)),
    Indicator("willr", "Williams %R", "Cierre respecto al máximo del periodo, de -100 a 0.", "Momentum", False,
              (_P(14),), (Output("willr", "%R", PALETTE[2]),), _single(talib.WILLR, "high", "low", "close", key="willr", timeperiod="period"),
              levels=(-80, -20), bounds=(-100, 0)),
    Indicator("mfi", "Índice de flujo de dinero (MFI)", "RSI ponderado por volumen.", "Momentum", False,
              (_P(14),), (Output("mfi", "MFI", PALETTE[3]),), _single(talib.MFI, "high", "low", "close", "volume", key="mfi", timeperiod="period"),
              levels=(20, 80), bounds=(0, 100)),
    Indicator("roc", "Tasa de cambio (ROC)", "Variación porcentual respecto a hace N velas.", "Momentum", False,
              (_P(10),), (Output("roc", "ROC", PALETTE[0]),), _single(talib.ROC, "close", key="roc", timeperiod="period"), levels=(0,)),
    Indicator("mom", "Momentum", "Diferencia de precio respecto a hace N velas.", "Momentum", False,
              (_P(10),), (Output("mom", "MOM", PALETTE[1]),), _single(talib.MOM, "close", key="mom", timeperiod="period"), levels=(0,)),
    Indicator("trix", "TRIX", "Tasa de cambio de una EMA triple.", "Momentum", False,
              (_P(15),), (Output("trix", "TRIX", PALETTE[2]),), _single(talib.TRIX, "close", key="trix", timeperiod="period"), levels=(0,)),
    Indicator("ultosc", "Oscilador último (ULTOSC)", "Momentum en tres periodos combinados.", "Momentum", False,
              (Param("p1", "Periodo 1", 7, 1, 100), Param("p2", "Periodo 2", 14, 1, 200), Param("p3", "Periodo 3", 28, 1, 400)),
              (Output("ultosc", "ULTOSC", PALETTE[3]),),
              lambda b, p: {"ultosc": talib.ULTOSC(b.high, b.low, b.close, timeperiod1=p["p1"], timeperiod2=p["p2"], timeperiod3=p["p3"])},
              levels=(30, 70), bounds=(0, 100)),
    Indicator("cmo", "Oscilador de momentum de Chande (CMO)", "Momentum acotado de -100 a 100.", "Momentum", False,
              (_P(14),), (Output("cmo", "CMO", PALETTE[4]),), _single(talib.CMO, "close", key="cmo", timeperiod="period"),
              levels=(-50, 50), bounds=(-100, 100)),
    Indicator("aroon", "Aroon", "Cuánto hace que se marcó el último máximo (Up) y mínimo (Down).", "Momentum", False,
              (_P(25),), (Output("up", "Up", "#0f8a5f"), Output("down", "Down", "#c8102e")), _aroon,
              levels=(30, 70), bounds=(0, 100)),
    Indicator("ppo", "Oscilador de precio porcentual (PPO)", "MACD expresado en porcentaje.", "Momentum", False,
              (Param("fast", "Rápida", 12, 2, 200), Param("slow", "Lenta", 26, 2, 400)),
              (Output("ppo", "PPO", PALETTE[0]),), _ppo, levels=(0,)),
    # ───────────── Volatilidad (panel propio) ─────────────
    Indicator("atr", "Rango verdadero medio (ATR)", "Volatilidad media del rango de las velas.", "Volatilidad", False,
              (_P(14),), (Output("atr", "ATR", PALETTE[1]),), _single(talib.ATR, "high", "low", "close", key="atr", timeperiod="period")),
    Indicator("natr", "ATR normalizado (NATR)", "ATR en porcentaje del cierre.", "Volatilidad", False,
              (_P(14),), (Output("natr", "NATR", PALETTE[1]),), _single(talib.NATR, "high", "low", "close", key="natr", timeperiod="period")),
    # ───────────── Volumen (panel propio) ─────────────
    Indicator("obv", "Volumen en balance (OBV)", "Volumen acumulado según el cierre suba o baje.", "Volumen", False,
              (), (Output("obv", "OBV", PALETTE[0]),), _no_params(talib.OBV, "close", "volume", key="obv")),
    Indicator("ad", "Acumulación/distribución (A/D)", "Flujo de volumen según dónde cierra la vela.", "Volumen", False,
              (), (Output("ad", "A/D", PALETTE[3]),), _no_params(talib.AD, "high", "low", "close", "volume", key="ad")),
    Indicator("adosc", "Oscilador de Chaikin (ADOSC)", "Diferencia de EMAs de la línea A/D.", "Volumen", False,
              (Param("fast", "Rápida", 3, 2, 100), Param("slow", "Lenta", 10, 2, 200)),
              (Output("adosc", "ADOSC", PALETTE[2]),),
              lambda b, p: {"adosc": talib.ADOSC(b.high, b.low, b.close, b.volume, fastperiod=p["fast"], slowperiod=p["slow"])},
              levels=(0,)),
)

BY_ID: dict[str, Indicator] = {i.id: i for i in INDICATORS}


def catalog() -> dict[str, Any]:
    """Catálogo completo para el diálogo "Indicadores" del navegador."""
    return {
        "palette": PALETTE,
        "categories": list(CATEGORIES),
        "indicators": [i.to_dict() for i in INDICATORS],
    }


def parse_spec(spec: str) -> tuple[Indicator, dict[str, Any]]:
    """Interpreta ``"macd:12,26,9"`` (id y parámetros por orden) y valida los valores.

    Los parámetros que falten toman su valor por defecto. Lanza ``ValueError``
    con un mensaje en español si el indicador no existe o un valor es inválido.
    """
    name, _, raw = (spec or "").strip().partition(":")
    indicator = BY_ID.get(name.strip().lower())
    if indicator is None:
        raise ValueError(f"Indicador desconocido: «{name.strip()[:30]}»")

    values = [v for v in raw.split(",")] if raw.strip() else []
    if len(values) > len(indicator.params):
        raise ValueError(f"«{indicator.name}» admite {len(indicator.params)} parámetros como máximo")

    params = indicator.defaults()
    for param, value in zip(indicator.params, values):
        params[param.key] = param.parse(value)
    return indicator, params


def _clean(array: np.ndarray) -> list[float | None]:
    """Lista JSON-safe: los NaN/inf (periodo de calentamiento) pasan a ``None``."""
    return [round(float(v), 8) if math.isfinite(v) else None for v in array]


def compute_series(candles: Sequence[dict[str, Any]], specs: Sequence[str], since: int | None = None) -> dict[str, Any]:
    """Calcula los indicadores ``specs`` sobre ``candles``.

    ``since`` (epoch en segundos) recorta el resultado a partir de esa vela: se
    calcula sobre más historia de la visible para que las medias largas ya
    estén "calentadas" en la primera vela del gráfico, como en TradingView.
    """
    parsed = [parse_spec(s) for s in specs]
    bars = Bars.from_candles(candles)
    start = 0 if since is None else int(np.searchsorted(bars.time, since, side="left"))

    result = []
    for (indicator, params), spec in zip(parsed, specs):
        if len(bars):
            outputs = {k: _clean(v[start:]) for k, v in indicator.compute(bars, params).items()}
        else:
            outputs = {o.key: [] for o in indicator.outputs}
        result.append({"spec": spec, "outputs": outputs})
    return {"time": [int(t) for t in bars.time[start:]], "indicators": result}


# Orden de los ``range`` de yfinance, de menos a más historia.
_RANGE_ORDER = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max")


def warmup_range(range_: str, interval: str) -> str:
    """``range`` de yfinance con el que calcular para que los indicadores lleguen
    calentados al primer punto visible. Nunca es menor que ``range_`` y respeta
    los límites de Yahoo (intradía: 1 mes a 5m/15m/30m, 1 año a 1h, 7 días a 1m).
    """
    if interval == "1m" or interval.endswith("s"):
        # Yahoo solo da 7 días a 1 minuto, y a segundos (Dukascopy) la historia
        # visible ya es casi todo lo que se puede pedir: no se amplía.
        return range_
    if interval in ("1wk", "1mo"):
        wanted = "max"
    elif interval == "1d":
        wanted = "5y"
    elif interval == "4h":
        wanted = "2y"
    elif interval == "1h":
        wanted = "1y"
    else:
        wanted = "1mo"  # 5m/10m/15m/30m
    return wanted if _RANGE_ORDER.index(wanted) >= _RANGE_ORDER.index(range_) else range_
