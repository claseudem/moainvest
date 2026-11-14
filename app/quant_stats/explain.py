"""Resúmenes en lenguaje llano de las gráficas y tablas de Quant stats.

Cada función recibe métricas ya calculadas (``AssetFacts`` y compañía, que
construye ``quant.asset_facts``) y devuelve 2-4 frases en un español que
entienda cualquiera: qué muestra la gráfica y qué significa para ESE activo
con SUS números. Son funciones puras (sin Flask, sin pandas, sin red ni LLM):
la redacción sale de reglas y umbrales fijos, definidos abajo, para que el
mismo dato produzca siempre el mismo texto y se pueda testear por tramos.

Convenciones de los números: los retornos y las caídas van en fracción
(``0.35`` = 35 %, ``-0.2`` = -20 %); los ratios (Sharpe, Calmar, beta...)
tal cual. Un ``None`` significa "no se pudo calcular" y la frase afectada se
sustituye por un aviso de datos insuficientes.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# Sesiones mínimas para que un resumen tenga sentido (≈ un mes de mercado).
MIN_TRADING_DAYS = 20

INSUFFICIENT = (
    "No hay datos suficientes para resumir esta gráfica: hacen falta al menos "
    f"{MIN_TRADING_DAYS} sesiones de precios. Prueba con un período más largo o con otro activo."
)

MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# --------------------------------------------------------------------------
# Umbrales: (límite inferior, etiqueta), del tramo más alto al más bajo.
# --------------------------------------------------------------------------

# Sharpe (rentabilidad por unidad de riesgo): por encima de 1 se considera bueno.
SHARPE_TIERS = ((2.0, "excelente"), (1.0, "bueno"), (0.5, "razonable"), (0.0, "pobre"))
# Volatilidad anual: un índice amplio como el S&P 500 suele rondar el 15-20 %.
VOLATILITY_TIERS = ((0.50, "muy alta"), (0.30, "alta"), (0.15, "moderada"), (0.0, "baja"))
# Peor caída desde máximos (en positivo: 0.35 = caída del 35 %).
DRAWDOWN_TIERS = ((0.50, "muy fuerte"), (0.25, "fuerte"), (0.10, "moderada"), (0.0, "leve"))
# Calmar: rentabilidad anual / peor caída. Por encima de 1, se gana al año más de lo que se llegó a perder.
CALMAR_TIERS = ((3.0, "muy bueno"), (1.0, "bueno"), (0.5, "aceptable"), (0.0, "bajo"))
# Probabilidad de "bust" en la simulación Monte Carlo.
BUST_TIERS = ((0.40, "alta"), (0.10, "moderada"), (0.0, "baja"))
# Beta frente al benchmark.
BETA_TIERS = (
    (1.2, "amplifica los movimientos del mercado de referencia"),
    (0.8, "se mueve más o menos como el mercado de referencia"),
    (0.5, "es menos sensible que el mercado de referencia"),
    (0.0, "apenas sigue al mercado de referencia"),
)
# Volatilidad / Sharpe móviles: cuánto se aleja el valor actual de su media.
ROLLING_HIGH = 1.2
ROLLING_LOW = 0.8
# Asimetría (skew) y curtosis en exceso (0 en una campana normal).
SKEW_THRESHOLD = 0.5
FAT_TAILS_KURTOSIS = 3.0
# Un día con un movimiento mayor que esto se considera extremo.
BIG_DAY = 0.10
# Diferencias que se consideran un empate al comparar dos retornos (puntos porcentuales).
TIE_POINTS = 0.02


def _tier(value: float, tiers: tuple[tuple[float, str], ...]) -> str:
    for low, label in tiers:
        if value >= low:
            return label
    return tiers[-1][1]


def sharpe_label(sharpe: float) -> str:
    """Calificación de un Sharpe: negativo, pobre, razonable, bueno o excelente."""
    return "negativo" if sharpe < 0 else _tier(sharpe, SHARPE_TIERS)


def volatility_label(volatility: float) -> str:
    return _tier(volatility, VOLATILITY_TIERS)


def drawdown_label(drawdown: float) -> str:
    return _tier(abs(drawdown), DRAWDOWN_TIERS)


def calmar_label(calmar: float) -> str:
    return "negativo" if calmar < 0 else _tier(calmar, CALMAR_TIERS)


def bust_label(probability: float) -> str:
    return _tier(probability, BUST_TIERS)


def beta_label(beta: float) -> str:
    return "tiende a moverse en sentido contrario al mercado de referencia" if beta < 0 else _tier(beta, BETA_TIERS)


# --------------------------------------------------------------------------
# Formato de números en español
# --------------------------------------------------------------------------

NBSP = " "


def _decimal(value: float, decimals: int) -> str:
    """``1234.5`` -> ``1.234,5`` (separadores españoles)."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: float, *, signed: bool = False, decimals: int | None = None) -> str:
    """Fracción -> porcentaje legible: ``0.352`` -> ``35 %``; ``0.0123`` -> ``1,2 %``."""
    number = value * 100
    if decimals is None:
        decimals = 0 if abs(number) >= 10 else 1
    text = _decimal(abs(number) if not signed else number, decimals)
    if signed and number > 0:
        text = "+" + text
    if text in ("-0", "-0,0", "+0", "+0,0"):
        text = text[1:]
    return f"{text}{NBSP}%"


