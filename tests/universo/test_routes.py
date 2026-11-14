"""Página de "Mi universo de acciones" y su catálogo de acciones."""
from app.universo.universe import UNIVERSE, format_market_cap, parse_market_cap, sectors


def test_universe_loads_every_stock_once():
    tickers = [s.ticker for s in UNIVERSE]
    assert len(tickers) == len(set(tickers)) == 149
    assert tickers[0] == "CTVA" and tickers[-1] == "BLZE"


def test_universe_uses_yahoo_tickers():
    tickers = {s.ticker for s in UNIVERSE}
    assert {"PBR-A", "VOD", "BEKE", "RDY", "TAK"} <= tickers


def test_universe_parses_market_cap_and_missing_pe():
    stocks = {s.ticker: s for s in UNIVERSE}
    assert stocks["BNL"].market_cap == 3.56e9
    assert stocks["BNL"].pe == 24.76
    assert stocks["UTZ"].pe is None
    assert parse_market_cap("696.55M") == 696.55e6


def test_sectors_are_counted_most_common_first():
    counts = sectors()
    assert sum(n for _, n in counts) == len(UNIVERSE)
    assert [n for _, n in counts] == sorted((n for _, n in counts), reverse=True)


def test_format_market_cap():
    assert format_market_cap(3.56e9) == "3.56 B"
    assert format_market_cap(696.55e6) == "697 M"


def test_page_lists_every_stock_with_quick_links(client):
    response = client.get("/app/universo/")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Mi universo de acciones · MoaiInvest" in html
    assert 'data-quote-url="/api/quote/__T__"' in html
    for stock in UNIVERSE:
        assert f'data-ticker="{stock.ticker}"' in html
        assert f"/app/graficador/?ticker={stock.ticker}" in html
        assert f"/app/quant-stats/fundamentales?ticker={stock.ticker}" in html
    assert "universo.js" in html


def test_page_is_in_sidebar(client):
    html = client.get("/app/universo/").data.decode()
    assert 'href="/app/universo/"' in html
