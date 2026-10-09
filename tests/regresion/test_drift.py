import numpy as np
import pandas as pd

from app.regresion import drift


def test_compare_distributions_uses_train_quantiles_and_detects_shift():
    result = drift.compare_distributions(np.arange(100), np.arange(100, 200))

    assert result["ks"] == 1.0
    assert result["p_value"] < 0.01
    assert result["psi"] > 0.2


def test_feature_drift_reports_each_feature():
    train = pd.DataFrame({"x": np.arange(40), "y": np.ones(40)})
    test = pd.DataFrame({"x": np.arange(40, 60), "y": np.ones(20)})

    result = drift.feature_drift(train, test, ["x", "y"])

    assert set(result) == {"x", "y"}
    assert result["x"]["psi"] > result["y"]["psi"]


def test_render_prediction_drift_returns_png_without_changing_global_theme():
    import matplotlib

    before = dict(matplotlib.rcParams)
    png = drift.render_prediction_drift(np.arange(30), np.arange(30) + 1)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert dict(matplotlib.rcParams) == before