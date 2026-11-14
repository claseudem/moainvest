"""Rutas de "QUANT STATS" dentro del Graficador (páginas y API de gráficas)."""
import re

import pytest


def test_quant_stats_index_redirects_to_fundamentales(client):
    response = client.get("/app/graficador/quant-stats/?ticker=AAPL&period=1y")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/app/graficador/quant-stats/fundamentales?ticker=AAPL&period=1y")


def test_quant_stats_sidebar_sections_keep_the_asset(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/fundamentales?ticker=aapl").data.decode()
    # Quant stats es una subsección del Graficador (marcado como app activa).
    assert re.search(r'sidebar__app is-active">\s*<a class="sidebar__app-header" href="/app/graficador/"', html)
    for href in (
        "/app/graficador/?ticker=AAPL",
        "/app/graficador/quant-stats/fundamentales?ticker=AAPL",
        "/app/graficador/quant-stats/revision?ticker=AAPL",
    ):
        assert f'href="{href}"' in html
    tabs = html.split('<nav class="app-tabs"', 1)[1].split("</nav>", 1)[0]
    assert 'aria-current="page">Quant stats</a>' in tabs
    assert "/app/graficador/quant-stats/tearsheet?ticker=AAPL&amp;period=2y" in tabs


def test_fundamentales_shows_metrics_charts_montecarlo_and_tearsheet(client, fake_uec):
    from app.quant_stats.quant import ABSOLUTE_PLOTS

    response = client.get("/app/graficador/quant-stats/fundamentales?period=1y")
    assert response.status_code == 200
    html = response.data.decode()
    for label in ("Retorno acumulado", "Volatilidad anualizada", "Sharpe", "Sortino", "Máximo drawdown", "Calmar"):
        assert label in html
    for plot in ABSOLUTE_PLOTS:
        assert f"/api/quant/UEC/plot/{plot.slug}.png?period=1y" in html
    assert "/api/quant/UEC/montecarlo.png" in html
    assert "/app/graficador/quant-stats/tearsheet" in html
    assert "Uranium Energy Corp" in html  # nombre de la watchlist
    # Las gráficas secundarias van plegadas en "Más gráficas".
    assert '<details class="qs-more">' in html and "Más gráficas" in html


def test_fundamentales_has_a_plain_language_summary_for_every_chart_and_table(client, fake_uec):
    from app.quant_stats.quant import ABSOLUTE_PLOTS, STAT_GROUPS

    html = client.get("/app/graficador/quant-stats/fundamentales").data.decode()
    keys = re.findall(r'data-summary="([^"]+)"', html)
    expected = {"overview", "montecarlo", *(p.slug for p in ABSOLUTE_PLOTS)}
    expected |= {f"group-{i}" for i in range(1, len(STAT_GROUPS) + 1)}
    assert set(keys) == expected
    assert len(keys) == len(expected)  # uno por gráfica o tabla, sin repetir
    # Dinámicos: hablan de este activo con sus cifras.
    overview = html.split('data-summary="overview"', 1)[1].split("</div>", 1)[0]
    assert "UEC" in overview and "%" in overview
    assert "Sharpe" in overview


def test_fundamentales_has_nothing_comparative(client, fake_uec):
    """MECE: benchmark, períodos y earnings viven solo en Revisión analítica."""
    html = client.get("/app/graficador/quant-stats/fundamentales").data.decode()
    assert "rolling-beta" not in html
    assert "benchmark=" not in html
    assert 'name="benchmark"' not in html
    assert "/api/quant/UEC/earnings.png" not in html  # reportes de resultados


def test_summary_metrics_are_not_repeated_in_the_stat_tables(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/fundamentales").data.decode()
    for label in ("Retorno acumulado", "Volatilidad anualizada", "Máximo drawdown"):
        assert html.count(f">{label}<") == 1


def test_fundamentales_runs_montecarlo_with_custom_thresholds(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/fundamentales?sims=500&bust=-30&goal=100").data.decode()
    assert "DD ≤ -30%" in html
    assert "retorno ≥ +100%" in html
    assert "/api/quant/UEC/montecarlo.png?period=2y&amp;sims=500&amp;bust=-30&amp;goal=100" in html


def test_fundamentales_works_for_any_asset(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/fundamentales?ticker=ccj").data.decode()
    assert '<span class="qs-hero__ticker">CCJ</span>' in html
    assert "Nombre CCJ" in html  # no está en las watchlists: nombre de Yahoo Finance
    assert "/api/quant/CCJ/plot/snapshot.png" in html


def test_invalid_ticker_falls_back_to_default(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/fundamentales?ticker=<script>").data.decode()
    assert '<span class="qs-hero__ticker">UEC</span>' in html


def test_fundamentales_without_data(client, monkeypatch):
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_candles", lambda *a, **k: [])
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_display_name", lambda ticker: ticker)
    response = client.get("/app/graficador/quant-stats/fundamentales?ticker=NOEXISTE")
    assert response.status_code == 200
    assert "No se pudieron descargar precios de NOEXISTE".encode() in response.data


def test_revision_defaults_to_benchmark_mode(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/revision?chart=bogus&period=bogus&mode=bogus").data.decode()
    assert "/api/quant/UEC/plot/returns.png?period=2y&amp;benchmark=SPY" in html
    assert "Métricas: UEC vs. SPY" in html
    assert "/app/graficador/quant-stats/tearsheet" in html
    assert 'data-summary="chart"' in html
    for i in range(1, 6):  # una explicación por tabla de métricas (resumen + 4 grupos)
        assert f'data-summary="compare-{i}"' in html
    chart = html.split('data-summary="chart"', 1)[1].split("</div>", 1)[0]
    assert "SPY" in chart  # compara con el benchmark


def test_revision_benchmark_mode_accepts_any_benchmark(client, fake_uec):
    html = client.get(
        "/app/graficador/quant-stats/revision?ticker=UEC&mode=benchmark&benchmark=ccj&chart=rolling-sharpe&window=63"
    ).data.decode()
    assert "/api/quant/UEC/plot/rolling-sharpe.png?period=2y&amp;benchmark=CCJ&amp;window=63" in html
    assert "Nombre CCJ" in html


def test_revision_benchmark_cannot_be_the_asset_itself(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/revision?ticker=UEC&benchmark=UEC").data.decode()
    assert "Métricas: UEC vs. SPY" in html


def test_revision_periods_mode_compares_two_periods(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/revision?mode=periodos&chart=drawdown&period=1y&compare=5y").data.decode()
    assert "/api/quant/UEC/plot/drawdown.png?period=1y\"" in html
    assert "/api/quant/UEC/plot/drawdown.png?period=5y\"" in html
    assert "rolling-beta" not in html  # sin benchmark no hay beta
    for key in ("chart", "chart-compare", "periods"):
        assert f'data-summary="{key}"' in html


def test_revision_periods_mode_never_compares_a_period_with_itself(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/revision?mode=periodos&chart=drawdown&period=2y&compare=2y").data.decode()
    assert "/api/quant/UEC/plot/drawdown.png?period=1y\"" in html


def test_revision_earnings_mode(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/revision?mode=earnings").data.decode()
    assert "/api/quant/UEC/earnings.png" in html
    earnings_section = html.split("Últimos 4 resultados trimestrales", 1)[1]
    assert earnings_section.count("<tr>") == 1 + 4  # cabecera + 4 earnings
    summary = html.split('data-summary="earnings"', 1)[1].split("</div>", 1)[0]
    assert "UEC" in summary and "EPS" in summary


def test_revision_earnings_mode_without_reports(client, fake_uec, monkeypatch):
    monkeypatch.setattr("app.quant_stats.quant.market_data.get_earnings", lambda *a, **k: [])
    html = client.get("/app/graficador/quant-stats/revision?mode=earnings&ticker=SPY").data.decode()
    assert "/api/quant/SPY/earnings.png" not in html
    assert "No hay reportes de resultados de SPY" in html


def test_revision_rolling_beta_explains_the_beta(client, fake_uec):
    html = client.get("/app/graficador/quant-stats/revision?chart=rolling-beta&benchmark=SPY").data.decode()
    chart = html.split('data-summary="chart"', 1)[1].split("</div>", 1)[0]
    assert "beta" in chart and "SPY" in chart


def test_tearsheet_is_served_and_downloadable(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.quant_stats.views.quant.tearsheet_html",
        lambda *a: calls.append(a) or "<html>tearsheet</html>",
    )
    response = client.get("/app/graficador/quant-stats/tearsheet?ticker=aapl&period=1y&benchmark=spy")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Content-Disposition" not in response.headers
    assert calls == [("AAPL", "1y", "SPY")]
    download = client.get("/app/graficador/quant-stats/tearsheet?period=1y&download=1")
    assert download.headers["Content-Disposition"] == 'attachment; filename="UEC-tearsheet-1y.html"'


def test_tearsheet_rejects_invalid_benchmark(client):
    assert client.get("/app/graficador/quant-stats/tearsheet?benchmark=%3Cx%3E").status_code == 400


@pytest.mark.parametrize("chart", ["drawdown", "monthly-heatmap"])
def test_api_quant_charts_reject_bad_period(client, chart):
    assert client.get(f"/api/quant/UEC/{chart}.png?period=bogus").status_code == 400


def test_api_quant_earnings_rejects_bad_count(client):
    assert client.get("/api/quant/UEC/earnings.png?count=50").status_code == 400


def test_api_quant_drawdown_returns_png(client, monkeypatch):
    monkeypatch.setattr(
        "app.quant_stats.api.quant.render_drawdown_chart", lambda ticker, period: b"fake-png-bytes"
    )
    response = client.get("/api/quant/uec/drawdown.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_api_quant_plot_validates_params(client):
    assert client.get("/api/quant/UEC/plot/bogus.png").status_code == 404
    assert client.get("/api/quant/UEC/plot/returns.png?period=bogus").status_code == 400
    assert client.get("/api/quant/UEC/plot/returns.png?benchmark=%3Cx%3E").status_code == 400
    assert client.get("/api/quant/%3Cx%3E/plot/returns.png").status_code == 400
    assert client.get("/api/quant/UEC/plot/rolling-sharpe.png?window=7").status_code == 400


def test_api_quant_plot_returns_png(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.quant_stats.api.quant.render_qs_plot",
        lambda *a, **k: calls.append((a, k)) or b"fake-png-bytes",
    )
    response = client.get("/api/quant/uec/plot/rolling-sharpe.png?period=1y&benchmark=SPY&window=63")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert calls == [(("UEC", "1y", "rolling-sharpe"), {"benchmark": "SPY", "window": 63})]


def test_api_quant_montecarlo_validates_params(client):
    assert client.get("/api/quant/UEC/montecarlo.png?sims=7").status_code == 400
    assert client.get("/api/quant/UEC/montecarlo.png?bust=5").status_code == 400
    assert client.get("/api/quant/UEC/montecarlo.png?goal=-5").status_code == 400
    assert client.get("/api/quant/UEC/montecarlo.png?period=bogus").status_code == 400


def test_api_quant_montecarlo_returns_png(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.quant_stats.api.quant.render_montecarlo_chart",
        lambda *a: calls.append(a) or b"fake-png-bytes",
    )
    response = client.get("/api/quant/aapl/montecarlo.png?period=1y&sims=500&bust=-30&goal=100")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert calls == [("AAPL", "1y", 500, -0.3, 1.0)]
