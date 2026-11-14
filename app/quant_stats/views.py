"""Controlador de "QUANT STATS": análisis cuantitativo con quantstats de
cualquier activo de Yahoo Finance (``?ticker=``, UEC por defecto).

No es una app propia del sidebar: vive dentro del Graficador
(``/app/graficador/quant-stats/``) como dos de sus subsecciones, y comparte
con él el activo elegido por la query string (``?ticker=``):

- ``fundamentales`` ("Quant stats"): el activo por sí solo, en un período:
  métricas clave, gráficas, simulación Monte Carlo, métricas detalladas y
  tearsheet.
- ``revision`` ("Comparar"): todo lo comparativo: el activo frente a un
  benchmark, un período frente a otro y sus reportes de resultados.

Cada gráfica y tabla lleva un resumen en lenguaje llano generado a partir de
sus métricas (``app.quant_stats.explain``). Las métricas se renderizan en el
servidor; las gráficas son PNG que sirve la API (``/api/quant/<ticker>/...``).
"""
from __future__ import annotations

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

from app.quant_stats import explain, quant
from app.core.navigation import get_app
from app.core.watchlists import WATCHLISTS

bp = Blueprint(
    "quant_stats",
    __name__,
    url_prefix="/app/graficador/quant-stats",
    template_folder="templates",
    static_folder="static",
)

DEFAULT_TICKER = "UEC"
PERIODS = {"1y": "1 año", "2y": "2 años", "5y": "5 años", "max": "Todo"}
DEFAULT_PERIOD = "2y"
EARNINGS_COUNT = 4

REVISION_MODES = {
    "benchmark": "Contra un índice",
    "periodos": "Entre períodos",
    "earnings": "Resultados trimestrales",
}
# Gráficas que se ven sin desplegar "Más gráficas" en Quant stats: las más
# fáciles de leer para alguien que empieza. El resto, plegadas.
FEATURED_PLOTS = ("snapshot", "returns", "drawdown", "monthly-heatmap", "yearly-returns", "rolling-volatility")
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

    facts = quant.asset_facts(ticker, returns)
    stat_groups = quant.stats_groups(returns)
    montecarlo = quant.montecarlo_summary(returns, sims, bust, goal)
    plots = quant.ABSOLUTE_PLOTS
    return render_template(
        "quant_stats/fundamentales.html",
        **_common(ticker),
        active_section="quant-stats",
        period=period,
        metrics=quant.performance_metrics(returns),
        stat_groups=stat_groups,
        montecarlo=montecarlo,
        montecarlo_sims=quant.MONTECARLO_SIMS,
        featured_plots=[p for p in plots if p.slug in FEATURED_PLOTS],
        more_plots=[p for p in plots if p.slug not in FEATURED_PLOTS],
        summaries={
            "overview": explain.overview(facts),
            "groups": {title: explain.stat_group(title, facts) for title, _ in stat_groups},
            "plots": {p.slug: explain.plot(p.slug, facts) for p in plots},
            "montecarlo": _montecarlo_summary(ticker, montecarlo),
            "tearsheet": explain.tearsheet(facts),
        },
    )


def _montecarlo_summary(ticker: str, montecarlo: quant.MonteCarloSummary | None) -> str:
    if montecarlo is None:
        return explain.INSUFFICIENT
    return explain.montecarlo(
        ticker,
        sims=montecarlo.sims,
        bust=montecarlo.bust,
        bust_probability=montecarlo.bust_probability,
        median_drawdown=montecarlo.max_drawdown.get("median"),
        worst_drawdown=montecarlo.max_drawdown.get("percentile_5"),
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
        "active_section": "comparar",
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
        context["summary"] = explain.earnings(ticker, context["earnings"])
        return render_template("quant_stats/revision.html", **context)

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
        facts = quant.asset_facts(ticker, returns, window)
        bench_facts = quant.benchmark_facts(benchmark, returns, bench, window)
        comparison = quant.compare_stats(returns, bench)
        bench_asset = bench_facts.facts if bench_facts else None
        context.update(
            benchmark=benchmark,
            benchmark_name=quant.asset_name(benchmark),
            comparison=comparison,
            summary=explain.plot(plot.slug, facts, bench_facts),
            comparison_summaries={title: explain.comparison_group(title, facts, bench_asset) for title, _ in comparison},
        )
    else:
        compare = request.args.get("compare", "")
        if compare not in PERIODS or compare == period:
            compare = next(p for p in PERIODS if p != period)
        facts = quant.asset_facts(ticker, quant.daily_returns(ticker, period), window)
        other = quant.asset_facts(ticker, quant.daily_returns(ticker, compare), window)
        context.update(
            compare=compare,
            summary=explain.plot(plot.slug, facts),
            compare_summary=explain.plot(plot.slug, other),
            periods_summary=explain.compare_periods(facts, PERIODS[period], other, PERIODS[compare]),
        )

    return render_template("quant_stats/revision.html", **context)


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
        "active_app": get_app("graficador"),
        # El sidebar y las pestañas conservan el activo al cambiar de subsección
        # (también al volver al gráfico del Graficador).
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
