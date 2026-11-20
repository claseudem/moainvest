"""Acciones del activo (core/_asset_actions.html), deep links entre apps y shell limpio."""
import html
import re

import pytest

from app.core.tickers import parse_tickers
from app.core.watchlists import get_watchlist


def _actions(page: str) -> list[str]:
    """Bloques ``asset-actions`` de la página."""
    return re.findall(r'<div class="asset-actions[^"]*"[^>]*>.*?</div>', page, re.S)


def _hrefs(block: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', block)]


def test_parse_tickers_keeps_valid_unique_and_limits():
    assert parse_tickers("aapl, msft;AAPL btc-usd <x> ^gspc", 3) == ["AAPL", "MSFT", "BTC-USD"]
    assert parse_tickers(None, 5) == [] and parse_tickers("", 5) == []


def test_home_cards_link_each_asset_to_every_tool(client):
    page = client.get("/").get_data(as_text=True)
    overview = get_watchlist("overview")
    blocks = _actions(page)
    assert len(blocks) == len(overview.symbols)
    first = overview.symbols[0].ticker
    hrefs = _hrefs(blocks[0])
    assert hrefs == [
        f"/app/graficador/?ticker={first.replace('^', '%5E')}",
        f"/app/graficador/quant-stats/fundamentales?ticker={first.replace('^', '%5E')}",
        f"/app/analisis-varianza/?ticker={first.replace('^', '%5E')}",
        f"/app/pyportfolio-opt/?tickers={first.replace('^', '%5E')}",
    ]
    # Sin sesión no hay botón de guardar, y cada acción se lee con su activo.
    assert 'data-asset-action="favorite"' not in page
    assert f'<span class="asset-actions__sr"> de {first}</span>' in blocks[0]


def test_home_ranks_app_tools_above_public_shortcuts(client):
    page = client.get("/").get_data(as_text=True)
    tools = page.index('id="herramientas-title"')
    shortcuts = page.index('id="atajos-title"')
    assert page.index('id="mercado-title"') < tools < shortcuts
    for href in ("/app/graficador/", "/app/graficador/quant-stats/fundamentales", "/app/analisis-varianza/", "/app/pyportfolio-opt/"):
        assert page.index(f'href="{href}"', tools) < shortcuts
    assert 'action="/app/graficador/"' in page and 'name="ticker"' in page
    assert "data-market-pulse" in page


def test_graficador_shows_actions_not_already_in_its_tabs(client):
    page = client.get("/app/graficador/?ticker=AAPL").get_data(as_text=True)
    (block,) = _actions(page)
    # Gráfico y Quant stats ya son pestañas del Graficador.
    assert 'data-asset-action="chart"' not in block and 'data-asset-action="quant"' not in block
    assert "/app/analisis-varianza/?ticker=AAPL" in block
    assert "/app/pyportfolio-opt/?tickers=AAPL" in block


def test_graficador_with_invalid_ticker_has_no_actions(client):
    assert _actions(client.get("/app/graficador/?ticker=%3Cx%3E").get_data(as_text=True)) == []


def test_quant_stats_shows_actions_not_already_in_its_tabs(client, fake_uec):
    page = client.get("/app/graficador/quant-stats/fundamentales?ticker=UEC").get_data(as_text=True)
    (block,) = _actions(page)
    assert 'data-asset-action="quant"' not in block and 'data-asset-action="chart"' not in block
    assert "/app/analisis-varianza/?ticker=UEC" in block


def test_varianza_deep_link_prefills_both_forms(client):
    page = client.get("/app/analisis-varianza/?ticker=nvda").get_data(as_text=True)
    assert 'id="varianza-form" data-autorun' in page
    assert 'value="NVDA"' in page
    assert 'data-initial-tickers="NVDA"' in page


def test_varianza_deep_link_with_several_tickers_drops_invalid_ones(client):
    page = client.get("/app/analisis-varianza/?tickers=AAPL,<b>,MSFT").get_data(as_text=True)
    assert 'data-initial-tickers="AAPL,MSFT"' in page
    assert "data-autorun" not in page  # sin ?ticker= no se descarga el histórico


def test_varianza_without_params_does_not_autorun(client):
    page = client.get("/app/analisis-varianza/").get_data(as_text=True)
    assert "data-autorun" not in page and "data-initial-tickers" not in page


def test_pyportfolio_deep_link_replaces_sample_tickers(client):
    page = client.get("/app/pyportfolio-opt/?tickers=tsla,qqq").get_data(as_text=True)
    assert 'value="TSLA, QQQ"' in page and "data-autorun" in page
    assert "data-autorun" not in client.get("/app/pyportfolio-opt/").get_data(as_text=True)


@pytest.mark.parametrize("url", ["/app/graficador/", "/app/analisis-varianza/"])
def test_sidebar_has_no_redundant_labels(client, url):
    page = client.get(url).get_data(as_text=True)
    sidebar = page.split('<aside class="sidebar"', 1)[1].split("</aside>", 1)[0]
    for noise in ("Nuevas secciones", "Herramientas", ">Apps<", "Datos de Yahoo Finance", "sidebar__group"):
        assert noise not in sidebar
    # Los dos grupos (herramientas / comunidad y perfil) quedan separados por una línea.
    assert sidebar.count('<hr class="sidebar__divider">') == 1
