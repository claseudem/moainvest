"""Página /mercados: categorías, precios por categoría y curva de rendimiento."""
import pytest

from app.core import market_data
from app.core.market_data import Quote
from app.moainvest import markets


@pytest.fixture()
def fake_quotes(monkeypatch):
    yields = {"^IRX": 4.5, "^FVX": 4.0, "^TNX": 4.2, "^TYX": 4.6}

    def get_quote(ticker):
        if ticker == "FAIL":
            raise RuntimeError("Yahoo is down")
        price = yields.get(ticker, 100.0)
        return Quote(ticker, ticker, price, price - 1, 1.0, 1.0, "USD")

    monkeypatch.setattr(market_data, "get_quote", get_quote)


def test_market_slugs_are_unique_and_have_symbols():
    slugs = [m.slug for m in markets.MARKETS]
    assert len(slugs) == len(set(slugs))
    assert all(m.symbols and m.about for m in markets.MARKETS)
    assert {"bonos-publicos", "bonos-corporativos", "divisas", "cripto"} <= set(slugs)


def test_corporate_bonds_belong_to_a_declared_group():
    bonds = markets.get_market("bonos-corporativos")
    assert bonds.kind == "bonds"
    assert {s.group for s in bonds.symbols} <= set(bonds.groups)


def test_yield_curve_points_have_maturities():
    curve = markets.get_market("bonos-publicos")
    assert curve.kind == "yield"
    assert all(s.years for s in curve.symbols)


@pytest.mark.parametrize(
    ("yields", "estado"),
    [
        ({0.25: 3.5, 10: 4.5}, "normal"),
        ({0.25: 4.4, 10: 4.5}, "plana"),
        ({0.25: 5.0, 10: 4.2}, "invertida"),
        ({0.25: None, 10: 4.2}, "sin-datos"),
    ],
)
def test_curve_shape(yields, estado):
    assert markets.curve_shape(yields)["estado"] == estado


def test_mercados_page_lists_every_market(client):
    response = client.get("/mercados")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<title>MOAINVEST | Mercados" in page
    for m in markets.MARKETS:
        assert f'id="{m.slug}"' in page
        assert f'href="#{m.slug}"' in page
        assert f'data-quotes-url="/api/mercados/{m.slug}/quotes"' in page
        for s in m.symbols:
            assert f'data-quote="{s.ticker}"' in page
    assert "data-yield-curve" in page
    assert 'data-bond-filter="Alto rendimiento"' in page
    assert '<a href="/mercados" aria-current="page"' in page


def test_market_quotes_api(client, fake_quotes):
    data = client.get("/api/mercados/divisas/quotes").get_json()
    assert set(data) == set(markets.get_market("divisas").tickers)
    assert data["USDCOP=X"]["price"] == 100.0


def test_market_quotes_api_unknown_market_is_404(client):
    assert client.get("/api/mercados/no-existe/quotes").status_code == 404


def test_market_quotes_skip_failing_tickers(client, fake_quotes, monkeypatch):
    fake = markets.Market("x", "X", "list", "Prueba", (markets.Instrument("FAIL"), markets.Instrument("OK")))
    monkeypatch.setattr(markets, "_BY_SLUG", {"x": fake})
    assert list(client.get("/api/mercados/x/quotes").get_json()) == ["OK"]


def test_yield_curve_api(client, fake_quotes):
    data = client.get("/api/mercados/curva").get_json()
    assert [p["anios"] for p in data["puntos"]] == [0.25, 5, 10, 30]
    assert data["puntos"][2]["rendimiento"] == 4.2
    assert data["estado"] == "invertida"  # 3 meses (4,5 %) paga más que 10 años (4,2 %)
