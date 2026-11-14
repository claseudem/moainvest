"""Flujo Prefect: favoritos (InsForge) -> precios diarios (yfinance) -> MotherDuck.

Uso:
    uv run data/main.py              # deja el flujo corriendo cada INTERVALO_SEGUNDOS
    uv run data/main.py --una-vez    # ejecuta una sola vez (útil para probar)

Variables del ``.env`` de la raíz: INSFORGE_URL, INSFORGE_API_KEY y MOTHER_DUCK_TOKEN.
La tabla ``precios_diarios`` de MotherDuck tiene una fila por (ticker, fecha);
las ejecuciones siguientes solo descargan lo nuevo y actualizan los últimos días.
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

import duckdb
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv
from prefect import flow, task

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_USER_ID = "cdff3ae8-a21a-4eed-8d39-1db6d1e4090e"
TABLE = "activos_favoritos"
INTERVALO_SEGUNDOS = 30

MD_DATABASE = "moainvest"
MD_TABLE = "precios_diarios"
HISTORIAL_INICIAL = "5y"  # primera descarga de un ticker nuevo
SOLAPE_DIAS = 5  # se vuelven a bajar los últimos días para corregir cierres provisionales


def _conectar_motherduck() -> duckdb.DuckDBPyConnection:
    token = os.environ.get("MOTHER_DUCK_TOKEN", "")
    if not token:
        raise RuntimeError("Falta MOTHER_DUCK_TOKEN en el .env.")
    os.environ["motherduck_token"] = token  # nombre que espera el cliente de DuckDB
    con = duckdb.connect("md:")
    con.execute(f"CREATE DATABASE IF NOT EXISTS {MD_DATABASE}")
    con.execute(f"USE {MD_DATABASE}")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MD_TABLE} (
            ticker VARCHAR NOT NULL,
            fecha DATE NOT NULL,
            apertura DOUBLE,
            maximo DOUBLE,
            minimo DOUBLE,
            cierre DOUBLE,
            volumen BIGINT,
            actualizado_en TIMESTAMP DEFAULT now(),
            PRIMARY KEY (ticker, fecha)
        )
        """
    )
    return con


@task(retries=2, retry_delay_seconds=5)
def fetch_favorites(user_id: str = DEFAULT_USER_ID) -> list[str]:
    """Tickers favoritos del usuario, desde la tabla de InsForge."""
    base = os.environ.get("INSFORGE_URL", "").rstrip("/")
    api_key = os.environ.get("INSFORGE_API_KEY", "")
    if not base or not api_key:
        raise RuntimeError("Faltan INSFORGE_URL o INSFORGE_API_KEY en el .env.")
    response = requests.get(
        f"{base}/api/database/records/{TABLE}",
        params={"user_id": f"eq.{user_id}", "select": "ticker", "order": "created_at.asc"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    response.raise_for_status()
    return [row["ticker"] for row in response.json()]


@task
def ultima_fecha(ticker: str):
    """Última fecha ya guardada en MotherDuck para ``ticker`` (None si es nuevo)."""
    con = _conectar_motherduck()
    try:
        row = con.execute(f"SELECT max(fecha) FROM {MD_TABLE} WHERE ticker = ?", [ticker]).fetchone()
    finally:
        con.close()
    return row[0]


@task(retries=2, retry_delay_seconds=10)
def descargar_yfinance(ticker: str, desde=None) -> pd.DataFrame:
    """Precios diarios de Yahoo Finance; incremental si ya hay datos guardados."""
    if desde is None:
        history = yf.Ticker(ticker).history(period=HISTORIAL_INICIAL, interval="1d", auto_adjust=False)
    else:
        inicio = desde - timedelta(days=SOLAPE_DIAS)
        history = yf.Ticker(ticker).history(start=inicio.isoformat(), interval="1d", auto_adjust=False)
    if history.empty:
        return pd.DataFrame()
    df = history.reset_index()
    df["fecha"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.date
    df = df.rename(columns={"Open": "apertura", "High": "maximo", "Low": "minimo", "Close": "cierre", "Volume": "volumen"})
    df["ticker"] = ticker
    df["volumen"] = df["volumen"].fillna(0).astype("int64")
    df = df.dropna(subset=["apertura", "maximo", "minimo", "cierre"])
    return df[["ticker", "fecha", "apertura", "maximo", "minimo", "cierre", "volumen"]]


@task
def subir_motherduck(df: pd.DataFrame) -> int:
    """Inserta o actualiza (por ticker y fecha) las filas en MotherDuck."""
    if df.empty:
        return 0
    con = _conectar_motherduck()
    try:
        con.register("nuevos", df)
        con.execute(
            f"""
            INSERT OR REPLACE INTO {MD_TABLE} (ticker, fecha, apertura, maximo, minimo, cierre, volumen)
            SELECT ticker, fecha, apertura, maximo, minimo, cierre, volumen FROM nuevos
            """
        )
    finally:
        con.close()
    return len(df)


@flow(log_prints=True)
def flujo_datos(user_id: str = DEFAULT_USER_ID) -> dict[str, int]:
    tickers = fetch_favorites(user_id)
    print(f"Favoritos: {tickers}")
    resultado: dict[str, int] = {}
    for ticker in tickers:
        try:
            desde = ultima_fecha(ticker)
            print(f"Descargando {ticker}" + (f" desde {desde}" if desde else f" ({HISTORIAL_INICIAL})"))
            df = descargar_yfinance(ticker, desde)
            resultado[ticker] = subir_motherduck(df)
        except Exception as exc:  # un ticker con problemas no frena a los demás
            print(f"{ticker}: error — {exc}")
            resultado[ticker] = -1
    print(f"Filas subidas a MotherDuck: {resultado}")
    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--una-vez", action="store_true", help="Ejecuta el flujo una vez y termina.")
    args = parser.parse_args()
    if args.una_vez:
        flujo_datos()
    else:
        flujo_datos.serve(
            name="flujo de datos",
            cron="0 18 * * 1-5",          # 6:00 pm, de lunes a viernes
            # timezone="America/New_York"  # si quieres fijarla a la hora de Nueva York
        )