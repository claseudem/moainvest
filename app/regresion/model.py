"""Preparación temporal y entrenamiento de modelos de regresión."""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.core import market_data

FEATURES = (
    "retorno_rezagado_1",
    "retorno_rezagado_2",
    "retorno_rezagado_3",
    "retorno_rezagado_5",
    "retorno_rezagado_10",
    "volatilidad_20d",
    "volatilidad_60d",
    "rsi_14",
    "distancia_sma_50",
    "distancia_sma_200",
    "dia_semana",
)

MODEL_FACTORIES: dict[str, Callable[[], object]] = {
    "LinearRegression": LinearRegression,
    "Ridge": lambda: Ridge(alpha=1.0),
    "RandomForestRegressor": lambda: RandomForestRegressor(
        n_estimators=100, max_depth=5, min_samples_leaf=3, random_state=42, n_jobs=1
    ),
    "GradientBoostingRegressor": lambda: GradientBoostingRegressor(
        n_estimators=100, max_depth=2, learning_rate=0.05, random_state=42
    ),
}


def build_dataset(candles: list[dict], horizon: int = 5) -> pd.DataFrame:
    """Construye objetivo y features conocidos al cierre de cada fecha."""
    if horizon < 1:
        raise ValueError("El horizonte debe ser al menos 1 día hábil")
    if not candles:
        return pd.DataFrame(columns=[*FEATURES, "objetivo"])

    prices = pd.DataFrame(candles)
    prices["fecha"] = pd.to_datetime(prices["time"], unit="s", utc=True)
    prices = prices.drop_duplicates("fecha").set_index("fecha").sort_index()
    closes = pd.to_numeric(prices["close"], errors="coerce").astype(float)
    log_prices = np.log(closes.where(closes > 0))
    returns = log_prices.diff()

    features = pd.DataFrame(index=prices.index)
    for lag in (1, 2, 3, 5, 10):
        features[f"retorno_rezagado_{lag}"] = returns.shift(lag)
    features["volatilidad_20d"] = returns.rolling(20).std()
    features["volatilidad_60d"] = returns.rolling(60).std()

    delta = closes.diff()
    gains = delta.clip(lower=0).rolling(14).mean()
    losses = -delta.clip(upper=0).rolling(14).mean()
    relative_strength = gains / losses.replace(0, np.nan)
    rsi = 100 - 100 / (1 + relative_strength)
    features["rsi_14"] = rsi.fillna(100).where(gains.notna(), np.nan)

    features["distancia_sma_50"] = closes / closes.rolling(50).mean() - 1
    features["distancia_sma_200"] = closes / closes.rolling(200).mean() - 1
    features["dia_semana"] = prices.index.dayofweek.astype(float)
    features["objetivo"] = log_prices.shift(-horizon) - log_prices

    return features.replace([np.inf, -np.inf], np.nan).dropna(subset=[*FEATURES, "objetivo"])


def _metrics(actual: np.ndarray, predicted: np.ndarray, random_walk_mae: float) -> dict[str, float]:
    mae = float(mean_absolute_error(actual, predicted))
    rmse = float(np.sqrt(mean_squared_error(actual, predicted)))
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": float(r2_score(actual, predicted)),
        "acierto_direccional": float(np.mean(np.sign(actual) == np.sign(predicted))),
        "mae_vs_paseo_aleatorio": mae / max(random_walk_mae, np.finfo(float).eps),
    }


def train_regression(ticker: str, period: str = "5y", horizon: int = 5) -> dict:
    """Entrena cuatro modelos y los compara con dos paseos de referencia."""
    if horizon < 1:
        raise ValueError("El horizonte debe ser al menos 1 día hábil")
    candles = market_data.get_candles(ticker, range_=period, interval="1d")
    dataset = build_dataset(candles, horizon)
    if len(dataset) < max(20, horizon + 3):
        raise ValueError("No hay suficientes datos para crear train y test")

    boundary = int(len(dataset) * 0.8)
    train_end = boundary - horizon
    train_frame = dataset.iloc[:train_end]
    test_frame = dataset.iloc[boundary:]
    if len(train_frame) < 2 or len(test_frame) < 2:
        raise ValueError("No hay suficientes observaciones en train o test")

    x_train = train_frame.loc[:, FEATURES]
    x_test = test_frame.loc[:, FEATURES]
    y_train = train_frame["objetivo"].to_numpy()
    y_test = test_frame["objetivo"].to_numpy()
    random_walk = {"train": np.zeros(len(y_train)), "test": np.zeros(len(y_test))}
    drift_value = float(y_train.mean())
    drift = {"train": np.full(len(y_train), drift_value), "test": np.full(len(y_test), drift_value)}
    actual = {"train": y_train, "test": y_test}

    benchmarks = {}
    for name, predictions in (("Paseo aleatorio", random_walk), ("Paseo con deriva", drift)):
        benchmarks[name] = {
            "predicciones": predictions,
            "metricas": {
                split: _metrics(actual[split], predictions[split], float(mean_absolute_error(actual[split], random_walk[split])))
                for split in ("train", "test")
            },
        }

    models = {}
    for name, factory in MODEL_FACTORIES.items():
        estimator = Pipeline([("escalador", StandardScaler()), ("modelo", factory())])
        estimator.fit(x_train, y_train)
        predictions = {
            "train": estimator.predict(x_train),
            "test": estimator.predict(x_test),
        }
        models[name] = {
            "estimador": estimator,
            "predicciones": predictions,
            "metricas": {
                split: _metrics(
                    actual[split],
                    predictions[split],
                    benchmarks["Paseo aleatorio"]["metricas"][split]["mae"],
                )
                for split in ("train", "test")
            },
        }

    return {
        "ticker": ticker.upper(),
        "periodo": period,
        "horizonte": horizon,
        "features": list(FEATURES),
        "train": train_frame,
        "test": test_frame,
        "modelos": models,
        "benchmarks": benchmarks,
        "n_train": len(train_frame),
        "n_test": len(test_frame),
    }