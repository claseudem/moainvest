"""Datos del Pronosticador: cierres diarios del SPY.

1. MotherDuck (preferente, solo lectura): tabla ``raw_spy_daily`` de la base
   ``Config.MOTHERDUCK_DATABASE`` (``riesgo_olap``), con el token
   ``Config.MOTHER_DUCK_TOKEN``. Trae también la auditoría ``audit_pipeline_runs``.
2. Yahoo Finance (respaldo): si MotherDuck no tiene los datos (sin token, sin
   base o sin tabla), se descargan los cierres diarios de
   ``Config.PRONOSTICADOR_TICKER`` (SPY) con ``core.market_data``.

Si ninguna fuente responde se lanza ``DatosNoDisponibles`` con un mensaje apto
para mostrar en la página.
"""
from __future__ import annotations

import re

import duckdb
import pandas as pd
from flask import current_app

from app.core import market_data

PRICES_TABLE = "raw_spy_daily"
AUDIT_TABLE = "audit_pipeline_runs"

FUENTE_MOTHERDUCK = "MotherDuck"
FUENTE_YAHOO = "Yahoo Finance"

# Con menos cierres el AR-GARCH no es fiable (ni suele converger).
MIN_CIERRES = 250

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatosNoDisponibles(RuntimeError):
    """No se pueden leer los datos de MotherDuck; el mensaje va al usuario."""


def get_connection() -> duckdb.DuckDBPyConnection:
    token = current_app.config.get("MOTHER_DUCK_TOKEN", "")
    database = current_app.config.get("MOTHERDUCK_DATABASE", "riesgo_olap")
    if not token:
        raise DatosNoDisponibles(
            "Falta configurar MOTHER_DUCK_TOKEN en el .env: sin él no se pueden leer los datos de MotherDuck."
        )
    if not _IDENTIFIER_RE.match(database):
        raise DatosNoDisponibles(f"MOTHERDUCK_DATABASE='{database}' no es un nombre de base válido.")
    try:
        # El token va en ``config`` y no en la cadena de conexión, para que no
        # aparezca en trazas ni logs.
        return duckdb.connect(f"md:{database}", config={"motherduck_token": token})
    except duckdb.Error as exc:
        if "no database/share named" in str(exc):
            raise DatosNoDisponibles(
                f"La base '{database}' no existe en tu cuenta de MotherDuck. Créala y carga la tabla "
                f"'{PRICES_TABLE}', o apunta MOTHERDUCK_DATABASE a la base que la contenga."
            ) from exc
        raise DatosNoDisponibles(f"No se pudo conectar a la base '{database}' de MotherDuck: {exc}") from exc


def cargar_datos() -> tuple[pd.DataFrame, list[dict], str]:
    """``(cierres, auditoría, fuente)``: MotherDuck si tiene la tabla y, si no, Yahoo Finance."""
    try:
        df, audit = cargar_de_motherduck()
        return df, audit, FUENTE_MOTHERDUCK
    except DatosNoDisponibles as motherduck_exc:
        current_app.logger.info("Pronosticador: %s Se usa Yahoo Finance.", motherduck_exc)
        try:
            return cargar_de_yahoo(), [], FUENTE_YAHOO
        except DatosNoDisponibles as yahoo_exc:
            raise DatosNoDisponibles(f"{motherduck_exc} Tampoco se pudo usar Yahoo Finance: {yahoo_exc}") from yahoo_exc


def cargar_de_yahoo() -> pd.DataFrame:
    """Cierres diarios del ticker del Pronosticador (por defecto SPY, 10 años) desde Yahoo Finance."""
    ticker = current_app.config.get("PRONOSTICADOR_TICKER", "SPY")
    period = current_app.config.get("PRONOSTICADOR_YAHOO_PERIOD", "10y")
    try:
        candles = market_data.get_candles(ticker, period, "1d")
    except Exception as exc:  # noqa: BLE001 — yfinance lanza errores de red muy variados
        raise DatosNoDisponibles(f"error descargando {ticker} ({exc}).") from exc
    if len(candles) < MIN_CIERRES:
        raise DatosNoDisponibles(
            f"Yahoo Finance devolvió {len(candles)} cierres diarios de {ticker}; hacen falta al menos {MIN_CIERRES}."
        )
    df = pd.DataFrame(
        {"Close": [c["close"] for c in candles]},
        index=pd.DatetimeIndex(pd.to_datetime([c["time"] for c in candles], unit="s").normalize(), name="Date"),
    )
    return df[~df.index.duplicated(keep="last")]


def cargar_de_motherduck(tabla: str = PRICES_TABLE) -> tuple[pd.DataFrame, list[dict]]:
    """Cierres diarios (índice ``Date``, columna ``Close``) y últimas corridas auditadas."""
    con = get_connection()
    try:
        try:
            df = con.execute(f"SELECT Date, Close FROM {tabla} ORDER BY Date ASC").df()
        except duckdb.CatalogException as exc:
            database = current_app.config.get("MOTHERDUCK_DATABASE", "riesgo_olap")
            raise DatosNoDisponibles(
                f"La tabla '{tabla}' no existe en la base '{database}' de MotherDuck. "
                "Cárgala antes de usar el Pronosticador."
            ) from exc
        except duckdb.Error as exc:
            raise DatosNoDisponibles(f"Error leyendo '{tabla}' en MotherDuck: {exc}") from exc

        try:
            audit = con.execute(
                f"SELECT run_timestamp, status, r_squared, var_95, var_99, precio_esperado "
                f"FROM {AUDIT_TABLE} ORDER BY run_timestamp DESC LIMIT 6"
            ).df()
            audit_records = audit.to_dict(orient="records")
        except duckdb.Error:
            # La auditoría es opcional: si la tabla no existe, la sección queda vacía.
            audit_records = []
    finally:
        con.close()

    if df.empty:
        raise DatosNoDisponibles(f"La tabla '{tabla}' de MotherDuck está vacía.")

    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date"), audit_records
