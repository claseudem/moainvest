"""Búsqueda de símbolos para el autocompletado de "Agregar un activo".

Combina una lista local de activos populares (respuesta instantánea al
enfocar el campo) con la búsqueda de Yahoo Finance (``yfinance.Search``), que
busca por ticker **y** por nombre y corrige erratas: "appl" devuelve AAPL.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import yfinance as yf

SEARCH_CACHE_TTL = 10 * 60
MAX_RESULTS = 8

# Tipos de Yahoo que tienen sentido en la app, con su etiqueta en español.
TYPES = {
    "EQUITY": "Acción",
    "ETF": "ETF",
    "INDEX": "Índice",
    "CRYPTOCURRENCY": "Cripto",
    "CURRENCY": "Divisa",
    "FUTURE": "Futuro",
    "MUTUALFUND": "Fondo",
}


@dataclass(frozen=True, slots=True)
class SymbolMatch:
    ticker: str
    nombre: str
    tipo: str
    bolsa: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


POPULAR: tuple[SymbolMatch, ...] = (
    SymbolMatch("AAPL", "Apple Inc.", "Acción", "NASDAQ"),
    SymbolMatch("BTC-USD", "Bitcoin USD", "Cripto", "CCC"),
    SymbolMatch("^GSPC", "S&P 500", "Índice", "SNP"),
    SymbolMatch("NVDA", "NVIDIA Corporation", "Acción", "NASDAQ"),
    SymbolMatch("TSLA", "Tesla, Inc.", "Acción", "NASDAQ"),
    SymbolMatch("MSFT", "Microsoft Corporation", "Acción", "NASDAQ"),
    SymbolMatch("AMZN", "Amazon.com, Inc.", "Acción", "NASDAQ"),
    SymbolMatch("ETH-USD", "Ethereum USD", "Cripto", "CCC"),
    SymbolMatch("^IXIC", "NASDAQ Composite", "Índice", "NASDAQ"),
    SymbolMatch("EURUSD=X", "EUR/USD", "Divisa", "CCY"),
)

_cache: dict[str, tuple[float, list[SymbolMatch]]] = {}


def _local_matches(query: str) -> list[SymbolMatch]:
    q = query.lower()
    starts = [m for m in POPULAR if m.ticker.lower().startswith(q)]
    contains = [m for m in POPULAR if m not in starts and (q in m.ticker.lower() or q in m.nombre.lower())]
    return starts + contains


def _remote(query: str) -> list[SymbolMatch]:
    try:
        quotes = yf.Search(query, max_results=MAX_RESULTS, news_count=0).quotes or []
    except Exception:
        return []
    matches = []
    for quote in quotes:
        ticker = quote.get("symbol")
        kind = TYPES.get(quote.get("quoteType") or "")
        if not ticker or kind is None:
            continue
        name = quote.get("longname") or quote.get("shortname") or ticker
        matches.append(SymbolMatch(ticker=ticker, nombre=name, tipo=kind, bolsa=quote.get("exchDisp")))
    return matches


def search(query: str) -> list[SymbolMatch]:
    """Activos que coinciden con ``query`` por ticker o nombre. Sin texto: los populares."""
    query = query.strip()
    if not query:
        return list(POPULAR)
    key = query.lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < SEARCH_CACHE_TTL:
        return hit[1]
    results: list[SymbolMatch] = []
    seen: set[str] = set()
    # Yahoo primero (corrige erratas y conoce miles de símbolos); los populares
    # completan si Yahoo no responde.
    for match in _remote(query) + _local_matches(query):
        if match.ticker not in seen:
            seen.add(match.ticker)
            results.append(match)
    results = results[:MAX_RESULTS]
    _cache[key] = (time.time(), results)
    return results
