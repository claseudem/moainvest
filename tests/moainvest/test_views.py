"""Sitio MOAINVEST (Resumen, Gráficas e Informe), servido por Flask en la raíz."""
import html
import re
from urllib.parse import parse_qs, urlsplit
from pathlib import Path

import pytest
from flask import url_for

from app.core.navigation import default_app
from app.core.watchlists import WATCHLISTS, get_watchlist
from app.moainvest import barometer

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
    for cls in (".accent", ".eyebrow", ".hero-in", "--color-brand:#c8102e"):
        assert cls in css, cls


def test_home_has_carousels_marquee_barometer_and_tools(client):
    overview = get_watchlist("overview")
    page = client.get("/").get_data(as_text=True)
    tickers = ",".join(s.ticker for s in overview.symbols)
    # Carrusel de noticias: pide las noticias de COMUNIDAD de los activos del resumen.
    carousels = dict(re.findall(r'data-carousel-kind="(\w+)" data-src="([^"]+)"', page))
    news_url = urlsplit(html.unescape(carousels["news"]))
    assert news_url.path == "/api/comunidad/noticias"
    assert parse_qs(news_url.query)["tickers"] == [tickers]
    assert carousels["comments"] == "/api/comunidad/comentarios"
    # Cinta: cada activo dos veces (la copia, oculta a lectores de pantalla) dentro del mismo sondeo de precios.
    marquee = page.split('class="marquee ', 1)[1].split("</div>", 2)[0]
    for s in overview.symbols:
        assert marquee.count(f'data-quote="{s.ticker}"') == 2
    assert page.index(f'data-watchlist-quotes="{overview.slug}"') < page.index('class="marquee ')
    # Barómetro: mapa con todas las regiones y su endpoint.
    assert "Barómetro Global de" in page and 'data-src="/api/barometro"' in page
    for region in barometer.REGIONS:
        assert f'data-region="{region.slug}"' in page
    # Herramientas en acordeón: solo la primera abierta por defecto.
    assert page.count('class="tool-item"') == 3
    assert page.count("data-open") == 1
    # Comunidad con su título exacto y enlace; sin la sección de equipos.
    assert '<h2 id="comunidad-title"' in page and ">Comunidad</h2>" in page
    assert "Ver toda la comunidad" in page
    assert "Los equipos que" not in page and "Quiénes somos" not in page


@pytest.mark.parametrize(
    "ticker, kind",
    [("^GSPC", "Índice"), ("BTC-USD", "Cripto"), ("EURUSD=X", "Divisa"), ("UEC", "Acción")],
)
def test_asset_cards_show_category(client, ticker, kind):
    page = client.get("/").get_data(as_text=True)
    card = page.split(f'data-quote="{ticker}" data-spotlight', 1)[1].split("</li>", 1)[0]
    assert kind in card
    assert "data-period-range" in card


def test_barometer_averages_indices_and_falls_back_to_global(client, monkeypatch):
    from app.core.market_data import Quote

    changes = {"^GSPC": 1.0, "^IXIC": 2.0, "^DJI": None, "^GSPTSE": 0.0}
    monkeypatch.setattr(
        barometer.market_data,
        "get_quote",
        lambda t: Quote(symbol=t, name=t, price=100.0, previous_close=None, change=None, change_percent=changes.get(t)),
    )
    regions = {r["slug"]: r for r in client.get("/api/barometro").get_json()["regions"]}
    assert regions["norteamerica"]["change_percent"] == pytest.approx(1.0)  # (1 + 2 + 0) / 3
    assert regions["norteamerica"]["fallback"] is False
    assert [i["name"] for i in regions["norteamerica"]["indices"]][:2] == ["S&P 500", "Nasdaq"]
    # Sin datos (o sin índice directo): promedio global, marcado como estimado.
    assert regions["europa"]["fallback"] is True
    assert regions["rusia-asia-central"]["change_percent"] == pytest.approx(1.0)


def test_world_map_covers_every_region():
    from app.moainvest.barometer import region_of

    svg = (STATIC.parent / "templates" / "moainvest" / "_world_map.svg").read_text()
    for region in barometer.REGIONS:
        assert f'data-region="{region.slug}"' in svg
    assert region_of({"ADM0_A3": "RUS", "CONTINENT": "Europe"}) == "rusia-asia-central"
    assert region_of({"ADM0_A3": "MEX", "CONTINENT": "North America", "SUBREGION": "Central America"}) == "latam"
    assert region_of({"ADM0_A3": "ATA", "CONTINENT": "Antarctica"}) is None


def test_home_js_keeps_15s_polling_and_adds_interactions():
    js = (STATIC / "moainvest.js").read_text()
    assert "const QUOTE_POLL_MS = 15000;" in js
    for name in ("initCarousels", "initBarometer", "initPointerEffects", "enableSparkHover", "renderPeriodRange"):
        assert f"{name}();" in js or f"function {name}(" in js
    css = (STATIC / "moainvest.css").read_text()
    for cls in (".marquee-track", ".tool-accordion", ".spotlight", ".cursor-badge", ".spark-tip", ".hero-glow", ".carousel-viewport", ".map-region", ".asset-card"):
        assert cls in css
