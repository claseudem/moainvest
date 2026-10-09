import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.pipeline import Pipeline

from app.regresion import model


def _fake_candles(count=520):
    dates = pd.bdate_range("2022-01-03", periods=count)
    returns = 0.0002 + 0.012 * np.sin(np.arange(count) / 8) + 0.003 * np.cos(np.arange(count) / 3)
    closes = 100 * np.exp(np.cumsum(returns))
    return [
        {"time": int(date.timestamp()), "close": float(close)}
        for date, close in zip(dates, closes)
    ]


def test_build_dataset_uses_only_observed_returns_and_forward_target():
    candles = _fake_candles()
    dataset = model.build_dataset(candles, horizon=5)
    index = dataset.index[0]
    positions = {pd.to_datetime(candle["time"], unit="s", utc=True): candle["close"] for candle in candles}
    dates = list(positions)
    position = dates.index(index)

    expected_lag_one = np.log(positions[dates[position - 1]] / positions[dates[position - 2]])
    expected_target = np.log(positions[dates[position + 5]] / positions[index])
    assert np.isclose(dataset.loc[index, "retorno_rezagado_1"], expected_lag_one)
    assert np.isclose(dataset.loc[index, "objetivo"], expected_target)
    assert set(dataset.columns) == {*model.FEATURES, "objetivo"}


def test_train_regression_splits_chronologically_and_builds_pipelines(monkeypatch):
    monkeypatch.setattr(model.market_data, "get_candles", lambda *args, **kwargs: _fake_candles())

    result = model.train_regression("fake", period="5y", horizon=5)

    assert result["ticker"] == "FAKE"
    assert result["train"].index[-1] < result["test"].index[0]
    assert len(result["train"]) == result["n_train"]
    assert len(result["test"]) == result["n_test"]
    assert set(result["modelos"]) == {
        "LinearRegression",
        "Ridge",
        "RandomForestRegressor",
        "GradientBoostingRegressor",
    }
    for fitted in result["modelos"].values():
        assert isinstance(fitted["estimador"], Pipeline)
        assert set(fitted["metricas"]["test"]) == {
            "mae",
            "rmse",
            "r2",
            "acierto_direccional",
            "mae_vs_paseo_aleatorio",
        }


def test_train_regression_uses_market_data_boundary(monkeypatch):
    calls = []

    def fake_get_candles(ticker, **kwargs):
        calls.append((ticker, kwargs))
        return _fake_candles()

    monkeypatch.setattr(model.market_data, "get_candles", fake_get_candles)
    model.train_regression("FAKE", period="2y", horizon=3)

    assert calls == [("FAKE", {"range_": "2y", "interval": "1d"})]


def test_tracking_logs_runs_metrics_artifacts_and_registered_models(monkeypatch, tmp_path):
    import mlflow

    from app.regresion import tracking

    monkeypatch.setattr(model.market_data, "get_candles", lambda *args, **kwargs: _fake_candles())
    result = model.train_regression("FAKE", horizon=5)

    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artifact_location = tmp_path / "mlartifacts"
    tracked = tracking.log_training_runs(
        result,
        tracking_uri=tracking_uri,
        artifact_location=artifact_location,
    )
    client = mlflow.MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name(tracking.EXPERIMENT_NAME)
    runs = client.search_runs([experiment.experiment_id])

    assert len(tracked) == len(result["modelos"]) == len(runs)
    assert all("drift_psi" in run.data.metrics for run in runs)
    assert all("drift_alert" in run.data.tags for run in runs)
    assert all({"drift_predicciones.png", "predicciones.csv"} <= set(client.list_artifacts(run.info.run_id)[i].path for i in range(2)) for run in runs)
    assert client.get_registered_model("moainvest-regresion-FAKE").name == "moainvest-regresion-FAKE"
    assert experiment.artifact_location == artifact_location.resolve().as_uri()
    assert all(
        Path(run.info.artifact_uri.removeprefix("file://")).is_relative_to(artifact_location.resolve())
        for run in runs
    )