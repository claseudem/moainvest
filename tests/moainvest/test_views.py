"""Sitio MOAINVEST (Resumen, Gráficas e Informe), servido por Flask en la raíz."""
import html
import re
from pathlib import Path

import pytest
from flask import url_for

from app.core.navigation import default_app
from app.core.watchlists import WATCHLISTS, get_watchlist

STATIC = Path(__file__).resolve().parents[2] / "app" / "moainvest" / "static"


def test_resumen_lists_overview_symbols_with_chart_links(client):
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    overview = get_watchlist("overview")
    assert "<title>MOAINVEST | Resumen, gráficas e informes de mercado</title>" in page
    assert 'Resumen del <span class="accent">mercado</span>.' in page
    assert f'data-watchlist-quotes="{overview.slug}"' in page
    for s in overview.symbols:
        assert f'data-quote="{s.ticker}"' in page
        assert f'data-sparkline="{s.ticker}"' in page
        assert html.escape(s.display_name) in page
    assert 'href="/graficas/overview/%5EGSPC"' in page


def test_resumen_hero_has_single_h1_and_cta_to_app(client):
    page = client.get("/").get_data(as_text=True)
    assert page.count("<h1") == 1
    assert 'Analiza el mercado con <span class="accent">datos reales</span>.' in page
    # La acción principal lleva a /app/ sin duplicar el texto «Abrir app» del navbar.
    assert re.search(r'<a href="/app/" class="[^"]*">\s*Empezar a analizar', page)
    assert 'href="#mercado"' in page and 'id="mercado"' in page


def _market_window(page: str) -> str:
    window = re.search(r"<article data-market-window.*?</article>", page, re.S)
    assert window, "falta la ventana de mercado"
    return window.group(0)


def test_market_window_starts_on_first_symbol_without_invented_figures(client):
    page = client.get("/").get_data(as_text=True)
    first = get_watchlist("overview").symbols[0]
    window = _market_window(page)
    assert "data-spark-scope" in window and "data-window-chart" in window
    assert f'data-window="link" href="/graficas/overview/%5EGSPC"' in window
    assert f'data-window="name" class="mt-1 truncate text-xl font-semibold tracking-tight">{html.escape(first.display_name)}<' in window
    for stat in ("min", "max", "change"):
        assert f'data-spark-stat="{stat}"' in window
    # La ventana no lleva [data-quote]: la rellena el JS con el activo elegido.
    assert "data-quote=" not in window
    # Sin datos inventados: los valores los rellena el JS desde la API.
    visible = re.sub(r"<[^>]+>", " ", window)
    assert not re.search(r"\d+,\d{2}", visible)
    assert 'data-window="announce" role="status"' in window


def test_constellation_is_a_keyboard_radiogroup_of_real_symbols(app, client):
    page = client.get("/").get_data(as_text=True)
    window = _market_window(page)
    overview = get_watchlist("overview")
    assert 'role="radiogroup"' in window
    radios = re.findall(r'<button type="button" role="radio" aria-checked="(\w+)" tabindex="(-?\d)"\s+data-select="([^"]+)"', window)
    assert [t for _, _, t in radios] == [s.ticker for s in overview.symbols]
    # Un único activo marcado y solo él en el orden de tabulación (roving tabindex).
    assert [(c, i) for c, i, _ in radios].count(("true", "0")) == 1
    assert all(i == "-1" for c, i, _ in radios if c == "false")
    with app.test_request_context():
        for s in overview.symbols:
            href = url_for("moainvest.grafica", slug="overview", ticker=s.ticker)
            assert f'data-select="{s.ticker}"' in window and f'data-href="{href}"' in window
    assert "no representa correlaciones" in window


def test_heatmap_has_one_comparable_tile_per_symbol(client):
    page = client.get("/").get_data(as_text=True)
    overview = get_watchlist("overview")
    tiles = re.findall(r'<button type="button" data-heat="([^"]+)" aria-pressed="(\w+)"', page)
    assert [t for t, _ in tiles] == [s.ticker for s in overview.symbols]
    assert [p for _, p in tiles].count("true") == 1
    assert "data-selected-link" in page
    assert "Todos los bloques miden lo mismo" in page
    assert "Leyenda:" in page


def test_intro_plays_once_per_session_and_can_be_skipped(client):
    page = client.get("/").get_data(as_text=True)
    head = page.split("</head>")[0]
    # Decide antes de pintar, una vez por sesión y nunca con movimiento reducido.
    assert 'sessionStorage.getItem("moai:intro")' in head
    assert "prefers-reduced-motion: reduce" in head
    assert 'classList.add("intro-play")' in head
    assert 'data-intro class="signal-intro' in page
    assert "data-intro-skip" in page and "Omitir introducción" in page
    # El logotipo oficial, no una reconstrucción.
    assert "logo/moainvest-compact.png" in re.search(r"<div data-intro.*?</button>", page, re.S).group(0)


