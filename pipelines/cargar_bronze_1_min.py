"""Descarga velas de 1 minuto de Dukascopy y las escribe en MotherDuck (bronze).

Uso:
    uv run pipelines/cargar_bronze_1_min.py

Variable del ``.env`` de la raíz: MOTHER_DUCK_TOKEN.
La tabla ``moainvest.bronze.spy_1_min`` guarda todas las columnas como VARCHAR,
más ``created_at`` y ``updated_at``. Se recrea completa en cada ejecución.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import dukascopy_python
import duckdb
from dotenv import load_dotenv
from dukascopy_python.instruments import INSTRUMENT_ETF_CFD_US_SPY_US_USD

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE = os.environ.get("MOTHERDUCK_DATABASE", "moainvest")
TABLE = f"{DATABASE}.bronze.spy_1_min"

START = datetime(2025, 1, 1)
END = datetime(2026, 10, 20)


def conectar() -> duckdb.DuckDBPyConnection:
    token = os.environ.get("MOTHER_DUCK_TOKEN", "")
    if not token:
        raise RuntimeError("Falta MOTHER_DUCK_TOKEN en el .env.")
    os.environ["motherduck_token"] = token  # nombre que espera el cliente de DuckDB
    return duckdb.connect("md:")


def descargar():
    return dukascopy_python.fetch(
        INSTRUMENT_ETF_CFD_US_SPY_US_USD,
        dukascopy_python.INTERVAL_MIN_1,
        dukascopy_python.OFFER_SIDE_BID,
        START,
        END,
    )


def main() -> None:
    t0 = time.perf_counter()
    df = descargar()
    t_descarga = time.perf_counter() - t0
    print(f"Descargadas {len(df):,} filas de Dukascopy en {t_descarga:.2f}s")

    # El índice (timestamp) pasa a columna y todo se convierte a texto.
    df = df.reset_index().astype(str)

    t0 = time.perf_counter()
    con = conectar()
    con.register("velas", df)
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {DATABASE}.bronze")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLE} AS
        SELECT v.*,
               current_timestamp AS created_at,
               current_timestamp AS updated_at
        FROM velas v
        """
    )
    total = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    t_escritura = time.perf_counter() - t0
    print(f"Escritas {total:,} filas en {TABLE} en {t_escritura:.2f}s")


if __name__ == "__main__":
    main()