def num(value: float, decimals: int = 1) -> str:
    return _decimal(value, decimals)


def money(value: float) -> str:
    return f"{_decimal(value, 0)}{NBSP}USD"


def duration(days: int) -> str:
    """Días naturales -> ``12 días``, ``8 meses``, ``1 año y 3 meses``."""
    if days < 45:
        return f"{days} día" if days == 1 else f"{days} días"
    months = round(days / 30.44)
    if months < 12:
        return "1 mes" if months == 1 else f"{months} meses"
    years, rest = divmod(months, 12)
    text = "1 año" if years == 1 else f"{years} años"
    if rest:
        text += " y 1 mes" if rest == 1 else f" y {rest} meses"
    return text


def month_label(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} de {year}"


# --------------------------------------------------------------------------
# Datos de entrada
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DrawdownPeriod:
    """Un bache: desde un máximo hasta que el precio lo recupera (o hasta hoy)."""

    depth: float  # fracción negativa: -0.35
    days: int  # días naturales que duró (o lleva) el bache
    recovered: bool


@dataclass(frozen=True, slots=True)
class Rolling:
    """Una métrica en ventana móvil: su valor más reciente y su media."""

    current: float
    average: float


@dataclass(frozen=True, slots=True)
class AssetFacts:
    """Métricas de un activo en un período, listas para redactar."""

    ticker: str
    trading_days: int = 0
    start: str = ""  # "enero de 2025"
    end: str = ""
    cumulative_return: float | None = None
    cagr: float | None = None
    volatility: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    current_drawdown: float | None = None
    drawdowns: tuple[DrawdownPeriod, ...] = ()  # los peores primero
    best_day: float | None = None
    worst_day: float | None = None
    typical_day: float | None = None  # desviación típica diaria
    typical_month: float | None = None  # desviación típica mensual
    win_rate_days: float | None = None
    win_rate_months: float | None = None
    months_total: int = 0
    months_positive: int = 0
    average_month: float | None = None
    best_month: tuple[str, float] | None = None  # ("marzo de 2025", 0.23)
    worst_month: tuple[str, float] | None = None
    yearly: tuple[tuple[int, float], ...] = ()  # (año, retorno)
    value_at_risk: float | None = None
    expected_shortfall: float | None = None
    skew: float | None = None
    kurtosis: float | None = None
    calmar: float | None = None
    omega: float | None = None
    probabilistic_sharpe: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    payoff_ratio: float | None = None
    profit_factor: float | None = None
    max_loss_streak: int | None = None
    max_win_streak: int | None = None
    rolling_window_label: str = ""  # "6 meses"
    rolling_volatility: Rolling | None = None
    rolling_sharpe: Rolling | None = None
    rolling_sortino: Rolling | None = None

    @property
    def enough(self) -> bool:
        return self.trading_days >= MIN_TRADING_DAYS and self.cumulative_return is not None


@dataclass(frozen=True, slots=True)
class BenchmarkFacts:
    """El benchmark de la comparación y cómo se relaciona con el activo."""

    facts: AssetFacts
    beta: float | None = None
    correlation: float | None = None


class EarningsLike(Protocol):
    """Lo que necesita ``earnings`` de cada reporte (``quant.EarningsReport``)."""

    label: str
    eps_estimate: float | None
    eps_reported: float
    surprise_percent: float | None
    price_change_percent: float | None


def _join(*sentences: str | None) -> str:
    return " ".join(s for s in sentences if s)


def _enough(*facts: AssetFacts | None) -> bool:
    return all(f is not None and f.enough for f in facts)


# --------------------------------------------------------------------------
# Frases reutilizables
# --------------------------------------------------------------------------


def _return_sentence(f: AssetFacts) -> str:
    verb = "ganó" if f.cumulative_return >= 0 else "perdió"
    text = f"Entre {f.start} y {f.end}, {f.ticker} {verb} un {pct(f.cumulative_return)} en total"
    if f.cagr is not None and f.trading_days >= 252:
        text += f" ({pct(f.cagr, signed=True)} al año de media)"
    return text + "."


def _drawdown_sentence(f: AssetFacts) -> str | None:
    if f.max_drawdown is None:
        return None
    if f.max_drawdown >= -0.001:
        return "No llegó a caer por debajo de su máximo anterior en todo el período."
    worst = f.drawdowns[0] if f.drawdowns else None
    text = f"En el peor momento llegó a perder un {pct(f.max_drawdown)} desde su máximo (una caída {drawdown_label(f.max_drawdown)})"
    if worst is None:
        return text + "."
    if worst.recovered:
        return text + f" y tardó {duration(worst.days)} en recuperarse."
    return text + f" y, tras {duration(worst.days)}, todavía no lo ha recuperado."


