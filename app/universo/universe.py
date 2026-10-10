"""Universo de acciones del usuario (los "models" de la app).

Las acciones viven en ``universe.csv`` (junto a este módulo), sacadas de un
screener de Finviz (filtros: con beneficios según el PER adelantado, volumen
medio > 2M, con opciones y precio entre 10 y 20 USD). La capitalización y el
PER son una foto fija; el precio y la variación del día los pide el navegador
en vivo a ``/api/quote/<ticker>``.

Para añadir o quitar acciones del universo basta con editar el CSV. Los
tickers deben ser los de Yahoo Finance (p. ej. ``PBR-A``).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

CSV_PATH = Path(__file__).with_name("universe.csv")


@dataclass(frozen=True, slots=True)
class Stock:
    ticker: str
    name: str
    sector: str
    industry: str
    country: str
    market_cap: float
    """Capitalización bursátil en USD."""
    pe: float | None
    """PER; ``None`` si no tiene (beneficios negativos)."""


def parse_market_cap(value: str) -> float:
    """``"3.56B"`` -> 3.56e9; ``"696.55M"`` -> 6.9655e8."""
    return float(value[:-1]) * {"B": 1e9, "M": 1e6}[value[-1]]


def load_universe(path: Path = CSV_PATH) -> tuple[Stock, ...]:
    with path.open(encoding="utf-8", newline="") as f:
        return tuple(
            Stock(
                ticker=row["ticker"],
                name=row["name"],
                sector=row["sector"],
                industry=row["industry"],
                country=row["country"],
                market_cap=parse_market_cap(row["market_cap"]),
                pe=None if row["pe"] == "-" else float(row["pe"]),
            )
            for row in csv.DictReader(f)
        )


UNIVERSE: tuple[Stock, ...] = load_universe()


def sectors() -> list[tuple[str, int]]:
    """Sectores del universo con su número de acciones, de más a menos."""
    counts: dict[str, int] = {}
    for stock in UNIVERSE:
        counts[stock.sector] = counts.get(stock.sector, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def format_market_cap(value: float) -> str:
    return f"{value / 1e9:.2f} B" if value >= 1e9 else f"{value / 1e6:.0f} M"
