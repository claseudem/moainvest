"""Resúmenes en lenguaje llano de Quant stats (``app.quant_stats.explain``).

Funciones puras: se prueban con ``AssetFacts`` construidos a mano, tramo a
tramo (bueno/regular/malo, positivo/negativo y datos insuficientes).
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.quant_stats import explain
from app.quant_stats.explain import AssetFacts, BenchmarkFacts, DrawdownPeriod, Rolling

NB = " "


def _facts(**overrides) -> AssetFacts:
    """Un activo "normal": 2 años, +30 %, volatilidad moderada y Sharpe 1,1."""
    base = AssetFacts(
        ticker="ACME",
        trading_days=500,
        start="enero de 2024",
        end="diciembre de 2025",
        cumulative_return=0.30,
        cagr=0.14,
        volatility=0.22,
        sharpe=1.1,
        sortino=1.6,
        max_drawdown=-0.35,
        current_drawdown=-0.05,
        drawdowns=(
            DrawdownPeriod(depth=-0.35, days=240, recovered=True),
            DrawdownPeriod(depth=-0.12, days=400, recovered=False),
            DrawdownPeriod(depth=-0.08, days=20, recovered=True),
        ),
        best_day=0.06,
        worst_day=-0.07,
        typical_day=0.014,
        typical_month=0.06,
        win_rate_days=0.53,
        win_rate_months=0.58,
        months_total=24,
        months_positive=14,
        average_month=0.012,
        best_month=("marzo de 2024", 0.15),
        worst_month=("agosto de 2025", -0.11),
        yearly=((2024, 0.21), (2025, 0.07)),
        value_at_risk=-0.022,
        expected_shortfall=-0.031,
        skew=-0.2,
        kurtosis=1.5,
        calmar=0.4,
        omega=1.2,
        probabilistic_sharpe=0.93,
        avg_win=0.011,
        avg_loss=-0.010,
        payoff_ratio=1.1,
        profit_factor=1.2,
        max_loss_streak=6,
        max_win_streak=7,
        rolling_window_label="6 meses",
        rolling_volatility=Rolling(current=0.20, average=0.21),
        rolling_sharpe=Rolling(current=1.4, average=1.0),
        rolling_sortino=Rolling(current=-0.3, average=0.9),
    )
    return replace(base, **overrides)


# --------------------------------------------------------------------------
# Formato y tramos
# --------------------------------------------------------------------------


def test_numbers_use_spanish_format():
    assert explain.pct(0.352) == f"35{NB}%"
    assert explain.pct(0.0123) == f"1,2{NB}%"
    assert explain.pct(-0.35) == f"35{NB}%"  # sin signo: la frase ya dice "caída"
    assert explain.pct(-0.35, signed=True) == f"-35{NB}%"
    assert explain.pct(0.07, signed=True) == f"+7,0{NB}%"
    assert explain.pct(0.0, signed=True) == f"0,0{NB}%"
    assert explain.num(1.1) == "1,1"
    assert explain.money(257_298.4) == f"257.298{NB}USD"


@pytest.mark.parametrize(
    ("days", "text"),
    [(1, "1 día"), (12, "12 días"), (61, "2 meses"), (240, "8 meses"), (365, "1 año"), (460, "1 año y 3 meses"), (800, "2 años y 2 meses")],
)
def test_duration_reads_naturally(days, text):
    assert explain.duration(days) == text


@pytest.mark.parametrize(
    ("sharpe", "label"),
    [(-0.4, "negativo"), (0.2, "pobre"), (0.7, "razonable"), (1.1, "bueno"), (2.5, "excelente")],
)
def test_sharpe_tiers(sharpe, label):
    assert explain.sharpe_label(sharpe) == label


@pytest.mark.parametrize(
    ("volatility", "label"), [(0.10, "baja"), (0.22, "moderada"), (0.40, "alta"), (0.80, "muy alta")]
)
def test_volatility_tiers(volatility, label):
    assert explain.volatility_label(volatility) == label


@pytest.mark.parametrize(
    ("drawdown", "label"), [(-0.05, "leve"), (-0.18, "moderada"), (-0.35, "fuerte"), (-0.7, "muy fuerte")]
)
def test_drawdown_tiers(drawdown, label):
    assert explain.drawdown_label(drawdown) == label


@pytest.mark.parametrize(("calmar", "label"), [(-1, "negativo"), (0.3, "bajo"), (0.7, "aceptable"), (1.5, "bueno"), (4, "muy bueno")])
def test_calmar_tiers(calmar, label):
    assert explain.calmar_label(calmar) == label


@pytest.mark.parametrize(
    ("beta", "fragment"),
    [(-0.3, "sentido contrario"), (0.3, "apenas sigue"), (0.6, "menos sensible"), (1.0, "más o menos como"), (1.6, "amplifica")],
)
def test_beta_tiers(beta, fragment):
    assert fragment in explain.beta_label(beta)


# --------------------------------------------------------------------------
# Resumen general
# --------------------------------------------------------------------------


def test_overview_uses_the_asset_numbers():
    text = explain.overview(_facts())
    assert "Entre enero de 2024 y diciembre de 2025, ACME ganó un 30" in text
    assert f"+14{NB}% al año" in text
    assert "volatilidad" in text and "moderada" in text and "S&P 500" in text
    assert f"llegó a perder un 35{NB}% desde su máximo (una caída fuerte) y tardó 8 meses en recuperarse" in text
    assert "rendimiento bueno (Sharpe 1,1; por encima de 1 se considera bueno)" in text


def test_overview_negative_asset_without_recovery():
    facts = _facts(
        cumulative_return=-0.42,
        cagr=-0.24,
        volatility=0.65,
        sharpe=-0.6,
        max_drawdown=-0.58,
        drawdowns=(DrawdownPeriod(depth=-0.58, days=500, recovered=False),),
    )
    text = explain.overview(facts)
    assert "ACME perdió un 42" in text
    assert "muy alta" in text
    assert "caída muy fuerte" in text and "todavía no lo ha recuperado" in text
    assert "negativo" in text and "no se vio recompensado" in text


def test_overview_without_any_drawdown():
    text = explain.overview(_facts(max_drawdown=0.0, drawdowns=()))
    assert "No llegó a caer por debajo de su máximo" in text


def test_short_history_skips_the_annualised_return():
    text = explain.overview(_facts(trading_days=100))
    assert "al año" not in text.split(".")[0]


@pytest.mark.parametrize(
    "facts",
    [None, AssetFacts(ticker="ACME"), AssetFacts(ticker="ACME", trading_days=5, cumulative_return=0.1)],
)
def test_insufficient_data_everywhere(facts):
    assert explain.overview(facts) == explain.INSUFFICIENT
    assert explain.stat_group("Riesgo", facts) == explain.INSUFFICIENT
    assert explain.plot("drawdown", facts) == explain.INSUFFICIENT
    assert explain.compare_periods(facts, "1 año", _facts(), "2 años") == explain.INSUFFICIENT
    assert explain.comparison_group("Resumen", _facts(), facts) == explain.INSUFFICIENT
    assert explain.tearsheet(facts) == explain.INSUFFICIENT


def test_summaries_are_short():
    """2-4 frases: ningún resumen se convierte en un párrafo interminable."""
    facts = _facts()
    texts = [explain.overview(facts)]
    texts += [explain.stat_group(t, facts) for t in ("Rendimiento", "Riesgo", "Rendimiento ajustado por riesgo", "Operativa diaria")]
    texts += [explain.plot(slug, facts) for slug in explain._PLOT_WRITERS]
    for text in texts:
        sentences = [s for s in text.replace("...", "").split(". ") if s.strip()]
        assert 1 <= len(sentences) <= 5, text


# --------------------------------------------------------------------------
# Tablas de métricas
# --------------------------------------------------------------------------


def test_performance_group():
    text = explain.stat_group("Rendimiento", _facts())
    assert f"habría visto crecer su inversión a un ritmo de +14{NB}% al año" in text
    assert "CAGR" in text
    assert "El mejor mes fue marzo de 2024" in text and "agosto de 2025" in text
    assert "muy nervioso" not in text


def test_performance_group_flags_big_days_and_shrinking():
    text = explain.stat_group("Rendimiento", _facts(cagr=-0.1, worst_day=-0.18))
    assert "encoger su inversión" in text
    assert "muy nervioso" in text


@pytest.mark.parametrize(
    ("skew", "kurtosis", "fragments"),
    [
        (-1.2, 6.0, ("asimetría negativa", "colas gordas")),
        (0.9, 0.5, ("asimetría positiva", "no son especialmente frecuentes")),
        (0.1, 1.0, ("equilibradas",)),
    ],
)
def test_risk_group(skew, kurtosis, fragments):
    text = explain.stat_group("Riesgo", _facts(skew=skew, kurtosis=kurtosis))
    assert f"1 de cada 20 sesiones, las peores, cabe esperar perder un 2,2{NB}% o más" in text
    assert "Expected Shortfall" in text
    for fragment in fragments:
        assert fragment in text


@pytest.mark.parametrize(
    ("calmar", "omega", "fragments"),
    [
        (1.8, 1.4, ("resultado bueno", "Las ganancias pesan más")),
        (0.3, 0.8, ("resultado bajo", "Las pérdidas pesan más")),
    ],
)
def test_risk_adjusted_group(calmar, omega, fragments):
    text = explain.stat_group("Rendimiento ajustado por riesgo", _facts(calmar=calmar, omega=omega))
    for fragment in fragments:
        assert fragment in text
    assert f"93{NB}% de probabilidad" in text


@pytest.mark.parametrize(("profit_factor", "verdict"), [(1.3, ": compensa."), (0.8, ": no compensa.")])
def test_daily_group(profit_factor, verdict):
    text = explain.stat_group("Operativa diaria", _facts(profit_factor=profit_factor))
    assert f"Subió en el 53{NB}% de las sesiones y en el 58{NB}% de los meses" in text
    assert verdict in text
    assert "6 sesiones seguidas en negativo" in text


def test_unknown_group_has_no_summary():
    assert explain.stat_group("Otra cosa", _facts()) == ""


# --------------------------------------------------------------------------
# Monte Carlo
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("probability", "fragment"), [(0.04, ": baja."), (0.25, ": moderada."), (0.7, ": alta."), (1.0, "prácticamente seguro")])
def test_montecarlo_tiers(probability, fragment):
    text = explain.montecarlo(
        "ACME", sims=1000, bust=-0.2, bust_probability=probability, median_drawdown=-0.28, worst_drawdown=-0.45
    )
    assert "baraja 1000 veces" in text
    assert f"la peor caída superó el 28{NB}%" in text and f"llegó al 45{NB}%" in text
    assert fragment in text


def test_montecarlo_without_data():
    text = explain.montecarlo("ACME", sims=1000, bust=-0.2, bust_probability=None, median_drawdown=None, worst_drawdown=None)
    assert text == explain.INSUFFICIENT


# --------------------------------------------------------------------------
# Gráficas
# --------------------------------------------------------------------------


def test_every_plot_has_its_own_summary():
    from app.quant_stats.quant import PLOTS

    facts = _facts()
    texts = {p.slug: explain.plot(p.slug, facts) for p in PLOTS}
    assert all(texts.values())
    assert len(set(texts.values())) == len(texts)  # ninguno repite el de otra gráfica


def test_drawdown_plot_mentions_current_situation():
    assert f"Ahora mismo está un 5,0{NB}% por debajo" in explain.plot("drawdown", _facts())
    assert "en máximos" in explain.plot("drawdown", _facts(current_drawdown=0.0))


def test_drawdown_periods_plot():
    text = explain.plot("drawdowns-periods", _facts())
    assert f"El peor restó un 35{NB}% y duró 8 meses" in text
    assert "el más largo se alargó 1 año y 1 mes" in text
    assert "2 de 3 ya se recuperaron" in text
    assert "No hubo caídas" in explain.plot("drawdowns-periods", _facts(drawdowns=()))


@pytest.mark.parametrize(
    ("current", "verdict"), [(0.35, "más agitado"), (0.12, "más tranquilo"), (0.21, "en línea con lo habitual")]
)
def test_rolling_volatility_plot(current, verdict):
    text = explain.plot("rolling-volatility", _facts(rolling_volatility=Rolling(current=current, average=0.21)))
    assert verdict in text and "6 meses" in text


def test_rolling_ratios_plot():
    sharpe = explain.plot("rolling-sharpe", _facts())
    assert "1,40" in sharpe and "bueno" in sharpe and "mejor que su media" in sharpe
    sortino = explain.plot("rolling-sortino", _facts())
    assert "se está perdiendo dinero" in sortino and "peor que su media" in sortino
    short = explain.plot("rolling-sharpe", _facts(rolling_sharpe=None))
    assert short == explain.INSUFFICIENT


def test_yearly_plot():
    text = explain.plot("yearly-returns", _facts())
    assert "El mejor fue 2024" in text and "el peor 2025" in text and "2 de 2 años" in text
    single = explain.plot("yearly-returns", _facts(yearly=((2025, -0.1),)))
    assert "solo entra 2025" in single


@pytest.mark.parametrize(("positive", "verdict"), [(24, "todos"), (17, "la mayoría"), (12, "la mitad"), (5, "una minoría"), (0, "ninguno")])
def test_monthly_heatmap_counts_positive_months(positive, verdict):
    text = explain.plot("monthly-heatmap", _facts(months_positive=positive))
    assert f"{positive} de 24 meses fueron positivos: " in text and verdict in text


def test_growth_plot_in_money():
    text = explain.plot("earnings", _facts())
    assert f"130.000{NB}USD" in text and "una ganancia" in text
    loss = explain.plot("earnings", _facts(cumulative_return=-0.25))
    assert f"75.000{NB}USD" in loss and "una pérdida" in loss


def test_plot_against_a_benchmark():
    spy = BenchmarkFacts(facts=_facts(ticker="SPY", cumulative_return=0.10, volatility=0.15, sharpe=0.8), beta=1.4, correlation=0.75)
    text = explain.plot("returns", _facts(), spy)
    assert "ACME superó SPY por 20 puntos porcentuales" in text
    behind = explain.plot("returns", _facts(cumulative_return=0.05), spy)
    assert "quedó por detrás de SPY" in behind
    tie = explain.plot("returns", _facts(cumulative_return=0.11), spy)
    assert "prácticamente lo mismo" in tie
    vol = explain.plot("rolling-volatility", _facts(), spy)
    assert "más volátil que SPY" in vol


def test_beta_plot():
    spy = BenchmarkFacts(facts=_facts(ticker="SPY"), beta=1.4, correlation=0.75)
    text = explain.plot("rolling-beta", _facts(), spy)
    assert "beta de 1,40" in text and "amplifica" in text and "fuerte" in text
    missing = explain.plot("rolling-beta", _facts(), None)
    assert "No se pudo calcular" in missing


def test_unknown_plot_has_no_summary():
    assert explain.plot("bogus", _facts()) == ""


# --------------------------------------------------------------------------
# Comparativas
# --------------------------------------------------------------------------


def test_compare_periods_picks_the_better_one():
    one_year = _facts(cumulative_return=-0.1, max_drawdown=-0.2, sharpe=-0.3)
    text = explain.compare_periods(one_year, "1 año", _facts(), "2 años")
    assert "en 1 año perdió un 10" in text and "en 2 años ganó un 30" in text
    assert "el mejor tramo fue 2 años" in text


@pytest.mark.parametrize(
    "title", ["Resumen", "Rendimiento", "Riesgo", "Rendimiento ajustado por riesgo", "Operativa diaria"]
)
def test_comparison_groups_name_both_assets(title):
    text = explain.comparison_group(title, _facts(), _facts(ticker="SPY", cumulative_return=0.1, volatility=0.15))
    assert "ACME" in text and "SPY" in text


def test_comparison_summary_tiers():
    spy = _facts(ticker="SPY", cumulative_return=0.10, volatility=0.15, sharpe=0.8, max_drawdown=-0.2)
    text = explain.comparison_group("Resumen", _facts(), spy)
    assert "ACME rindió más que SPY" in text
    assert "bastante más brusquedad" in text
    assert "fue mejor (1,10 frente a 0,80)" in text
    calm = explain.comparison_group("Resumen", _facts(volatility=0.10, cumulative_return=0.0), spy)
    assert "rindió menos" in calm and "menos sobresaltos" in calm


# --------------------------------------------------------------------------
# Earnings
# --------------------------------------------------------------------------


def _report(label, estimate, reported, change=None):
    return SimpleNamespace(
        label=label, eps_estimate=estimate, eps_reported=reported, surprise_percent=None, price_change_percent=change
    )


def test_earnings_summary():
    reports = [
        _report("21 Abr 2025", 0.10, 0.12),
        _report("21 Jul 2025", 0.12, 0.10, change=-5.0),
        _report("20 Oct 2025", 0.12, 0.15, change=12.0),
        _report("20 Ene 2026", None, 0.18, change=4.0),
    ]
    text = explain.earnings("ACME", reports)
    assert "beneficio por acción (EPS)" in text
    assert "en 2 de 3" in text
    assert "El EPS ha mejorado del primer reporte (0,12) al último (0,18)" in text
    assert f"la acción subió de media un 3,7{NB}%" in text


def test_earnings_all_or_none_beats():
    beats = [_report("a", 0.1, 0.2), _report("b", 0.1, 0.3)]
    misses = [_report("a", 0.3, 0.2), _report("b", 0.4, 0.1, change=-8.0)]
    assert "en todos ellos" in explain.earnings("ACME", beats)
    worse = explain.earnings("ACME", misses)
    assert "en ninguno" in worse and "ha empeorado" in worse and "bajó de media" in worse


def test_earnings_without_reports():
    assert "No hay reportes de resultados de SPY" in explain.earnings("SPY", [])