def _volatility_sentence(f: AssetFacts) -> str | None:
    if f.volatility is None:
        return None
    return (
        f"Su volatilidad —cuánto sube y baja el precio— es {volatility_label(f.volatility)}: "
        f"un {pct(f.volatility)} anual, cuando un índice amplio como el S&P 500 suele rondar el 15-20{NBSP}%."
    )


def _sharpe_sentence(f: AssetFacts) -> str | None:
    if f.sharpe is None:
        return None
    label = sharpe_label(f.sharpe)
    if label == "negativo":
        return (
            f"El ratio de Sharpe, que mide cuánto rinde por cada unidad de riesgo, es negativo ({num(f.sharpe, 2)}): "
            "asumir esos vaivenes no se vio recompensado."
        )
    return (
        f"Por cada unidad de riesgo obtuvo un rendimiento {label} (Sharpe {num(f.sharpe)}; "
        "por encima de 1 se considera bueno)."
    )


# --------------------------------------------------------------------------
# Fundamentales: tarjetas de resumen y tablas de stats
# --------------------------------------------------------------------------


def overview(f: AssetFacts | None) -> str:
    """Las 5 métricas clave (retorno, volatilidad, Sharpe, Sortino y peor caída)."""
    if not _enough(f):
        return INSUFFICIENT
    return _join(_return_sentence(f), _volatility_sentence(f), _drawdown_sentence(f), _sharpe_sentence(f))


def stat_group(title: str, f: AssetFacts | None) -> str:
    """Resumen de una tabla de ``quant.STAT_GROUPS`` (por su título)."""
    if not _enough(f):
        return INSUFFICIENT
    writer = _GROUP_WRITERS.get(title)
    return writer(f) if writer else ""


def _group_performance(f: AssetFacts) -> str:
    sentences = []
    if f.cagr is not None:
        verb = "crecer" if f.cagr >= 0 else "encoger"
        sentences.append(
            f"Quien hubiera mantenido {f.ticker} todo el período habría visto {verb} su inversión "
            f"a un ritmo de {pct(f.cagr, signed=True)} al año (el CAGR, o crecimiento anual compuesto)."
        )
    if f.best_day is not None and f.worst_day is not None:
        sentences.append(f"Su mejor día subió un {pct(f.best_day)} y el peor cayó un {pct(f.worst_day)}.")
        if max(abs(f.best_day), abs(f.worst_day)) >= BIG_DAY:
            sentences.append("Movimientos de más del 10 % en una sola sesión son propios de un activo muy nervioso.")
    if f.best_month and f.worst_month:
        sentences.append(
            f"El mejor mes fue {f.best_month[0]} ({pct(f.best_month[1], signed=True)}) "
            f"y el peor, {f.worst_month[0]} ({pct(f.worst_month[1], signed=True)})."
        )
    return _join(*sentences[:4]) or INSUFFICIENT


def _group_risk(f: AssetFacts) -> str:
    sentences = []
    if f.value_at_risk is not None:
        text = (
            f"En 1 de cada 20 sesiones, las peores, cabe esperar perder un {pct(f.value_at_risk)} o más "
            "(es el «Value at Risk» al 95 %)"
        )
        if f.expected_shortfall is not None:
            text += f"; cuando eso ocurre, la pérdida media ronda el {pct(f.expected_shortfall)} (Expected Shortfall)"
        sentences.append(text + ".")
    if f.skew is not None:
        if f.skew <= -SKEW_THRESHOLD:
            sentences.append("Las caídas bruscas son más habituales que las subidas bruscas (asimetría negativa).")
        elif f.skew >= SKEW_THRESHOLD:
            sentences.append("Tiende a dar más sorpresas al alza que a la baja (asimetría positiva).")
        else:
            sentences.append("Las subidas y bajadas extremas están bastante equilibradas (asimetría cercana a cero).")
    if f.kurtosis is not None:
        if f.kurtosis >= FAT_TAILS_KURTOSIS:
            sentences.append(
                "Además, los días extremos aparecen más a menudo de lo normal («colas gordas», curtosis "
                f"{num(f.kurtosis)}): conviene estar preparado para sustos."
            )
        else:
            sentences.append("Los días extremos no son especialmente frecuentes (curtosis baja).")
    return _join(*sentences) or INSUFFICIENT


