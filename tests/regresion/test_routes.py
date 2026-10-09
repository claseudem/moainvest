import pytest


def test_regresion_page_is_reachable(client):
    response = client.get("/app/regresion/")

    assert response.status_code == 200
    assert "Regresión ML · MoaiInvest".encode() in response.data
    assert b'id="regresion-form"' in response.data
    assert b'class="table regresion-table"' in response.data


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"ticker": "!bad", "horizon": 5}, "Ticker inválido"),
        ({"ticker": "SPY", "horizon": 0}, "horizonte"),
        ({"ticker": "SPY", "horizon": "no"}, "horizonte"),
        ({"ticker": "SPY", "period": "10y", "horizon": 5}, "Periodo inválido"),
    ],
)
def test_regression_api_validates_input(client, payload, message):
    response = client.post("/api/regression/train", json=payload)

    assert response.status_code == 400
    assert message in response.json["error"]


def test_regression_api_returns_metrics_and_drift(client, monkeypatch):
    from app.regresion import api

    metrics = {
        "mae": 0.01,
        "rmse": 0.02,
        "r2": 0.4,
        "acierto_direccional": 0.6,
        "mae_vs_paseo_aleatorio": 0.8,
    }
    result = {
        "ticker": "SPY",
        "periodo": "5y",
        "horizonte": 5,
        "n_train": 200,
        "n_test": 50,
        "modelos": {"Ridge": {"metricas": {"train": metrics, "test": metrics}}},
        "benchmarks": {"Paseo aleatorio": {"metricas": {"train": metrics, "test": metrics}}},
    }
    tracked = {
        "Ridge": {
            "predicciones": {"ks": 0.2, "p_value": 0.03, "psi": 0.25},
            "features": {"retorno_rezagado_1": {"ks": 0.1, "p_value": 0.4, "psi": 0.02}},
            "grafico": b"png-data",
            "drift_alert": True,
        }
    }
    monkeypatch.setattr(api.model, "train_regression", lambda *args, **kwargs: result)
    monkeypatch.setattr(api.tracking, "log_training_runs", lambda result: tracked)

    response = client.post("/api/regression/train", json={"ticker": "spy", "horizon": 5})

    assert response.status_code == 200
    payload = response.json
    assert payload["resultados"][0]["test"]["mae"] == 0.01
    assert payload["resultados"][0]["drift"]["psi"] == 0.25
    assert payload["resultados"][0]["grafico"] == "data:image/png;base64,cG5nLWRhdGE="
    assert payload["resultados"][1]["modelo"] == "Paseo aleatorio"


def test_train_regression_cli_prints_comparison(client, monkeypatch):
    from app.regresion import commands

    metric = {
        "mae": 0.01,
        "rmse": 0.02,
        "r2": 0.4,
        "acierto_direccional": 0.6,
        "mae_vs_paseo_aleatorio": 0.8,
    }
    result = {
        "modelos": {"Ridge": {"metricas": {"train": metric, "test": metric}}},
        "benchmarks": {"Paseo aleatorio": {"metricas": {"train": metric, "test": metric}}},
    }
    monkeypatch.setattr(commands.model, "train_regression", lambda *args, **kwargs: result)
    monkeypatch.setattr(commands.tracking, "log_training_runs", lambda result: {"Ridge": {"predicciones": {}}})

    outcome = client.application.test_cli_runner().invoke(
        args=["train-regression", "--ticker", "SPY", "--horizon", "5"]
    )

    assert outcome.exit_code == 0, outcome.output
    assert "Linear" not in outcome.output
    assert "Paseo aleatorio" in outcome.output
    assert "MAE/RW" in outcome.output