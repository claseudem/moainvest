"""Rutas de la app "Pronosticador" (página y API), sin red: MotherDuck se
sustituye por una base DuckDB en memoria."""
import duckdb
import numpy as np
import pandas as pd
import pytest

from app import create_app
from app.pronosticador import econometrics
from config import TestingConfig


@pytest.fixture
def memory_db(monkeypatch):
    """``get_connection`` devuelve una DuckDB en memoria (vacía) en vez de MotherDuck."""
    con = duckdb.connect(":memory:")
    # cargar_datos cierra la conexión al terminar: se le da un cursor nuevo cada vez.
    monkeypatch.setattr("app.pronosticador.db.get_connection", lambda: con.cursor())
    yield con
    con.close()


@pytest.fixture
def spy_table(memory_db):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=400)
    close = 450 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(dates))))
    df = pd.DataFrame({"Date": dates, "Close": close})
    memory_db.execute("CREATE TABLE raw_spy_daily AS SELECT * FROM df")
    return memory_db


def _fake_spy_candles(n=400):
    rng = np.random.default_rng(1)
    start = pd.Timestamp("2024-01-01", tz="UTC")
    close = 450 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    return [{"time": int((start + pd.Timedelta(days=i)).timestamp()), "close": float(c)} for i, c in enumerate(close)]


@pytest.fixture(autouse=True)
def yahoo(monkeypatch):
    """Yahoo Finance falso (sin red); ``calls`` guarda los tickers pedidos."""
    calls = []

    def fake(ticker, range_, interval):
        calls.append((ticker, range_, interval))
        return _fake_spy_candles()

    monkeypatch.setattr("app.pronosticador.db.market_data.get_candles", fake)
    return calls


@pytest.fixture(autouse=True)
def reset_model_state():
    from app.pronosticador import api

    api._ESTADO_MODELO.update(ar=None, garch=None, metricas=None)


def test_pronosticador_page_is_reachable(client):
    response = client.get("/app/pronosticador/")
    assert response.status_code == 200
    html = response.data
    assert "Pronosticador · MoaiInvest".encode() in html
    assert b'id="chart-serie"' in html
    assert b"plotly" in html
    # Extiende el layout de MOAI y se marca activa en el sidebar.
    assert b'class="sidebar"' in html
    assert b'href="/app/pronosticador/" title="Pronosticador" aria-current="page"' in html
    assert b"ui-icon--chart-spline" in html
    # Sin MLFLOW_UI_URL no hay enlace a MLflow (ni al 127.0.0.1:5001 del original).
    assert b"pron-mlflow-link" not in html
    assert b"127.0.0.1:5001" not in html


def test_short_url_redirects_to_app_area(client):
    response = client.get("/pronosticador/")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("/app/pronosticador/")


def test_mlflow_link_only_when_configured():
    class WithMlflowUi(TestingConfig):
        MLFLOW_UI_URL = "http://mlflow.example:5001"

    html = create_app(WithMlflowUi).test_client().get("/app/pronosticador/").data
    assert b'id="pron-mlflow-link" href="http://mlflow.example:5001"' in html


def test_pronosticador_requires_login_when_auth_required():
    class WithAuth(TestingConfig):
        AUTH_REQUIRED = True

    client = create_app(WithAuth).test_client()
    for path in ("/app/pronosticador/", "/app/pronosticador/api/dashboard-data", "/app/pronosticador/predict"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/ingresar" in response.headers["Location"]


def test_without_token_uses_yahoo_finance(client, yahoo):
    response = client.get("/app/pronosticador/api/dashboard-data")
    assert response.status_code == 200
    data = response.get_json()
    assert data["fuente"] == "Yahoo Finance"
    assert data["metricas"]["sigma_t1"] > 0
    assert data["audit_records"] == []
    assert yahoo == [("SPY", "10y", "1d")]


def test_missing_table_falls_back_to_yahoo_finance(client, memory_db, yahoo):
    response = client.get("/app/pronosticador/api/dashboard-data")
    assert response.status_code == 200
    assert response.get_json()["fuente"] == "Yahoo Finance"


def test_no_source_available_returns_clear_error(client, memory_db, monkeypatch):
    def broken(*args):
        raise ConnectionError("sin red")

    monkeypatch.setattr("app.pronosticador.db.market_data.get_candles", broken)
    response = client.get("/app/pronosticador/api/dashboard-data")
    assert response.status_code == 503
    error = response.get_json()["error"]
    assert "raw_spy_daily" in error and "no existe" in error
    assert "Yahoo Finance" in error


def test_too_few_yahoo_closes_is_an_error(client, monkeypatch):
    monkeypatch.setattr("app.pronosticador.db.market_data.get_candles", lambda *a: _fake_spy_candles(30))
    response = client.get("/app/pronosticador/api/dashboard-data")
    assert response.status_code == 503
    assert "al menos 250" in response.get_json()["error"]


def test_api_rejects_invalid_lags(client):
    assert client.get("/app/pronosticador/api/dashboard-data?lags=9").status_code == 400
    assert client.post("/app/pronosticador/train", json={"lags": "x"}).status_code == 400


def test_dashboard_data_with_spy_table(client, spy_table):
    response = client.get("/app/pronosticador/api/dashboard-data?lags=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["fuente"] == "MotherDuck"
    assert data["lags"] == 2
    assert data["decision_color"] in {"green", "yellow", "red"}
    m = data["metricas"]
    assert m["sigma_t1"] > 0
    assert m["var_99"] > m["var_95"]
    assert m["cvar_95"] > m["var_95"]
    assert len(data["historico"]["precios"]) == 60
    assert len(data["montecarlo"]["trayectorias"]) == 25
    assert data["audit_records"] == []


def test_motherduck_table_wins_over_yahoo(client, spy_table, yahoo):
    assert client.get("/app/pronosticador/api/dashboard-data").get_json()["fuente"] == "MotherDuck"
    assert yahoo == []


def test_train_then_predict_reuses_model(client, spy_table):
    trained = client.post("/app/pronosticador/train", json={"lags": 1})
    assert trained.status_code == 200
    assert trained.get_json()["status"] == "ok"
    predicted = client.get("/app/pronosticador/predict")
    assert predicted.status_code == 200
    assert predicted.get_json() == trained.get_json()["metricas"]


def test_mlflow_tracking_is_optional(app):
    with app.app_context():
        assert econometrics.registrar_en_mlflow({"a": 1}, {"m": 1.0}) is False
        # Servidor inexistente: no lanza, solo devuelve False.
        app.config["MLFLOW_TRACKING_URI"] = "http://127.0.0.1:9"
        assert econometrics.registrar_en_mlflow({"a": 1}, {"m": 1.0}) is False