def _group_risk_adjusted(f: AssetFacts) -> str:
    sentences = []
    if f.calmar is not None:
        sentences.append(
            f"El ratio Calmar compara lo que gana al año con su peor caída: vale {num(f.calmar, 2)}, "
            f"un resultado {calmar_label(f.calmar)} (por encima de 1 se gana al año más de lo que se llegó a perder)."
        )
    if f.omega is not None:
        if f.omega >= 1:
            sentences.append(f"Las ganancias pesan más que las pérdidas (Omega {num(f.omega, 2)}, por encima de 1).")
        else:
            sentences.append(f"Las pérdidas pesan más que las ganancias (Omega {num(f.omega, 2)}, por debajo de 1).")
    if f.probabilistic_sharpe is not None:
        sentences.append(
            f"Hay un {pct(f.probabilistic_sharpe)} de probabilidad de que su rentabilidad ajustada al riesgo sea "
            "realmente positiva y no fruto de la suerte."
        )
    return _join(*sentences) or INSUFFICIENT


def _group_daily(f: AssetFacts) -> str:
    sentences = []
    if f.win_rate_days is not None:
        text = f"Subió en el {pct(f.win_rate_days)} de las sesiones"
        if f.win_rate_months is not None:
            text += f" y en el {pct(f.win_rate_months)} de los meses"
        sentences.append(text + ".")
    if f.avg_win is not None and f.avg_loss is not None:
        sentences.append(
            f"Un día bueno sube de media un {pct(f.avg_win)} y uno malo baja un {pct(f.avg_loss)}."
        )
    if f.profit_factor is not None:
        verdict = "compensa" if f.profit_factor >= 1 else "no compensa"
        sentences.append(
            f"Sumando todo, por cada dólar perdido en los días malos ganó {num(f.profit_factor, 2)} en los buenos "
            f"(profit factor): {verdict}."
        )
    if f.max_loss_streak:
        sentences.append(f"Su peor racha fue de {f.max_loss_streak} sesiones seguidas en negativo.")
    return _join(*sentences[:4]) or INSUFFICIENT


_GROUP_WRITERS = {
    "Rendimiento": _group_performance,
    "Riesgo": _group_risk,
    "Rendimiento ajustado por riesgo": _group_risk_adjusted,
    "Operativa diaria": _group_daily,
}


# --------------------------------------------------------------------------
# Monte Carlo
# --------------------------------------------------------------------------


def montecarlo(
    ticker: str,
    *,
    sims: int,
    bust: float,
    bust_probability: float | None,
    median_drawdown: float | None,
    worst_drawdown: float | None,
) -> str:
    """Simulación Monte Carlo: probabilidad de una caída grave en caminos alternativos."""
    if bust_probability is None or median_drawdown is None or worst_drawdown is None:
        return INSUFFICIENT
    intro = (
        f"Monte Carlo baraja {sims} veces el orden de los días reales de {ticker} para imaginar otros caminos que "
        "podría haber seguido el precio con las mismas subidas y bajadas."
    )
    paths = (
        f"En la mitad de esos caminos la peor caída superó el {pct(median_drawdown)}, "
        f"y en el 5 % más desfavorable llegó al {pct(worst_drawdown)}."
    )
    if bust_probability >= 0.995:
        risk = f"Sufrir una caída de al menos el {pct(bust)} (el umbral «bust») es prácticamente seguro."
    else:
        risk = (
            f"La probabilidad de sufrir una caída de al menos el {pct(bust)} (el umbral «bust») es del "
            f"{pct(bust_probability)}: {bust_label(bust_probability)}."
        )
    return _join(intro, paths, risk)


# --------------------------------------------------------------------------
# Gráficas (quant.PLOTS), por slug
# --------------------------------------------------------------------------


def plot(slug: str, f: AssetFacts | None, benchmark: BenchmarkFacts | None = None) -> str:
    """Resumen de la gráfica ``slug``; con ``benchmark``, añade la comparación."""
    if not _enough(f):
        return INSUFFICIENT
    if slug == "rolling-beta":
        return _plot_beta(f, benchmark)
    writer = _PLOT_WRITERS.get(slug)
    if writer is None:
        return ""
    text = writer(f)
    if benchmark is not None and benchmark.facts.enough:
        text = _join(text, _versus(slug, f, benchmark.facts))
    return text


def _plot_snapshot(f: AssetFacts) -> str:
    return _join(
        "Tres vistas en una: arriba, cuánto ha crecido la inversión; en medio, las caídas desde máximos; abajo, cada día.",
        _return_sentence(f),
        _drawdown_sentence(f),
    )


def _plot_returns(f: AssetFacts) -> str:
    end = "por encima" if f.cumulative_return >= 0 else "por debajo"
    return _join(
        "La línea muestra cuánto habría ganado o perdido quien invirtiera al principio del período.",
        _return_sentence(f),
        f"Termina {end} del punto de partida.",
    )


def _plot_log_returns(f: AssetFacts) -> str:
    return _join(
        "Es la misma curva de crecimiento en escala logarítmica: una subida del 10 % mide igual empiece en 10 o en "
        "100 dólares, así que los tramos antiguos y los recientes se comparan de tú a tú.",
        _return_sentence(f),
    )


