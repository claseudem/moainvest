"""Pruebas de drift de predicciones y variables, sin dependencias de Flask."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from app.core.charts import PALETTE, MPL_RC


def compare_distributions(reference, current, bins: int = 10) -> dict[str, float]:
    """Compara dos muestras con KS y PSI; los cortes PSI salen de train."""
    reference_values = np.asarray(reference, dtype=float)
    current_values = np.asarray(current, dtype=float)
    reference_values = reference_values[np.isfinite(reference_values)]
    current_values = current_values[np.isfinite(current_values)]
    if not len(reference_values) or not len(current_values):
        raise ValueError("KS y PSI requieren dos muestras no vacías")

    ks = ks_2samp(reference_values, current_values, alternative="two-sided", method="auto")
    quantiles = np.quantile(reference_values, np.linspace(0, 1, bins + 1))
    edges = np.unique(quantiles[1:-1])
    edges = np.concatenate(([-np.inf], edges, [np.inf]))
    expected = np.histogram(reference_values, bins=edges)[0].astype(float)
    observed = np.histogram(current_values, bins=edges)[0].astype(float)
    expected /= expected.sum()
    observed /= observed.sum()
    epsilon = 1e-6
    expected = np.clip(expected, epsilon, None)
    observed = np.clip(observed, epsilon, None)
    expected /= expected.sum()
    observed /= observed.sum()
    psi = float(np.sum((observed - expected) * np.log(observed / expected)))
    return {"ks": float(ks.statistic), "p_value": float(ks.pvalue), "psi": psi}


def prediction_drift(train_predictions, test_predictions) -> dict[str, float]:
    """Drift entre las predicciones fuera de muestra y las de entrenamiento."""
    return compare_distributions(train_predictions, test_predictions, bins=10)


def feature_drift(train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict[str, dict[str, float]]:
    """Calcula KS y PSI por feature usando los cuantiles de train como bins."""
    return {
        feature: compare_distributions(train[feature], test[feature], bins=10)
        for feature in features
    }


def render_prediction_drift(train_predictions, test_predictions) -> bytes:
    """Histograma PNG superpuesto de predicciones de train y test."""
    with plt.rc_context(MPL_RC):
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        ax.hist(
            train_predictions,
            bins=20,
            density=True,
            alpha=0.48,
            color=PALETTE[0],
            label="Train",
        )
        ax.hist(
            test_predictions,
            bins=20,
            density=True,
            alpha=0.48,
            color=PALETTE[1],
            label="Test",
        )
        ax.set_title("Drift de predicciones", loc="left")
        ax.set_xlabel("Retorno logarítmico predicho")
        ax.set_ylabel("Densidad")
        ax.legend()
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=120)
        plt.close(fig)
    return buffer.getvalue()