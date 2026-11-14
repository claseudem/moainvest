"""Catálogo de activos de la plataforma, agrupados por categoría.

Lo usan los filtros de "Noticias" y la cuadrícula de "¿Qué piensas tú?".
Incluye todos los símbolos de las watchlists (``core.watchlists``) más los
principales índices, tecnológicas y criptomonedas.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.watchlists import WATCHLISTS


@dataclass(frozen=True, slots=True)
class Category:
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class Asset:
    ticker: str
    nombre: str
    categoria: str


CATEGORIES: tuple[Category, ...] = (
    Category("indices", "Índices"),
    Category("tecnologia", "Tecnología"),
    Category("cripto", "Cripto"),
    Category("divisas", "Divisas"),
    Category("gaming", "Gaming"),
    Category("energia", "Energía"),
)

ASSETS: tuple[Asset, ...] = (
    Asset("^GSPC", "S&P 500", "indices"),
    Asset("^IXIC", "Nasdaq Composite", "indices"),
    Asset("^DJI", "Dow Jones Industrial Average", "indices"),
    Asset("AAPL", "Apple Inc.", "tecnologia"),
    Asset("MSFT", "Microsoft Corporation", "tecnologia"),
    Asset("NVDA", "NVIDIA Corporation", "tecnologia"),
    Asset("AMZN", "Amazon.com, Inc.", "tecnologia"),
    Asset("GOOGL", "Alphabet Inc.", "tecnologia"),
    Asset("META", "Meta Platforms, Inc.", "tecnologia"),
    Asset("TSLA", "Tesla, Inc.", "tecnologia"),
    Asset("DELL", "Dell Technologies Inc.", "tecnologia"),
    Asset("HPQ", "HP Inc.", "tecnologia"),
    Asset("005930.KS", "Samsung Electronics", "tecnologia"),
    Asset("BTC-USD", "Bitcoin", "cripto"),
    Asset("ETH-USD", "Ethereum", "cripto"),
    Asset("SOL-USD", "Solana", "cripto"),
    Asset("EURUSD=X", "EUR/USD", "divisas"),
    Asset("SONY", "Sony Group Corporation", "gaming"),
    Asset("NTDOY", "Nintendo Co., Ltd.", "gaming"),
    Asset("EA", "Electronic Arts Inc.", "gaming"),
    Asset("TTWO", "Take-Two Interactive", "gaming"),
    Asset("RBLX", "Roblox Corporation", "gaming"),
    Asset("UEC", "Uranium Energy Corp", "energia"),
)

BY_TICKER = {asset.ticker: asset for asset in ASSETS}
CATEGORY_NAMES = {c.slug: c.name for c in CATEGORIES}


def get(ticker: str) -> Asset | None:
    return BY_TICKER.get(ticker)


def tickers_in(category: str) -> list[str]:
    return [a.ticker for a in ASSETS if a.categoria == category]


def name_for(ticker: str) -> str:
    asset = BY_TICKER.get(ticker)
    if asset:
        return asset.nombre
    for watchlist in WATCHLISTS:
        for symbol in watchlist.symbols:
            if symbol.ticker == ticker:
                return symbol.display_name
    return ticker