def _plot_daily(f: AssetFacts) -> str:
    if f.typical_day is None or f.best_day is None or f.worst_day is None:
        return INSUFFICIENT
    text = (
        f"Cada barra es lo que subió o bajó {f.ticker} en una sesión. Un día normal se mueve alrededor de "
        f"±{pct(f.typical_day)}; el mejor fue {pct(f.best_day, signed=True)} y el peor {pct(f.worst_day, signed=True)}."
    )
    if f.win_rate_days is not None:
        text += f" Cerró en positivo el {pct(f.win_rate_days)} de los días."
    return text


def _plot_yearly(f: AssetFacts) -> str:
    if not f.yearly:
        return INSUFFICIENT
    if len(f.yearly) == 1:
        year, value = f.yearly[0]
        return (
            f"Cada barra es el resultado de un año natural. En el período solo entra {year}, con un "
            f"{pct(value, signed=True)}; elige un período más largo para comparar años."
        )
    best = max(f.yearly, key=lambda item: item[1])
    worst = min(f.yearly, key=lambda item: item[1])
    positives = sum(1 for _, value in f.yearly if value > 0)
    return (
        f"Cada barra es el resultado de un año natural (el último puede estar incompleto). El mejor fue {best[0]} "
        f"({pct(best[1], signed=True)}) y el peor {worst[0]} ({pct(worst[1], signed=True)}); "
        f"{positives} de {len(f.yearly)} años terminaron en positivo."
    )


def _months_sentence(f: AssetFacts) -> str | None:
    if not f.months_total:
        return None
    share = f.months_positive / f.months_total
    if share == 1:
        verdict = "todos"
    elif share == 0:
        verdict = "ninguno"
    elif share >= 0.6:
        verdict = "la mayoría"
    elif share >= 0.4:
        verdict = "más o menos la mitad"
    else:
        verdict = "una minoría"
    return f"{f.months_positive} de {f.months_total} meses fueron positivos: {verdict}."


def _plot_histogram(f: AssetFacts) -> str:
    if f.typical_month is None or f.average_month is None:
        return INSUFFICIENT
    return _join(
        "Agrupa los meses según su resultado: cuanto más estrecha y alta la montaña, más predecible es el activo.",
        f"Un mes normal se movió ±{pct(f.typical_month)}, con una media de {pct(f.average_month, signed=True)} al mes.",
        _months_sentence(f),
    )


def _plot_distribution(f: AssetFacts) -> str:
    if f.typical_day is None or f.typical_month is None:
        return INSUFFICIENT
    return (
        "Cada caja muestra el rango habitual de resultados en un plazo distinto: día, semana, mes, trimestre y año. "
        f"Un día normal oscila ±{pct(f.typical_day)} y un mes ±{pct(f.typical_month)}: cuanto más largo el plazo, "
        "más amplio el rango, pero el ruido diario pesa menos."
    )


def _plot_heatmap(f: AssetFacts) -> str:
    if not f.best_month or not f.worst_month:
        return INSUFFICIENT
    return _join(
        "Cada casilla es un mes: verde si subió y rojo si bajó, más intenso cuanto mayor el movimiento.",
        f"El mejor fue {f.best_month[0]} ({pct(f.best_month[1], signed=True)}) y el peor, "
        f"{f.worst_month[0]} ({pct(f.worst_month[1], signed=True)}).",
        _months_sentence(f),
    )


def _plot_drawdown(f: AssetFacts) -> str:
    sentences = [
        "La zona sombreada mide cuánto está el precio por debajo de su máximo anterior (el «drawdown»).",
        _drawdown_sentence(f),
    ]
    if f.current_drawdown is not None:
        if f.current_drawdown <= -0.01:
            sentences.append(f"Ahora mismo está un {pct(f.current_drawdown)} por debajo de su máximo.")
        else:
            sentences.append("Ahora mismo cotiza en máximos o muy cerca de ellos.")
    return _join(*sentences)


def _plot_drawdown_periods(f: AssetFacts) -> str:
    if not f.drawdowns:
        return "No hubo caídas desde máximos en el período: no hay baches que marcar."
    worst = f.drawdowns[0]
    longest = max(f.drawdowns, key=lambda d: d.days)
    recovered = sum(1 for d in f.drawdowns if d.recovered)
    n = len(f.drawdowns)
    text = (
        f"Las franjas marcan los {n} peores baches del período sobre la curva de crecimiento. "
        f"El peor restó un {pct(worst.depth)} y duró {duration(worst.days)}"
    )
    text += "." if longest is worst else f"; el más largo se alargó {duration(longest.days)}."
    return text + f" {recovered} de {n} ya se recuperaron."


def _rolling_text(metric: Rolling, window: str, *, as_pct: bool) -> str:
    fmt = (lambda v: pct(v)) if as_pct else (lambda v: num(v, 2))
    return f"Ahora está en {fmt(metric.current)} frente a una media de {fmt(metric.average)} en ventanas de {window}"


