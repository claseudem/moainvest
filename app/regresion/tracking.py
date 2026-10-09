"""Registro de experimentos de regresión con MLflow local."""
from __future__ import annotations

import tempfile
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature

from app.regresion import drift
from config import Config

EXPERIMENT_NAME = "moainvest-regresion"
DEFAULT_TRACKING_URI = Config.MLFLOW_TRACKING_URI
DEFAULT_ARTIFACT_LOCATION = Path("mlartifacts").resolve().as_uri()


def _model_metrics(metrics: dict, prefix: str = "") -> dict[str, float]:
    return {f"{prefix}{name}": float(value) for name, value in metrics.items()}


def log_training_runs(
    result: dict,
    tracking_uri: str | Path | None = None,
    artifact_location: str | Path | None = None,
) -> dict[str, dict]:
    """Registra un run por estimador, artefactos, métricas y modelo versionado."""
    mlflow.set_tracking_uri(str(tracking_uri or DEFAULT_TRACKING_URI))
    if mlflow.get_experiment_by_name(EXPERIMENT_NAME) is None:
        location = Path(artifact_location).resolve().as_uri() if artifact_location else DEFAULT_ARTIFACT_LOCATION
        mlflow.create_experiment(EXPERIMENT_NAME, artifact_location=location)
    mlflow.set_experiment(EXPERIMENT_NAME)
    feature_names = result["features"]
    drift_by_model = {}

    for name, fitted in result["modelos"].items():
        train_predictions = fitted["predicciones"]["train"]
        test_predictions = fitted["predicciones"]["test"]
        prediction_stats = drift.prediction_drift(train_predictions, test_predictions)
        feature_stats = drift.feature_drift(result["train"], result["test"], feature_names)
        chart = drift.render_prediction_drift(train_predictions, test_predictions)

        estimator = fitted["estimador"]
        estimator_params = estimator.named_steps["modelo"].get_params(deep=True)
        params = {
            "ticker": result["ticker"],
            "periodo": result["periodo"],
            "horizonte": result["horizonte"],
            "modelo": name,
            "n_train": result["n_train"],
            "n_test": result["n_test"],
            **{f"hiperparametro_{key}": value for key, value in estimator_params.items()},
        }
        metrics = {}
        for split, split_metrics in fitted["metricas"].items():
            metrics.update(_model_metrics(split_metrics, f"{split}_"))
        for benchmark_name, benchmark in result["benchmarks"].items():
            benchmark_key = "paseo_aleatorio" if benchmark_name == "Paseo aleatorio" else "paseo_con_deriva"
            for split, split_metrics in benchmark["metricas"].items():
                metrics.update(_model_metrics(split_metrics, f"{benchmark_key}_{split}_"))
        metrics.update(
            {
                "drift_ks": prediction_stats["ks"],
                "drift_p_value": prediction_stats["p_value"],
                "drift_psi": prediction_stats["psi"],
            }
        )
        for feature, stats in feature_stats.items():
            metrics[f"feature_drift_{feature}_ks"] = stats["ks"]
            metrics[f"feature_drift_{feature}_p_value"] = stats["p_value"]
            metrics[f"feature_drift_{feature}_psi"] = stats["psi"]

        model_input = result["train"].loc[:, feature_names].iloc[:5]
        signature = infer_signature(model_input, estimator.predict(model_input))
        csv_rows = []
        for split in ("train", "test"):
            frame = result[split]
            csv_rows.append(
                pd.DataFrame(
                    {
                        "fecha": frame.index,
                        "particion": split,
                        "real": frame["objetivo"].to_numpy(),
                        "prediccion": fitted["predicciones"][split],
                    }
                )
            )
        predictions_csv = pd.concat(csv_rows, ignore_index=True)

        with mlflow.start_run(run_name=f"{result['ticker']}-{name}") as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            mlflow.set_tag("drift_alert", "true" if prediction_stats["psi"] > 0.2 else "false")
            with tempfile.TemporaryDirectory() as temp_dir:
                chart_path = Path(temp_dir) / "drift_predicciones.png"
                csv_path = Path(temp_dir) / "predicciones.csv"
                chart_path.write_bytes(chart)
                predictions_csv.to_csv(csv_path, index=False)
                mlflow.log_artifact(str(chart_path))
                mlflow.log_artifact(str(csv_path))
            mlflow.sklearn.log_model(
                estimator,
                name="modelo",
                serialization_format="cloudpickle",
                signature=signature,
                input_example=model_input,
                registered_model_name=f"moainvest-regresion-{result['ticker']}",
            )

            drift_by_model[name] = {
                "predicciones": prediction_stats,
                "features": feature_stats,
                "grafico": chart,
                "run_id": run.info.run_id,
                "drift_alert": prediction_stats["psi"] > 0.2,
            }

    return drift_by_model