def test_intro_only_on_home(client):
    for path in ("/informe", "/graficas/overview/%5EGSPC"):
        page = client.get(path).get_data(as_text=True)
        assert "moai:intro" not in page and "data-intro" not in page


def test_narrative_has_four_stages_with_real_capabilities(client):
    from app.graficador.indicators import INDICATORS

    page = client.get("/").get_data(as_text=True)
    story = re.search(r'<section id="como-funciona".*', page, re.S).group(0)
    for stage in ("Mercado", "Datos", "Análisis", "Herramientas"):
        assert f'<h3 class="mt-4 text-lg font-semibold tracking-tight">{stage}</h3>' in story
    assert f"{len(INDICATORS)} indicadores de TA-Lib" in story
    assert "/api/candles" in story
    assert "no representan datos" in story


def test_resumen_quote_states_are_accessible(client):
    page = client.get("/").get_data(as_text=True)
    assert 'data-quotes-status role="status"' in page
    assert 'data-quotes-list aria-busy="true"' in page
    assert "data-quotes-failed hidden" in page
    assert page.count('<span class="sr-only">Cargando precio…</span>') == len(get_watchlist("overview").symbols) + 1


def test_resumen_tools_link_to_real_destinations(client):
    page = client.get("/").get_data(as_text=True)
    tools = re.search(r'<section id="herramientas".*?</section>', page, re.S).group(0)
    for href in ("/graficas", "/informe", "/app/personas/"):
        assert f'href="{href}"' in tools
    for title in ("Gráficas", "Informe", "Comunidad"):
        assert title in tools


def test_resumen_warns_login_only_when_app_requires_it(app, client):
    assert "Requiere sesión" not in client.get("/").get_data(as_text=True)
    app.config["AUTH_REQUIRED"] = True
    page = client.get("/").get_data(as_text=True)
    assert "Requiere sesión" in page and 'href="/ingresar"' in page
    with client.session_transaction() as s:
        s["user"] = {"id": "u1", "email": "ana@example.com", "name": "Ana"}
    assert "Requiere sesión" not in client.get("/").get_data(as_text=True)


def test_resumen_tape_reuses_quotes_and_is_keyboard_friendly(client):
    page = client.get("/").get_data(as_text=True)
    tape = re.search(r"<section aria-labelledby=\"cinta-title\" data-tape.*?</section>", page, re.S)
    assert tape, "falta la cinta de cotizaciones"
    tape = tape.group(0)
    root = page.index('data-watchlist-quotes="overview"')
    assert root < page.index("data-tape") < page.index('id="mercado"')  # mismo sondeo que las tarjetas
    symbols = get_watchlist("overview").symbols
    for s in symbols:
        assert tape.count(f'data-quote="{s.ticker}"') == 2
    # La copia del bucle no se lee ni se tabula; el botón de pausa es un toggle.
    assert tape.count('aria-hidden="true" data-tape-copy') == len(symbols)
    assert tape.count('tabindex="-1"') == len(symbols)
    assert 'data-tape-toggle aria-pressed="false" aria-label="Pausar la cinta"' in tape


def test_resumen_hero_art_is_decorative_without_figures(client):
    page = client.get("/").get_data(as_text=True)
    art = re.search(r'<svg data-scene aria-hidden="true".*?</svg>', page, re.S)
    assert art, "falta la pieza SVG del hero"
    assert "<text" not in art.group(0)


def test_resumen_lists_teams(client):
    from app.personas.content import TEAMS

    page = client.get("/").get_data(as_text=True)
    for team in TEAMS:
        assert team.name in page


def _nav_links(page: str, label: str) -> list[tuple[str, str]]:
    """(href, texto) de los enlaces del ``<nav aria-label="...">`` indicado."""
    nav = re.search(rf'<nav aria-label="{label}".*?</nav>', page, re.S)
    assert nav, label
    return re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', nav.group(0))


@pytest.mark.parametrize("label", ["Menú principal", "Menú principal móvil", "Navegación del pie de página"])
def test_navbar_has_only_inicio_and_app(client, label):
    page = client.get("/").get_data(as_text=True)
    assert _nav_links(page, label) == [("/", "Inicio"), ("/app/", "App")]


def test_navbar_marks_inicio_as_current_on_home(client):
    page = client.get("/").get_data(as_text=True)
    assert '<a href="/" aria-current="page"' in page
    assert '<a href="/app/" aria-current="page"' not in page


