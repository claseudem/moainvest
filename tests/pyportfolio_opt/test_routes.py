"""Rutas de la app "Pyportfolio opt" (página y API de retornos esperados)."""
import pytest

from app.pyportfolio_opt import expected


def test_page_is_reachable_and_in_sidebar(client):
    response = client.get("/app/pyportfolio-opt/")
    assert response.status_code == 200
    html = response.data
    assert "Pyportfolio opt · MoaiInvest".encode() in html
    assert b'id="pypfopt-form"' in html
    assert b'value="historical"' in html and b'value="ema"' in html
    assert b'data-max-tickers="10"' in html
    # Enlace activo del sidebar.
    assert b'href="/app/pyportfolio-opt/" title="Pyportfolio opt" aria-current="page"' in html


@pytest.fixture
def fake_compute(monkeypatch):
    calls = []

    def compute(**params):
        calls.append(params)
        assets = [
            expected.AssetExpectedReturn(
                ticker=t,
                observations=250,
                start="2025-01-02",
                end="2025-12-31",
                returns={m: 0.1 for m in params["methods"]},
            )
            for t in params["tickers"]
        ]
        return expected.ExpectedReturnsResult(
            period=params["period"],
            methods=params["methods"],
            span=params["span"],
            compounding=params["compounding"],
            log_returns=params["log_returns"],
            assets=assets,
            missing=[],
        )

    monkeypatch.setattr("app.pyportfolio_opt.api.expected.compute_expected_returns", compute)
    return calls


def test_api_returns_both_methods_by_default(client, fake_compute):
    response = client.get("/api/pyportfolio-opt/expected-returns?tickers=aapl, msft,AAPL")
    assert response.status_code == 200
    data = response.get_json()
    assert [a["ticker"] for a in data["assets"]] == ["AAPL", "MSFT"]
    assert data["assets"][0]["historical"] == 0.1 and data["assets"][0]["ema"] == 0.1
    assert fake_compute[0] == {
        "tickers": ["AAPL", "MSFT"],
        "period": "5y",
        "methods": ("historical", "ema"),
        "span": 500,
        "compounding": True,
        "log_returns": False,
    }


def test_api_passes_method_and_options(client, fake_compute):
    response = client.get(
        "/api/pyportfolio-opt/expected-returns?tickers=SPY&method=ema&period=2y&span=120&compounding=0&log_returns=1"
    )
    assert response.status_code == 200
    assert fake_compute[0]["methods"] == ("ema",)
    assert fake_compute[0]["period"] == "2y"
    assert fake_compute[0]["span"] == 120
    assert fake_compute[0]["compounding"] is False
    assert fake_compute[0]["log_returns"] is True


@pytest.mark.parametrize(
    "query",
    [
        "",
        "tickers=" + ",".join(f"T{i}" for i in range(11)),
        "tickers=AAPL&period=1mo",
        "tickers=AAPL&method=capm",
        "tickers=AAPL&span=abc",
        "tickers=AAPL&span=1",
        "tickers=AA%20PL$",
    ],
)
def test_api_rejects_invalid_input(client, fake_compute, query):
    response = client.get(f"/api/pyportfolio-opt/expected-returns?{query}")
    assert response.status_code == 400
    assert "error" in response.get_json()
    assert fake_compute == []


def test_api_returns_404_without_prices(client, monkeypatch):
    monkeypatch.setattr("app.pyportfolio_opt.expected.market_data.get_candles", lambda *a, **k: [])
    response = client.get("/api/pyportfolio-opt/expected-returns?tickers=NADA")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_api_chart_returns_png(client, fake_compute, monkeypatch):
    monkeypatch.setattr(
        "app.pyportfolio_opt.api.expected.render_expected_returns_chart", lambda result: b"fake-png-bytes"
    )
    response = client.get("/api/pyportfolio-opt/expected-returns.png?tickers=AAPL")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == b"fake-png-bytes"
