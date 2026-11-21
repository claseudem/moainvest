"""Sitio MOAINVEST (Resumen, Gráficas e Informe), servido por Flask en la raíz."""
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
    for cls in ("bg-up-soft", "text-brand-deep", r"hover\:bg-line", r"border-ink\/30"):
        assert cls in css, cls
    for cls in (".accent", ".eyebrow", ".hero-in"):
        assert cls in css, cls
    # Los valores salen de core/static/css/tokens.css (fuente única), que se
    # importa al compilar; @theme solo los expone como utilidades.
    assert "--brand:#c8102e" in css
    assert "--color-brand:var(--brand)" in css


def test_home_shows_every_asset_and_a_real_signup_form(client):
    page = client.get("/").get_data(as_text=True)
    # La banda oscura muestra todos los activos de todas las watchlists, sin repetir.
    tickers = {s.ticker for w in WATCHLISTS for s in w.symbols}
    slugs = " ".join(w.slug for w in WATCHLISTS)
    assert f'data-watchlist-quotes="{slugs}"' in page
    for ticker in tickers:
        assert f'data-quote="{ticker}"' in page
    # El cierre tiene el registro real (POST a /registro) cuando no hay sesión.
    assert '<form method="post" action="/registro"' in page
    for name in ("name", "email", "password", "password2"):
        assert f'name="{name}"' in page
    assert "Invierte con" in page and "Datos de mercado de Yahoo Finance." in page


def test_home_hides_signup_form_when_logged_in(client):
    with client.session_transaction() as s:
        s["user"] = {"id": "u1", "email": "ana@example.com", "name": "Ana"}
    page = client.get("/").get_data(as_text=True)
    assert 'action="/registro"' not in page
    assert "Hola, Ana." in page