def test_header_and_mobile_button_open_app(client):
    page = client.get("/").get_data(as_text=True)
    assert page.count(">Abrir app</a>") == 2
    assert "Generar informe" not in page
    assert len(re.findall(r'<a href="/app/" class="[^"]*">Abrir app</a>', page)) == 2


@pytest.mark.parametrize("path", ["/app/", "/app"])
def test_app_home_redirects_to_default_app(app, client, path):
    with app.test_request_context():
        target = url_for(default_app().endpoint)
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(target)


def test_home_content_links_still_work(client):
    # Gráficas e Informe salen del navbar, pero los atajos del Resumen siguen funcionando.
    page = client.get("/").get_data(as_text=True)
    for href in ("/graficas", "/informe"):
        assert f'href="{href}"' in page
    assert client.get("/graficas").status_code == 302
    assert client.get("/informe").status_code == 200


def test_layout_has_assets(client):
    page = client.get("/informe").get_data(as_text=True)
    assert "/static/moainvest/moainvest.css" in page
    assert "/static/moainvest/moainvest.js" in page
    assert 'id="menu-movil" hidden' in page


@pytest.mark.parametrize("path", ["/graficas", "/graficas/overview"])
def test_graficas_redirects_to_first_symbol(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/graficas/overview/%5EGSPC")


def test_watchlist_redirects_to_its_first_symbol(client):
    watchlist = WATCHLISTS[1]
    response = client.get(f"/graficas/{watchlist.slug}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/graficas/{watchlist.slug}/{watchlist.symbols[0].ticker}")


def test_chart_page_renders_workspace(client):
    watchlist = WATCHLISTS[1]
    symbol = watchlist.symbols[1]
    response = client.get(f"/graficas/{watchlist.slug}/{symbol.ticker}")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert f"<title>{symbol.display_name} · Gráficas | MOAINVEST</title>" in page
    assert '<meta name="robots" content="noindex">' in page
    assert f'data-chart-workspace data-ticker="{symbol.ticker}"' in page
    assert "lightweight-charts.standalone.production.js" in page
    # El rango por defecto es 1M y todos los símbolos de la watchlist están en la lista.
    assert re.search(r'data-range="1mo" data-interval="1d" aria-pressed="true"', page)
    assert page.count("data-quote=") == len(watchlist.symbols)
    for w in WATCHLISTS:
        assert f'href="/graficas/{w.slug}/' in page


def test_chart_page_accepts_encoded_ticker(client):
    assert client.get("/graficas/overview/%5EGSPC").status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/graficas/no-existe", "/graficas/overview/NOPE", "/no-existe"],
)
def test_unknown_paths_show_moainvest_404(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "Este camino todavía no" in response.get_data(as_text=True)


def test_informe_lists_watchlists_and_api_urls(client):
    page = client.get("/informe").get_data(as_text=True)
    assert 'data-preview-url="/api/report/preview"' in page
    assert 'data-send-url="/api/email/send-assets-report"' in page
    for w in WATCHLISTS:
        assert f'name="watchlists" value="{w.slug}" checked' in page


@pytest.mark.parametrize("path", ["/app/analisis-varianza/", "/app/informes/"])
def test_other_sections_link_to_graficador_from_sidebar(client, path):
    # La primera entrada del sidebar oscuro es ahora el Graficador.
    response = client.get(path)
    assert response.status_code == 200
    assert 'href="/app/graficador/"' in response.get_data(as_text=True)


def test_old_chart_urls_are_gone(client):
    # El antiguo panel oscuro (/graficas/w/<slug>) ya no existe; /graficas/ sigue funcionando.
    assert client.get("/graficas/").status_code == 302
    assert client.get("/graficas/w/overview").status_code == 404


def test_compiled_css_includes_classes_used_by_templates_and_js():
    css = (STATIC / "moainvest.css").read_text()
    # Clases que solo aparecen en moainvest.js (tonos que se ponen en tiempo de ejecución).
    for cls in ("bg-up-soft", "text-brand-deep", r"hover\:bg-line", r"border-ink\/30", ".bg-up{", ".border-dashed",
                r"bg-brand\/25", r"bg-up\/25", r"border-up\/30", r"border-brand\/25"):
        assert cls in css, cls
    for cls in (".accent", ".eyebrow", ".hero-in", "--color-brand:#c8102e", ".tape-track", ".spark-reveal", "tape-scroll",
                ".signal-intro{display:none}", "intro-out", ".sig-logo", "html.tab-hidden"):
        assert cls in css, cls
