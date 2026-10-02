"""Controlador de la app "QUANT STATS": análisis cuantitativo con quantstats de
cualquier activo de Yahoo Finance (``?ticker=``, UEC por defecto).

Sus dos subsecciones del sidebar no se solapan:

- ``fundamentales``: "Gráficas y fundamentales estadísticos". El activo por
  sí solo, en un período: los 3 módulos principales de quantstats (stats
  con su simulación Monte Carlo, plots y reports).
- ``revision``: "Revisión analítica". Todo lo comparativo: el activo frente a
  un benchmark (gráficas superpuestas y métricas lado a lado), un período
  frente a otro, y un reporte de resultados frente al anterior (earnings).

Las métricas se renderizan en el servidor; las gráficas son PNG que sirve la
API (``/api/quant/<ticker>/...``).
"""
from __future__ import annotations

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

from app.models import quant
from app.models.apps import get_app
from app.models.watchlists import WATCHLISTS

bp = Blueprint("quant_stats", __name__, url_prefix="/quant-stats")

DEFAULT_TICKER = "UEC"
PERIODS = {"1y": "1 año", "2y": "2 años", "5y": "5 años", "max": "Todo"}
DEFAULT_PERIOD = "2y"
EARNINGS_COUNT = 4

REVISION_MODES = {
    "benchmark": "Activo vs. benchmark",
    "periodos": "Período vs. período",
    "earnings": "Reporte vs. reporte (earnings)",
}
DEFAULT_BENCHMARK = "SPY"


@bp.get("/")
def index():
    return redirect(url_for("quant_stats.fundamentales", **request.args))


@bp.get("/fundamentales")
def fundamentales():
    ticker = _ticker_arg()
    period = _period_arg("period")
    returns = quant.daily_returns(ticker, period)

    sims = request.args.get("sims", quant.DEFAULT_MONTECARLO_SIMS, type=int)
    if sims not in quant.MONTECARLO_SIMS:
        sims = quant.DEFAULT_MONTECARLO_SIMS
    bust = _percent_arg("bust", quant.DEFAULT_BUST, low=-0.99, high=-0.01)
    goal = _percent_arg("goal", quant.DEFAULT_GOAL, low=0.01, high=20.0)

    return render_template(
        "quant_fundamentales.html",
        **_common(ticker),
        active_section="fundamentales",
        period=period,
        metrics=quant.performance_metrics(returns),
        stat_groups=quant.stats_groups(returns),
        montecarlo=quant.montecarlo_summary(returns, sims, bust, goal),
        montecarlo_sims=quant.MONTECARLO_SIMS,
        plots=quant.ABSOLUTE_PLOTS,
    )


@bp.get("/revision")
def revision():
    ticker = _ticker_arg()
    mode = request.args.get("mode", "benchmark")
    if mode not in REVISION_MODES:
        mode = "benchmark"
    period = _period_arg("period")
    window = request.args.get("window", quant.DEFAULT_ROLLING_WINDOW, type=int)
    if window not in quant.ROLLING_WINDOWS:
        window = quant.DEFAULT_ROLLING_WINDOW

    context = {
        **_common(ticker),
        "active_section": "revision",
        "mode": mode,
        "modes": REVISION_MODES,
        "period": period,
        "window": window,
        "windows": quant.ROLLING_WINDOWS,
        "plot": None,
        "benchmark": None,
        "compare": None,
    }

    if mode == "earnings":
        context["earnings"] = quant.last_earnings(ticker, EARNINGS_COUNT)
        context["earnings_count"] = EARNINGS_COUNT
        return render_template("quant_revision.html", **context)

    plots = quant.BENCHMARK_PLOTS if mode == "benchmark" else quant.ABSOLUTE_PLOTS
    plot = quant.get_plot(request.args.get("chart", ""))
    if plot not in plots:
        plot = plots[0]
    position = plots.index(plot)
    context.update(plots=plots, plot=plot, previous_plot=plots[position - 1], next_plot=plots[(position + 1) % len(plots)])

    if mode == "benchmark":
        benchmark = quant.normalize_ticker(request.args.get("benchmark")) or DEFAULT_BENCHMARK
        if benchmark == ticker:
            benchmark = DEFAULT_BENCHMARK if ticker != DEFAULT_BENCHMARK else "QQQ"
        returns = quant.daily_returns(ticker, period)
        bench = quant.benchmark_returns(benchmark, period, returns.index) if not returns.empty else returns
        context.update(
            benchmark=benchmark,
            benchmark_name=quant.asset_name(benchmark),
            comparison=quant.compare_stats(returns, bench),
        )
    else:
        compare = request.args.get("compare", "")
        if compare not in PERIODS or compare == period:
            compare = next(p for p in PERIODS if p != period)
        context["compare"] = compare

    return render_template("quant_revision.html", **context)


@bp.get("/tearsheet")
def tearsheet():
    """Tearsheet HTML de ``quantstats.reports``. ?ticker=UEC&period=2y&benchmark=SPY&download=1"""
    ticker = _ticker_arg()
    period = _period_arg("period")
    benchmark = request.args.get("benchmark") or None
    if benchmark is not None:
        benchmark = quant.normalize_ticker(benchmark)
        if benchmark is None:
            abort(400)
    html = quant.tearsheet_html(ticker, period, benchmark)
    if html is None:
        abort(404)
    response = Response(html, mimetype="text/html")
    if request.args.get("download"):
        filename = f"{ticker}-tearsheet-{period}.html"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _common(ticker: str) -> dict:
    return {
        "active_app": get_app("quant-stats"),
        # El sidebar conserva el activo al cambiar de subsección.
        "section_args": {"ticker": ticker},
        "ticker": ticker,
        "asset_name": quant.asset_name(ticker),
        "known_assets": _known_assets(),
        "periods": PERIODS,
        "benchmarks": quant.BENCHMARKS,
    }


def _known_assets() -> list[tuple[str, str]]:
    """Sugerencias para el selector de activo: los símbolos de las watchlists."""
    seen: dict[str, str] = {}
    for watchlist in WATCHLISTS:
        for symbol in watchlist.symbols:
            seen.setdefault(symbol.ticker, symbol.display_name)
    return sorted(seen.items())


def _ticker_arg() -> str:
    return quant.normalize_ticker(request.args.get("ticker")) or DEFAULT_TICKER


def _period_arg(name: str) -> str:
    period = request.args.get(name, DEFAULT_PERIOD)
    return period if period in PERIODS else DEFAULT_PERIOD


def _percent_arg(name: str, default: float, *, low: float, high: float) -> float:
    """Lee un porcentaje entero de la URL (``bust=-20``) y lo devuelve en fracción."""
    value = request.args.get(name, type=float)
    if value is None:
        return default
    return min(max(value / 100, low), high)