def _plot_rolling_volatility(f: AssetFacts) -> str:
    rolling = f.rolling_volatility
    if rolling is None:
        return INSUFFICIENT
    ratio = rolling.current / rolling.average if rolling.average else 1.0
    if ratio >= ROLLING_HIGH:
        verdict = "más agitado de lo habitual"
    elif ratio <= ROLLING_LOW:
        verdict = "más tranquilo de lo habitual"
    else:
        verdict = "en línea con lo habitual"
    return (
        "Mide la volatilidad (cuánto sube y baja el precio) de forma continua, para ver si el activo atraviesa una "
        f"etapa tranquila o agitada. {_rolling_text(rolling, f.rolling_window_label, as_pct=True)}: "
        f"{verdict}."
    )


def _plot_rolling_ratio(f: AssetFacts, rolling: Rolling | None, intro: str) -> str:
    if rolling is None:
        return INSUFFICIENT
    if rolling.current < 0:
        verdict = "en la ventana más reciente se está perdiendo dinero"
    else:
        verdict = f"el momento actual es {sharpe_label(rolling.current)}"
    if abs(rolling.current - rolling.average) <= 0.1 * max(abs(rolling.average), 0.1):
        trend = "parecido a su media"
    else:
        trend = ("mejor" if rolling.current > rolling.average else "peor") + " que su media"
    return (
        f"{intro} {_rolling_text(rolling, f.rolling_window_label, as_pct=False)}: {verdict} y {trend}. "
        "Por encima de 1 es bueno; por debajo de 0, la ventana acumula pérdidas."
    )


def _plot_rolling_sharpe(f: AssetFacts) -> str:
    return _plot_rolling_ratio(
        f, f.rolling_sharpe,
        "El Sharpe móvil calcula, ventana a ventana, si la rentabilidad compensaba el riesgo asumido.",
    )


def _plot_rolling_sortino(f: AssetFacts) -> str:
    return _plot_rolling_ratio(
        f, f.rolling_sortino,
        "El Sortino móvil es como el Sharpe pero solo cuenta como riesgo las caídas, no las subidas.",
    )


def _plot_growth(f: AssetFacts) -> str:
    final = 100_000 * (1 + f.cumulative_return)
    diff = final - 100_000
    verb = "una ganancia" if diff >= 0 else "una pérdida"
    return (
        f"Muestra en qué se habrían convertido 100.000 USD invertidos en {f.ticker} en {f.start}. "
        f"Hoy valdrían unos {money(final)}: {verb} de {money(abs(diff))}."
    )


def _plot_beta(f: AssetFacts, benchmark: BenchmarkFacts | None) -> str:
    if benchmark is None or benchmark.beta is None:
        return (
            "La beta mide cuánto amplifica el activo los movimientos de un mercado de referencia. "
            "No se pudo calcular por falta de datos del benchmark."
        )
    bench = benchmark.facts.ticker
    text = (
        f"La beta mide cuánto amplifica {f.ticker} los movimientos de {bench}. Con una beta de {num(benchmark.beta, 2)}, "
        f"cuando {bench} se mueve un 1 %, {f.ticker} tiende a moverse un {num(benchmark.beta, 2)}{NBSP}%: "
        f"{beta_label(benchmark.beta)}."
    )
    if benchmark.correlation is not None:
        strength = "fuerte" if abs(benchmark.correlation) >= 0.7 else "moderada" if abs(benchmark.correlation) >= 0.4 else "débil"
        text += f" La relación entre ambos es {strength} (correlación {num(benchmark.correlation, 2)})."
    return text


_PLOT_WRITERS = {
    "snapshot": _plot_snapshot,
    "returns": _plot_returns,
    "log-returns": _plot_log_returns,
    "daily-returns": _plot_daily,
    "yearly-returns": _plot_yearly,
    "histogram": _plot_histogram,
    "distribution": _plot_distribution,
    "monthly-heatmap": _plot_heatmap,
    "drawdown": _plot_drawdown,
    "drawdowns-periods": _plot_drawdown_periods,
    "rolling-volatility": _plot_rolling_volatility,
    "rolling-sharpe": _plot_rolling_sharpe,
    "rolling-sortino": _plot_rolling_sortino,
    "earnings": _plot_growth,
}


def _beat(a: float, b: float, higher_is_better: bool = True) -> str:
    better = a > b if higher_is_better else a < b
    return "mejor" if better else "peor"


