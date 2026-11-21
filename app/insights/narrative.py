"""Textos de Insights: cada cifra con una frase en lenguaje humano, siempre
anclada al benchmark, y el glosario "¿Qué significa?" de las 4 tarjetas."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.insights.engine import Insight, SUSPICIOUS_SHARPE


def pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def money(value: float) -> str:
    return f"${value:,.0f}"


@dataclass(frozen=True, slots=True)
class Glossary:
    definition: str
    good_bad: str
    limitation: str


GLOSSARY: dict[str, Glossary] = {
    "total": Glossary(
        "Cuánto ha crecido (o encogido) tu dinero de principio a fin del periodo.",
        "Positiva es ganancia; lo importante es si supera al benchmark en el mismo periodo.",
        "Depende mucho de las fechas elegidas: empezar justo antes de una caída la cambia por completo.",
    ),
    "cagr": Glossary(
        "La rentabilidad anual constante que, compuesta, daría el mismo resultado final (CAGR).",
        "Por encima del benchmark y de la tasa libre de riesgo es bueno; por debajo, no compensa el riesgo.",
        "Suaviza el camino: dos activos con el mismo CAGR pueden haber sufrido caídas muy distintas.",
    ),
    "max_drawdown": Glossary(
        "La mayor caída desde un máximo hasta el mínimo siguiente (Max Drawdown).",
        "Cuanto más cerca de 0 %, mejor. Caídas de -20 % o más son normales en acciones individuales.",
        "Es un único episodio del pasado: la próxima caída puede ser mayor.",
    ),
    "sharpe": Glossary(
        "Rentabilidad extra sobre la tasa libre de riesgo por cada unidad de volatilidad (ratio de Sharpe).",
        "Menos de 0,5 es flojo, de 0,5 a 1 aceptable, más de 1 bueno. Por encima de 3 suele ser un error o suerte.",
        "Trata igual las subidas y las bajadas bruscas y supone retornos normales; con poca historia es inestable.",
    ),
}


@dataclass(frozen=True, slots=True)
class Quality:
    """Semáforo de la calidad del rendimiento (Sharpe), con icono y texto
    para no depender solo del color."""

    level: Literal["good", "neutral", "weak", "alert", "none"]
    label: str
    icon: str  # carácter visible junto al color


def sharpe_quality(sharpe: float | None) -> Quality:
    if sharpe is None:
        return Quality("none", "Sin dato", "–")
    if sharpe > SUSPICIOUS_SHARPE:
        return Quality("alert", "Revisar: demasiado bueno", "!")
    if sharpe >= 1:
        return Quality("good", "Buena", "▲")
    if sharpe >= 0.5:
        return Quality("neutral", "Aceptable", "●")
    return Quality("weak", "Débil", "▼")


def headline_cards(insight: Insight) -> list[dict]:
    """Las 4 tarjetas de la capa 1, con su frase humana y su contexto."""
    s, b, bench = insight.strategy, insight.benchmark, insight.benchmark_label
    cards = []

    final = 100 * (1 + s.total_return) if s.total_return is not None else None
    bench_final = 100 * (1 + b.total_return) if b.total_return is not None else None
    cards.append({
        "key": "total",
        "title": "Rentabilidad total",
        "value": pct(s.total_return),
        "sign": _sign(s.total_return),
        "sentence": (
            f"Si hubieras invertido $100 al inicio, hoy tendrías {money(final)}."
            if final is not None else "No hay datos suficientes para calcularla."
        ),
        "context": f"{bench}: {pct(b.total_return)} ({money(bench_final)})" if bench_final is not None else "",
    })

    cards.append({
        "key": "cagr",
        "title": "Rentabilidad anual (CAGR)",
        "value": pct(s.cagr),
        "sign": _sign(s.cagr),
        "sentence": (
            f"Equivale a {'ganar' if (s.cagr or 0) >= 0 else 'perder'} un {abs(s.cagr) * 100:.1f}% cada año, de media."
            if s.cagr is not None else "No hay datos suficientes para calcularla."
        ),
        "context": f"{bench}: {pct(b.cagr)} al año · tasa libre de riesgo: {pct(insight.rf.annual, signed=False)}",
        "attenuated": insight.short_sample,
    })

    dd = insight.worst_drawdown
    remaining = 100 * (1 + s.max_drawdown) if s.max_drawdown is not None else None
    context = f"Peor caída de {bench}: {pct(b.max_drawdown)}"
    if dd is not None and dd.benchmark_change is not None:
        verb = "cayó" if dd.benchmark_change < 0 else "se movió"
        context = f"Entre {dd.start} y {dd.valley}, {bench} {verb} {pct(dd.benchmark_change)}. " + context
    cards.append({
        "key": "max_drawdown",
        "title": "Peor caída (Max Drawdown)",
        "value": pct(s.max_drawdown),
        "sign": "is-down" if (s.max_drawdown or 0) < 0 else "",
        "sentence": (
            f"En el peor momento, por cada $100 llegaste a tener {money(remaining)}."
            + (" Ya se recuperó." if dd is not None and dd.end else " Aún no se ha recuperado del todo." if dd else "")
            if remaining is not None else "No hubo caídas en el periodo."
        ),
        "context": context,
    })

    quality = sharpe_quality(s.sharpe)
    cards.append({
        "key": "sharpe",
        "title": "Calidad del rendimiento",
        "value": f"{s.sharpe:.2f}" if s.sharpe is not None else "—",
        "sign": "",
        "quality": quality,
        "sentence": (
            f"Por cada unidad de riesgo obtuviste {s.sharpe:.2f} unidades de rentabilidad extra sobre la tasa libre de riesgo."
            if s.sharpe is not None else "Sin variación suficiente para medir el riesgo."
        ),
        "context": f"Sharpe de {bench}: {b.sharpe:.2f}" if b.sharpe is not None else "",
        "attenuated": insight.short_sample,
    })
    for card in cards:
        card["glossary"] = GLOSSARY[card["key"]]
        card.setdefault("attenuated", False)
    return cards


def _sign(value: float | None) -> str:
    if value is None:
        return ""
    return "is-up" if value >= 0 else "is-down"
