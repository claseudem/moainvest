"""API JSON del Pronosticador (bajo /app/pronosticador, así hereda el login de AUTH_REQUIRED).

- ``GET  /api/dashboard-data?lags=3``  todo lo que pinta el dashboard
- ``POST /train``  {"lags": 3}          re-estima el modelo y lo guarda en memoria
- ``GET  /predict``                     métricas del último modelo (lo entrena si no hay)

Los datos salen de MotherDuck (``raw_spy_daily``) o, si no los tiene, de Yahoo
Finance (ver ``db.cargar_datos``); ``fuente`` indica cuál se usó. Si ninguna
responde, 503 con ``{"error": "<mensaje>"}`` que la página muestra tal cual.
"""
from __future__ import annotations

from threading import Lock
from typing import Any

from flask import Blueprint, jsonify, request

from app.pronosticador import db, econometrics
from app.pronosticador.db import DatosNoDisponibles
from app.pronosticador.econometrics import ALLOWED_LAGS, DEFAULT_LAGS

bp = Blueprint("pronosticador_api", __name__, url_prefix="/app/pronosticador")

# Último modelo entrenado en este proceso (lo usa /predict).
_ESTADO_MODELO: dict[str, Any] = {"ar": None, "garch": None, "metricas": None}
_lock = Lock()


def _parse_lags(raw) -> int | None:
    try:
        lags = int(raw if raw is not None else DEFAULT_LAGS)
    except (TypeError, ValueError):
        return None
    return lags if lags in ALLOWED_LAGS else None


def _bad_lags():
    return jsonify({"error": f"lags debe ser uno de {list(ALLOWED_LAGS)}"}), 400


def _unavailable(exc: DatosNoDisponibles):
    return jsonify({"error": str(exc)}), 503


def _entrenar(lags: int) -> dict[str, Any]:
    df, _, fuente = db.cargar_datos()
    ar, garch, metricas = econometrics.entrenar_modelo_completo(df, lags=lags)
    metricas = {**metricas, "fuente": fuente}
    with _lock:
        _ESTADO_MODELO.update(ar=ar, garch=garch, metricas=metricas)
    return metricas


@bp.get("/api/dashboard-data")
def dashboard_data():
    lags = _parse_lags(request.args.get("lags"))
    if lags is None:
        return _bad_lags()
    try:
        df, audit, fuente = db.cargar_datos()
    except DatosNoDisponibles as exc:
        return _unavailable(exc)
    return jsonify({**econometrics.calcular_analisis_avanzado(df, audit, lags=lags), "fuente": fuente})


@bp.post("/train")
def train():
    lags = _parse_lags((request.get_json(silent=True) or {}).get("lags"))
    if lags is None:
        return _bad_lags()
    try:
        metricas = _entrenar(lags)
    except DatosNoDisponibles as exc:
        return _unavailable(exc)
    return jsonify({"status": "ok", "lags": lags, "metricas": metricas})


@bp.get("/predict")
def predict():
    metricas = _ESTADO_MODELO["metricas"]
    if metricas is None:
        try:
            metricas = _entrenar(DEFAULT_LAGS)
        except DatosNoDisponibles as exc:
            return _unavailable(exc)
    return jsonify(metricas)