def _versus(slug: str, f: AssetFacts, b: AssetFacts) -> str | None:
    """Frase de comparación con el benchmark para la gráfica ``slug``."""
    if slug in {"returns", "log-returns", "monthly-heatmap", "histogram", "yearly-returns", "daily-returns"}:
        diff = f.cumulative_return - b.cumulative_return
        if abs(diff) < TIE_POINTS:
            return f"En el mismo tiempo, {b.ticker} hizo prácticamente lo mismo ({pct(b.cumulative_return, signed=True)})."
        verb = "superó" if diff > 0 else "quedó por detrás de"
        return (
            f"En el mismo tiempo, {b.ticker} hizo un {pct(b.cumulative_return, signed=True)}: {f.ticker} "
            f"{verb} {b.ticker} por {num(abs(diff) * 100, 0)} puntos porcentuales."
        )
    if slug == "rolling-volatility" and f.volatility is not None and b.volatility is not None:
        word = "más" if f.volatility > b.volatility else "menos"
        return f"En todo el período fue {word} volátil que {b.ticker} ({pct(f.volatility)} frente a {pct(b.volatility)})."
    if slug in {"rolling-sharpe", "rolling-sortino"} and f.sharpe is not None and b.sharpe is not None:
        return (
            f"En el conjunto del período, su Sharpe ({num(f.sharpe, 2)}) fue {_beat(f.sharpe, b.sharpe)} que el de "
            f"{b.ticker} ({num(b.sharpe, 2)})."
        )
    return None


# --------------------------------------------------------------------------
# Comparativas: período vs. período y activo vs. benchmark
# --------------------------------------------------------------------------


def compare_periods(f: AssetFacts | None, label: str, other: AssetFacts | None, other_label: str) -> str:
    """Las mismas gráficas en dos períodos distintos, lado a lado."""
    if not _enough(f, other):
        return INSUFFICIENT

    def part(facts: AssetFacts, name: str) -> str:
        verb = "ganó" if facts.cumulative_return >= 0 else "perdió"
        text = f"en {name.lower()} {verb} un {pct(facts.cumulative_return)}"
        if facts.max_drawdown is not None:
            text += f" con una peor caída del {pct(facts.max_drawdown)}"
        return text

    text = f"Mirando {f.ticker} con dos lupas distintas: {part(f, label)}; {part(other, other_label)}."
    if f.sharpe is not None and other.sharpe is not None:
        best = label if f.sharpe >= other.sharpe else other_label
        text += (
            f" Teniendo en cuenta el riesgo, el mejor tramo fue {best.lower()} (Sharpe {num(max(f.sharpe, other.sharpe), 2)} "
            f"frente a {num(min(f.sharpe, other.sharpe), 2)})."
        )
    return text + " Un período largo suaviza los baches; uno corto refleja mejor el momento actual."


def comparison_group(title: str, f: AssetFacts | None, b: AssetFacts | None) -> str:
    """Resumen de una tabla de métricas del activo frente a su benchmark."""
    if not _enough(f, b):
        return INSUFFICIENT
    writer = _COMPARISON_WRITERS.get(title)
    return writer(f, b) if writer else ""


def _compare_summary(f: AssetFacts, b: AssetFacts) -> str:
    sentences = []
    diff = f.cumulative_return - b.cumulative_return
    if abs(diff) < TIE_POINTS:
        sentences.append(f"{f.ticker} y {b.ticker} rindieron prácticamente lo mismo en el período.")
    else:
        verb = "rindió más" if diff > 0 else "rindió menos"
        sentences.append(
            f"{f.ticker} {verb} que {b.ticker}: {pct(f.cumulative_return, signed=True)} frente a "
            f"{pct(b.cumulative_return, signed=True)}."
        )
    if f.volatility is not None and b.volatility is not None and b.volatility > 0:
        ratio = f.volatility / b.volatility
        if ratio >= ROLLING_HIGH:
            sentences.append(f"A cambio, se movió con bastante más brusquedad ({num(ratio)} veces la volatilidad de {b.ticker}).")
        elif ratio <= ROLLING_LOW:
            sentences.append(f"Y lo hizo con menos sobresaltos ({num(ratio)} veces la volatilidad de {b.ticker}).")
        else:
            sentences.append(f"Su volatilidad fue parecida a la de {b.ticker}.")
    if f.max_drawdown is not None and b.max_drawdown is not None:
        sentences.append(
            f"Su peor caída fue del {pct(f.max_drawdown)}, frente al {pct(b.max_drawdown)} de {b.ticker}."
        )
    if f.sharpe is not None and b.sharpe is not None:
        sentences.append(
            f"Ajustado por riesgo (Sharpe), el resultado de {f.ticker} fue {_beat(f.sharpe, b.sharpe)} "
            f"({num(f.sharpe, 2)} frente a {num(b.sharpe, 2)})."
        )
    return _join(*sentences[:4])


def _compare_performance(f: AssetFacts, b: AssetFacts) -> str:
    sentences = []
    if f.cagr is not None and b.cagr is not None:
        sentences.append(
            f"Al año, {f.ticker} creció a un ritmo de {pct(f.cagr, signed=True)} y {b.ticker} de {pct(b.cagr, signed=True)} "
            "(CAGR, crecimiento anual compuesto)."
        )
    if None not in (f.best_day, f.worst_day, b.best_day, b.worst_day):
        wider = abs(f.worst_day) + f.best_day > abs(b.worst_day) + b.best_day
        sentences.append(
            f"Sus días extremos fueron {'más' if wider else 'menos'} violentos: de {pct(f.worst_day, signed=True)} a "
            f"{pct(f.best_day, signed=True)}, frente a {pct(b.worst_day, signed=True)} y {pct(b.best_day, signed=True)} "
            f"de {b.ticker}."
        )
    return _join(*sentences) or INSUFFICIENT


