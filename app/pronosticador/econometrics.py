"""Modelo AR(p)-GARCH(1,1) del Pronosticador sobre los retornos diarios del SPY.

1. AR(p) por MCO con errores robustos Newey-West (HAC) para la media.
2. GARCH(1,1) sobre sus residuos para la volatilidad condicional.
3. Con la previsión a t+1: VaR/CVaR paramétricos (normal), precio esperado,
   Monte Carlo, backtest de dirección, ADF, cointegración y un semáforo.

Las funciones reciben el ``DataFrame`` de cierres (ver ``db.cargar_datos``),
así que no tocan la red y se pueden probar con datos sintéticos.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from arch import arch_model
from flask import current_app
from scipy.stats import norm
from statsmodels.tsa.stattools import adfuller, coint

log = logging.getLogger(__name__)

EXPERIMENT_NAME = "spy_sp500_riesgo_garch"
ALLOWED_LAGS = (1, 2, 3, 4, 5)
DEFAULT_LAGS = 3


def preparar_features(df: pd.DataFrame, lags: int = DEFAULT_LAGS) -> pd.DataFrame:
    data = df.copy()
    data["log_return"] = np.log(data["Close"] / data["Close"].shift(1))
    for i in range(1, lags + 1):
        data[f"lag_{i}"] = data["log_return"].shift(i)
    return data.dropna()


def entrenar_modelo_completo(df_raw: pd.DataFrame, lags: int = DEFAULT_LAGS) -> tuple[Any, Any, dict[str, float]]:
    """Ajusta AR(p)-GARCH(1,1) y devuelve ``(modelo_ar, res_garch, metricas)``."""
    data = preparar_features(df_raw, lags=lags)
    feature_cols = [f"lag_{i}" for i in range(1, lags + 1)]
    X = sm.add_constant(data[feature_cols])
    y = data["log_return"]

    # 1. AR(p) con errores estándar robustos Newey-West (HAC)
    modelo_ar = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})

    # 2. GARCH(1,1) sobre los residuos (en %, para que el optimizador converja)
    garch = arch_model(modelo_ar.resid * 100.0, p=1, q=1, mean="Zero", vol="GARCH", dist="normal")
    res_garch = garch.fit(disp="off")
    var_cond_pct = res_garch.forecast(horizon=1).variance.iloc[-1, 0]
    sigma_t1 = float(np.sqrt(var_cond_pct) / 100.0)

    # Retorno t+1: el retorno de hoy pasa a ser lag_1, lag_1 pasa a lag_2...
    ultimos_lags = data.iloc[-1][feature_cols].to_numpy()
    vector_pred = [1.0, data.iloc[-1]["log_return"], *ultimos_lags[:-1]]
    mu_t1 = float(modelo_ar.predict(np.array(vector_pred).reshape(1, -1))[0])

    # 3. VaR y CVaR (Expected Shortfall) paramétricos a 1 día
    z_95, z_99 = norm.ppf(0.95), norm.ppf(0.99)
    var_95 = float(-(mu_t1 - z_95 * sigma_t1))
    var_99 = float(-(mu_t1 - z_99 * sigma_t1))
    cvar_95 = float(-(mu_t1 - sigma_t1 * (norm.pdf(z_95) / 0.05)))
    cvar_99 = float(-(mu_t1 - sigma_t1 * (norm.pdf(z_99) / 0.01)))

    ultimo_cierre = float(df_raw["Close"].iloc[-1])
    metricas = {
        "r_squared": float(modelo_ar.rsquared),
        "aic": float(modelo_ar.aic),
        "mu_t1": mu_t1,
        "sigma_t1": sigma_t1,
        "var_95": var_95,
        "var_99": var_99,
        "cvar_95": cvar_95,
        "cvar_99": cvar_99,
        "ultimo_cierre": ultimo_cierre,
        "precio_esperado_t1": float(ultimo_cierre * np.exp(mu_t1)),
    }

    registrar_en_mlflow(
        params={"lags_ar": lags, "vol_model": "GARCH(1,1)"},
        metrics={
            "ar_r_squared": metricas["r_squared"],
            "ar_aic": metricas["aic"],
            "garch_aic": float(res_garch.aic),
            "sigma_t1_anualizada": float(sigma_t1 * np.sqrt(252)),
            "var_95": var_95,
            "var_99": var_99,
            "cvar_95": cvar_95,
            "cvar_99": cvar_99,
        },
    )
    return modelo_ar, res_garch, metricas


def registrar_en_mlflow(params: dict[str, Any], metrics: dict[str, float]) -> bool:
    """Registra la corrida en MLflow si hay ``MLFLOW_TRACKING_URI``.

    Es opcional y nunca rompe el entrenamiento: sin URI no hace nada y si el
    servidor no responde lo deja en el log. Devuelve si se llegó a registrar.
    """
    uri = current_app.config.get("MLFLOW_TRACKING_URI", "")
    if not uri:
        return False
    # Sin esto, MLflow reintenta durante minutos contra un servidor caído.
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
    try:
        import mlflow

        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(EXPERIMENT_NAME)
        with mlflow.start_run():
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
        return True
    except Exception:  # noqa: BLE001 — el tracking es best-effort
        log.warning("No se pudo registrar la corrida en MLflow (%s)", uri, exc_info=True)
        return False


def _decision(tasa_acierto: float, mu_t1: float, prob_ganancia: float, var_95: float) -> tuple[str, str, str]:
    if tasa_acierto >= 52.0 and mu_t1 > 0 and prob_ganancia >= 50.0:
        return (
            "Invertir (compra fuerte)",
            "green",
            f"Tendencia estocástica favorable ({tasa_acierto:.1f}% de acierto histórico), deriva positiva "
            f"y {prob_ganancia:.1f}% de trayectorias en ganancia.",
        )
    if prob_ganancia >= 48.0 and var_95 < 0.008:
        return (
            "Mantener / cautela",
            "yellow",
            f"Mercado en equilibrio o deriva neutra. Volatilidad controlada (VaR 95% = {var_95 * 100:.2f}%); "
            "se recomienda operar con coberturas.",
        )
    return (
        "No invertir (alto riesgo / venta)",
        "red",
        "Riesgo de cola asimétrico desfavorable: pérdida esperada superior a la ganancia prevista "
        "o tasa de acierto subóptima.",
    )


def _json_safe(value: Any) -> Any:
    """Fechas a ISO y NaN/inf a ``None`` para que el JSON sea válido."""
    if isinstance(value, pd.Timestamp | np.datetime64):
        return pd.Timestamp(value).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def calcular_analisis_avanzado(
    df_raw: pd.DataFrame,
    audit_records: list[dict] | None = None,
    lags: int = DEFAULT_LAGS,
    num_simulaciones: int = 150,
    dias_proy: int = 15,
    seed: int = 42,
) -> dict[str, Any]:
    """Todo lo que pinta el dashboard: métricas, semáforo, Monte Carlo y gráficos."""
    rng = np.random.default_rng(seed)
    data = preparar_features(df_raw, lags=lags)
    ar_model, res_garch, metricas = entrenar_modelo_completo(df_raw, lags=lags)

    # 1. Backtest de acierto de dirección (signo previsto = signo real)
    X = sm.add_constant(data[[f"lag_{i}" for i in range(1, lags + 1)]], has_constant="add")
    pred_ret = ar_model.predict(X)
    tasa_acierto = float(np.mean(np.sign(pred_ret) == np.sign(data["log_return"])) * 100.0)

    # 2. ADF sobre retornos y cointegración contra un paseo aleatorio de referencia
    adf_pval = float(adfuller(data["log_return"], result_object=False)[1])
    benchmark = np.cumsum(rng.normal(0.0001, 0.003, size=len(df_raw))) + df_raw["Close"].iloc[0]
    _, coint_pval, _ = coint(df_raw["Close"].to_numpy(), benchmark)

    # 3. Volatilidad condicional GARCH anualizada (%), últimos 60 días
    vol_anual = (res_garch.conditional_volatility / 100.0) * np.sqrt(252) * 100.0

    # 4. Monte Carlo de precios con la media y sigma previstas
    s0 = metricas["ultimo_cierre"]
    shocks = rng.normal(metricas["mu_t1"], metricas["sigma_t1"], size=(num_simulaciones, dias_proy))
    trayectorias = s0 * np.exp(np.cumsum(shocks, axis=1))
    prob_ganancia = float(np.mean(trayectorias[:, -1] > s0) * 100.0)

    decision, decision_color, decision_desc = _decision(
        tasa_acierto, metricas["mu_t1"], prob_ganancia, metricas["var_95"]
    )

    return {
        "lags": lags,
        "metricas": metricas,
        "tasa_acierto": tasa_acierto,
        "coint_pval": _json_safe(float(coint_pval)),
        "adf_pval": _json_safe(adf_pval),
        "prob_ganancia": prob_ganancia,
        "decision": decision,
        "decision_color": decision_color,
        "decision_desc": decision_desc,
        "retornos_hist": (data["log_return"] * 100.0).round(5).tolist(),
        "garch_vol": {
            "fechas": [d.strftime("%Y-%m-%d") for d in data.index[-60:]],
            "valores": [float(v) for v in vol_anual.iloc[-60:]],
        },
        "montecarlo": {
            "dias": list(range(1, dias_proy + 1)),
            "trayectorias": trayectorias[:25].tolist(),
            "s0": s0,
        },
        "historico": {
            "fechas": [d.strftime("%Y-%m-%d") for d in df_raw.index[-60:]],
            "precios": [float(p) for p in df_raw["Close"].iloc[-60:]],
        },
        "audit_records": [{k: _json_safe(v) for k, v in r.items()} for r in (audit_records or [])],
    }
