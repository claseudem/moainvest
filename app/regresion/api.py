"""API para entrenar modelos y obtener sus métricas de evaluación y drift."""
from __future__ import annotations

import base64
import re

from flask import Blueprint, jsonify, request

from app.regresion import model, tracking

bp = Blueprint("regresion_api", __name__, url_prefix="/api")
PERIODS = {"1y", "2y", "5y", "max"}
TICKER_PATTERN = re.compile(r"[A-Z0-9.^=\-]{1,20}")


@bp.post("/regression/train")
def train():
    payload = request.get_json(silent=True) or request.form
    ticker = str(payload.get("ticker", "")).strip().upper()
    period = str(payload.get("period", "5y"))
    try:
        horizon = int(payload.get("horizon", 5))
    except (TypeError, ValueError):
        return jsonify({"error": "El horizonte debe ser un entero entre 1 y 60"}), 400

    if not TICKER_PATTERN.fullmatch(ticker):
        return jsonify({"error": "Ticker inválido"}), 400
    if period not in PERIODS:
        return jsonify({"error": "Periodo inválido"}), 400
    if not 1 <= horizon <= 60:
        return jsonify({"error": "El horizonte debe estar entre 1 y 60"}), 400

    try:
        result = model.train_regression(ticker, period=period, horizon=horizon)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    tracked = tracking.log_training_runs(result)

    rows = []
    for name, fitted in result["modelos"].items():
        drift_result = tracked[name]
        rows.append(
            {
                "modelo": name,
                "train": fitted["metricas"]["train"],
                "test": fitted["metricas"]["test"],
                "drift": drift_result["predicciones"],
                "alerta_drift": drift_result["drift_alert"],
                "grafico": "data:image/png;base64," + base64.b64encode(drift_result["grafico"]).decode("ascii"),
            }
        )
    for name, benchmark in result["benchmarks"].items():
        rows.append(
            {
                "modelo": name,
                "train": benchmark["metricas"]["train"],
                "test": benchmark["metricas"]["test"],
                "drift": None,
                "alerta_drift": False,
                "grafico": None,
            }
        )

    return jsonify(
        {
            "ticker": result["ticker"],
            "periodo": result["periodo"],
            "horizonte": result["horizonte"],
            "n_train": result["n_train"],
            "n_test": result["n_test"],
            "resultados": rows,
            "drift_features": tracked[next(iter(result["modelos"]))]["features"],
        }
    )