def _compare_risk(f: AssetFacts, b: AssetFacts) -> str:
    if f.value_at_risk is None or b.value_at_risk is None:
        return INSUFFICIENT
    riskier = abs(f.value_at_risk) > abs(b.value_at_risk)
    return (
        f"En un día malo (uno de cada 20), {f.ticker} puede perder un {pct(f.value_at_risk)} o más, y {b.ticker} un "
        f"{pct(b.value_at_risk)} (Value at Risk al 95 %). Por tanto, el día a día de {f.ticker} es "
        f"{'más' if riskier else 'menos'} arriesgado que el de su referencia."
    )


def _compare_risk_adjusted(f: AssetFacts, b: AssetFacts) -> str:
    if f.calmar is None or b.calmar is None:
        return INSUFFICIENT
    return (
        f"El ratio Calmar (lo que gana al año dividido entre su peor caída) es de {num(f.calmar, 2)} para {f.ticker} y "
        f"{num(b.calmar, 2)} para {b.ticker}: en relación con los sustos que dio, {f.ticker} lo hizo "
        f"{_beat(f.calmar, b.calmar)} que su referencia. Por encima de 1 se considera bueno."
    )


def _compare_daily(f: AssetFacts, b: AssetFacts) -> str:
    if f.win_rate_days is None or b.win_rate_days is None:
        return INSUFFICIENT
    text = (
        f"{f.ticker} subió en el {pct(f.win_rate_days)} de las sesiones y {b.ticker} en el {pct(b.win_rate_days)}."
    )
    if f.profit_factor is not None and b.profit_factor is not None:
        text += (
            f" Por cada dólar perdido en los días malos, {f.ticker} ganó {num(f.profit_factor, 2)} en los buenos y "
            f"{b.ticker} {num(b.profit_factor, 2)} (profit factor; por encima de 1 compensa)."
        )
    return text


_COMPARISON_WRITERS = {
    "Resumen": _compare_summary,
    "Rendimiento": _compare_performance,
    "Riesgo": _compare_risk,
    "Rendimiento ajustado por riesgo": _compare_risk_adjusted,
    "Operativa diaria": _compare_daily,
}


# --------------------------------------------------------------------------
# Earnings
# --------------------------------------------------------------------------


def earnings(ticker: str, reports: Sequence[EarningsLike]) -> str:
    """Últimos reportes de resultados: sorpresas frente a lo esperado y reacción del precio."""
    if not reports:
        return (
            f"No hay reportes de resultados de {ticker}. Los índices, ETFs, divisas y criptomonedas no publican "
            "resultados trimestrales."
        )
    n = len(reports)
    sentences = [
        f"Cada trimestre la empresa publica su beneficio por acción (EPS): lo que gana por cada acción. "
        f"Aquí se comparan sus últimos {n} reportes con lo que esperaban los analistas."
    ]
    with_estimate = [r for r in reports if r.eps_estimate is not None]
    if with_estimate:
        beats = sum(1 for r in with_estimate if r.eps_reported >= r.eps_estimate)
        if beats == len(with_estimate):
            verdict = "en todos ellos"
        elif beats == 0:
            verdict = "en ninguno"
        else:
            verdict = f"en {beats} de {len(with_estimate)}"
        sentences.append(f"{ticker} igualó o superó las previsiones {verdict}.")
    first, last = reports[0], reports[-1]
    if n >= 2:
        trend = "mejorado" if last.eps_reported > first.eps_reported else "empeorado" if last.eps_reported < first.eps_reported else "repetido"
        sentences.append(
            f"El EPS ha {trend} del primer reporte ({num(first.eps_reported, 2)}) al último ({num(last.eps_reported, 2)}); "
            "ojo, en muchas empresas unos trimestres son más fuertes que otros por temporada."
        )
    moves = [r.price_change_percent for r in reports if r.price_change_percent is not None]
    if moves:
        average = sum(moves) / len(moves) / 100
        verb = "subió" if average >= 0 else "bajó"
        sentences.append(f"Entre un reporte y el siguiente, la acción {verb} de media un {pct(average)}.")
    return _join(*sentences[:4])


# --------------------------------------------------------------------------
# Tearsheet
# --------------------------------------------------------------------------


def tearsheet(f: AssetFacts | None) -> str:
    """Breve presentación del tearsheet de quantstats (informe completo en otra pestaña)."""
    if not _enough(f):
        return INSUFFICIENT
    return (
        f"El tearsheet reúne en una sola página todas las métricas y gráficas de {f.ticker} entre {f.start} y {f.end}. "
        "Es la versión «para expertos» de esta página: úsalo si quieres guardarlo o compartirlo."
    )
