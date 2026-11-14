"""Prefect flow: favorites (InsForge) -> 1-minute candles (Dukascopy) -> MotherDuck bronze.

Usage:
    uv run pipelines/precios_1_min.py              # keeps the flow running every hour
    uv run pipelines/precios_1_min.py --una-vez    # runs once and exits (handy for testing)

Variables from the root ``.env``: INSFORGE_URL, INSFORGE_API_KEY and MOTHER_DUCK_TOKEN.
Takes the unique tickers from EVERYONE's favorites, looks each one up in Dukascopy and
appends to ``moainvest.bronze.precios`` (data columns as VARCHAR, plus ``granularity``,
``source``, ``partition_date``, ``created_at`` and ``updated_at``).
Each run only appends candles newer than the last one stored per ticker.

MotherDuck native tables have no declarative partitioning or clustering, so both are
emulated: ``partition_date`` is the partition key and every insert is sorted by
(partition_date, ticker, granularity, timestamp) so DuckDB zonemaps can skip row groups.
"""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import dukascopy_python
import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv
from dukascopy_python import instruments
from prefect import flow, task

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

FAVORITES_TABLE = "activos_favoritos"
MD_DATABASE = os.environ.get("MOTHERDUCK_DATABASE", "moainvest")
MD_TABLE = f"{MD_DATABASE}.bronze.precios"
INITIAL_HISTORY_DAYS = 30  # first download for a new ticker
GRANULARITY = "1min"
SOURCE = "dukascopy"

# Yahoo tickers that do not follow the INSTRUMENT_US_<TICKER>_US_USD rule.
SPECIAL_INSTRUMENTS = {
    "BTC-USD": "INSTRUMENT_VCCY_BTC_USD",
    "^GSPC": "INSTRUMENT_IDX_AMERICA_E_SANDP_500",
}


def resolve_instrument(ticker: str) -> str | None:
    """Dukascopy instrument for a Yahoo ticker (None if it does not exist)."""
    name = SPECIAL_INSTRUMENTS.get(ticker, f"INSTRUMENT_US_{ticker.replace('-', '_')}_US_USD")
    return getattr(instruments, name, None)


def _connect_motherduck() -> duckdb.DuckDBPyConnection:
    token = os.environ.get("MOTHER_DUCK_TOKEN", "")
    if not token:
        raise RuntimeError("MOTHER_DUCK_TOKEN is missing from .env.")
    os.environ["motherduck_token"] = token  # name the DuckDB client expects
    con = duckdb.connect("md:")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {MD_DATABASE}.bronze")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MD_TABLE} (
            ticker VARCHAR,
            timestamp VARCHAR,
            open VARCHAR,
            high VARCHAR,
            low VARCHAR,
            close VARCHAR,
            volume VARCHAR,
            granularity VARCHAR,
            source VARCHAR,
            partition_date DATE,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    return con


@task(retries=2, retry_delay_seconds=5)
def favorite_tickers() -> list[str]:
    """Unique tickers from all users' favorites, from InsForge."""
    base = os.environ.get("INSFORGE_URL", "").rstrip("/")
    api_key = os.environ.get("INSFORGE_API_KEY", "")
    if not base or not api_key:
        raise RuntimeError("INSFORGE_URL or INSFORGE_API_KEY is missing from .env.")
    response = requests.get(
        f"{base}/api/database/records/{FAVORITES_TABLE}",
        params={"select": "ticker"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    response.raise_for_status()
    return sorted({row["ticker"] for row in response.json()})


@task
def last_candle(ticker: str) -> str | None:
    """ISO timestamp (text) of the last stored candle for ``ticker``."""
    con = _connect_motherduck()
    try:
        return con.execute(f"SELECT max(timestamp) FROM {MD_TABLE} WHERE ticker = ? AND granularity = ? AND source = ?", [ticker, GRANULARITY, SOURCE]).fetchone()[0]
    finally:
        con.close()


@task(retries=2, retry_delay_seconds=10)
def download_dukascopy(ticker: str, instrument: str, since: str | None) -> pd.DataFrame:
    """1-minute (bid) candles after ``since``; if none stored, the last few days."""
    end = datetime.now(UTC).replace(tzinfo=None)
    start = pd.Timestamp(since).tz_localize(None).to_pydatetime() if since else end - timedelta(days=INITIAL_HISTORY_DAYS)
    df = dukascopy_python.fetch(
        instrument,
        dukascopy_python.INTERVAL_MIN_1,
        dukascopy_python.OFFER_SIDE_BID,
        start,
        end,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index().rename(columns={df.index.name or "index": "timestamp"})
    df = df.astype(str)
    if since:
        df = df[df["timestamp"] > since]  # only new candles (ISO text sorts correctly)
    df.insert(0, "ticker", ticker)
    return df[["ticker", "timestamp", "open", "high", "low", "close", "volume"]]


@task
def append_motherduck(df: pd.DataFrame) -> int:
    """Appends the new candles, sorted for clustering, with created_at and updated_at."""
    if df.empty:
        return 0
    con = _connect_motherduck()
    try:
        con.register("new_candles", df)
        con.execute(
            f"""
            INSERT INTO {MD_TABLE}
            SELECT ticker, timestamp, open, high, low, close, volume,
                   ? AS granularity, ? AS source,
                   CAST(CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS DATE) AS partition_date,
                   current_timestamp, current_timestamp
            FROM new_candles
            ORDER BY partition_date, ticker, granularity, timestamp
            """,
            [GRANULARITY, SOURCE],
        )
    finally:
        con.close()
    return len(df)


@flow(log_prints=True)
def prices_flow() -> dict[str, int]:
    tickers = favorite_tickers()
    print(f"Unique tickers: {tickers}")
    result: dict[str, int] = {}
    for ticker in tickers:
        instrument = resolve_instrument(ticker)
        if instrument is None:
            print(f"{ticker}: not available on Dukascopy, skipping")
            result[ticker] = 0
            continue
        try:
            since = last_candle(ticker)
            print(f"Downloading {ticker} ({instrument})" + (f" since {since}" if since else f" (last {INITIAL_HISTORY_DAYS} days)"))
            result[ticker] = append_motherduck(download_dukascopy(ticker, instrument, since))
        except Exception as exc:  # one failing ticker does not stop the others
            print(f"{ticker}: error: {exc}")
            result[ticker] = -1
    print(f"Rows appended to {MD_TABLE}: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--una-vez", action="store_true", help="Run the flow once and exit.")
    args = parser.parse_args()
    if args.una_vez:
        prices_flow()
    else:
        prices_flow.serve(name="1-min prices flow", cron="0 * * * 1-5")  # every hour, Monday to Friday
