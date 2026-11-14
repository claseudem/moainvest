"""Sitio MOAINVEST (Resumen y Gráficas), servido por Flask en la raíz."""
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
    assert "<title>MOAINVEST | Resumen y gráficas de mercado</title>" in page
    assert 'Resumen del <span class="accent">mercado</span>.' in page
    assert f'data-watchlist-quotes="{overview.slug}"' in page
    for s in overview.symbols:
        assert f'data-quote="{s.ticker}"' in page
        assert f'data-sparkline="{s.ticker}"' in page
    assert 'href="/graficas/overview/%5EGSPC"' in page


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
    # Gráficas sale del navbar, pero los atajos del Resumen siguen funcionando.
    page = client.get("/").get_data(as_text=True)
    for href in ("/graficas", "/app/graficador/quant-stats/fundamentales"):
        assert f'href="{href}"' in page
    assert client.get("/graficas").status_code == 302


def test_informe_page_was_removed(client):
    # La app Informes se eliminó: ni el sitio rojo ni el Resumen la enlazan.
    page = client.get("/").get_data(as_text=True)
    assert 'href="/informe"' not in page
    assert "Informe" not in page
    assert client.get("/informe").status_code == 404


def test_layout_has_assets(client):
    page = client.get("/").get_data(as_text=True)
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


@pytest.mark.parametrize("path", ["/app/analisis-varianza/", "/app/favoritos/"])
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
    for cls in ("bg-up-soft", "text-brand-deep", r"hover\:bg-line"):
        assert cls in css, cls
    for cls in (".accent", ".eyebrow", ".hero-in", "--color-brand:#c8102e"):
        assert cls in css, cls
