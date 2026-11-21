"""Controlador de INSIGHTS (``/app/insights/``): rendimiento de un activo o
portafolio frente a un benchmark, en 3 capas de divulgación progresiva.

El blueprint vive en ``api.py`` (no en ``views.py``) a propósito: así se
registra con la única línea añadida a ``INSTALLED_APPS`` sin tener que dar de
alta la app en el sidebar (``app/core/navigation.py``), que es un archivo
existente que esta feature no puede modificar. Ver ``PR_BODY.md``.

``?ticker=AAPL`` o ``?ticker=SPY:60,TLT:40`` · ``range`` (1y por defecto) ·
``benchmark`` (SPY) · ``rf`` (tasa anual en %, por defecto la actual de ^IRX).
"""
from __future__ import annotations

import logging

from flask import Blueprint, render_template, request

from app.core.api import ALLOWED_RANGES
from app.insights import data, engine, narrative

log = logging.getLogger(__name__)

bp = Blueprint(
    "insights",
    __name__,
    url_prefix="/app/insights",
    template_folder="templates",
    static_folder="static",
)

SUGGESTIONS = (
    ("AAPL", "Apple"),
    ("QQQ", "Nasdaq 100"),
    ("SPY:60, TLT:40", "Cartera 60/40"),
    ("BTC-USD", "Bitcoin"),
)
BENCHMARKS = (("SPY", "S&P 500 (SPY)"), ("QQQ", "Nasdaq 100 (QQQ)"), ("ACWI", "Mundo (ACWI)"), ("BTC-USD", "Bitcoin"))


@bp.get("/")
def index():
    text = (request.args.get("ticker") or "").strip()
    range_ = request.args.get("range", data.DEFAULT_RANGE)
    if range_ not in data.RANGES or range_ not in ALLOWED_RANGES:
        range_ = data.DEFAULT_RANGE
    benchmark = data.normalize_ticker(request.args.get("benchmark")) or data.DEFAULT_BENCHMARK
    rf_text = (request.args.get("rf") or "").strip().replace(",", ".")

    context = {
        "ticker_text": text,
        "range": range_,
        "ranges": data.RANGES,
        "benchmark": benchmark,
        "benchmarks": BENCHMARKS,
        "rf_text": rf_text,
        "suggestions": SUGGESTIONS,
        "insight": None,
        "error": None,
    }
    if not text:
        return render_template("insights/index.html", **context)

    try:
        rf_override = _rf_arg(rf_text)
        weights = data.parse_portfolio(text)
        if list(weights) == [benchmark]:
            benchmark = "QQQ" if benchmark != "QQQ" else data.DEFAULT_BENCHMARK
            context["benchmark"] = benchmark
        key = (tuple(sorted(weights.items())), range_, benchmark, rf_override)
        result = engine.cached(key, lambda: _analyse(weights, benchmark, range_, rf_override))
    except data.InputError as exc:
        context["error"] = str(exc)
        return render_template("insights/index.html", **context), 400
    except engine.InsightError as exc:
        context["error"] = str(exc)
        return render_template("insights/index.html", **context)
    except Exception:  # noqa: BLE001 - nunca un traceback al usuario
        log.exception("Insights falló para %r", text)
        context["error"] = "Algo salió mal al calcular el análisis. Prueba de nuevo en unos minutos o con otro activo."
        return render_template("insights/index.html", **context), 500

    context.update(result)
    return render_template("insights/index.html", **context)


def _rf_arg(text: str) -> float | None:
    if not text:
        return None
    try:
        value = float(text.rstrip("%"))
    except ValueError:
        raise data.InputError("La tasa libre de riesgo debe ser un número en % anual, por ejemplo 4.5.") from None
    if not 0 <= value <= 20:
        raise data.InputError("La tasa libre de riesgo debe estar entre 0 % y 20 % anual.")
    return value


def _analyse(weights: dict[str, float], benchmark: str, range_: str, rf_override: float | None) -> dict:
    prepared = data.prepare(weights, benchmark, range_)
    rf = data.risk_free_rate(prepared.periods, rf_override)
    insight = engine.compute_insight(
        prepared.strategy,
        prepared.benchmark,
        rf,
        label=data.portfolio_label(weights),
        benchmark_label=benchmark,
        data_notes=prepared.notes,
    )
    return {
        "insight": insight,
        "weights": weights,
        "cards": narrative.headline_cards(insight),
        "charts": engine.chart_series(insight),
        "heatmap": engine.monthly_heatmap(insight.returns),
        "months": engine.MONTHS,
        "pct": narrative.pct,
    }
