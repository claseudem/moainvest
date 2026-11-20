"""Barómetro Global de Mercado: variación del día por región del mundo.

Cada región se representa con sus índices bursátiles de referencia en Yahoo
Finance (los de Norteamérica son los mismos de la watchlist «Resumen»). La
variación de la región es el promedio de la variación diaria de sus índices
con datos.

Si una región no tiene índice directo (Rusia y Asia Central) o ninguno de sus
índices responde, se usa el promedio global de las demás y se marca
``fallback=True`` para que el mapa lo indique como estimación.

El mapa (``templates/moainvest/_world_map.svg``) se genera a partir de Natural
Earth 110m (dominio público) con ``flask --app run build-world-map``; la
asignación de países a regiones está en ``region_of``.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.core import market_data


@dataclass(frozen=True, slots=True)
class Region:
    slug: str
    name: str
    indices: tuple[tuple[str, str], ...]  # (ticker de Yahoo, nombre corto)


REGIONS: tuple[Region, ...] = (
    Region("norteamerica", "Norteamérica", (("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow Jones"), ("^GSPTSE", "S&P/TSX"))),
    Region("latam", "Latinoamérica", (("^BVSP", "Ibovespa"), ("^MXX", "IPC México"))),
    Region("europa", "Europa", (("^STOXX50E", "Euro Stoxx 50"), ("^GDAXI", "DAX"), ("^FTSE", "FTSE 100"), ("^FCHI", "CAC 40"))),
    Region("oriente-medio", "Oriente Medio", (("^TASI.SR", "Tadawul"), ("^TA125.TA", "TA-125"), ("XU100.IS", "BIST 100"))),
    Region("africa", "África", (("^J203.JO", "JSE All Share"), ("AFK", "VanEck Africa"))),
    Region("rusia-asia-central", "Rusia y Asia Central", ()),
    Region("asia-sur", "Sur de Asia", (("^BSESN", "Sensex"), ("^NSEI", "Nifty 50"))),
    Region("asia-oriental", "Asia Oriental", (("^N225", "Nikkei 225"), ("^HSI", "Hang Seng"), ("000001.SS", "SSE Composite"), ("^KS11", "KOSPI"))),
    Region("sudeste-asiatico", "Sudeste Asiático", (("^STI", "STI Singapur"), ("^JKSE", "IDX Jakarta"))),
    Region("oceania", "Oceanía", (("^AXJO", "ASX 200"), ("^NZ50", "NZX 50"))),
)

MAX_WORKERS = 12


def region_of(props: dict) -> str | None:
    """Región del barómetro de un país de Natural Earth (``None``: no se dibuja)."""
    code = props.get("ADM0_A3")
    continent = props.get("CONTINENT")
    sub = props.get("SUBREGION")
    if continent in ("Antarctica", "Seven seas (open ocean)"):
        return None
    if code == "RUS" or sub == "Central Asia":
        return "rusia-asia-central"
    if code == "IRN" or sub == "Western Asia":
        return "oriente-medio"
    if sub == "Northern America":
        return "norteamerica"
    if continent in ("North America", "South America"):
        return "latam"
    return {
        "Europe": "europa",
        "Africa": "africa",
        "Oceania": "oceania",
    }.get(continent) or {
        "Southern Asia": "asia-sur",
        "Eastern Asia": "asia-oriental",
        "South-Eastern Asia": "sudeste-asiatico",
    }.get(sub)


def snapshot() -> list[dict]:
    """Variación diaria de cada región con el detalle de sus índices."""
    tickers = [t for r in REGIONS for t, _ in r.indices]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        quotes = dict(zip(tickers, pool.map(market_data.get_quote, tickers)))

    regions = []
    for region in REGIONS:
        indices = []
        for ticker, label in region.indices:
            q = quotes[ticker]
            indices.append({"ticker": ticker, "name": label, "price": q.price, "change_percent": q.change_percent})
        values = [i["change_percent"] for i in indices if i["change_percent"] is not None]
        regions.append(
            {
                "slug": region.slug,
                "name": region.name,
                "change_percent": sum(values) / len(values) if values else None,
                "indices": indices,
                "fallback": not values,
            }
        )

    measured = [r["change_percent"] for r in regions if not r["fallback"]]
    global_avg = sum(measured) / len(measured) if measured else None
    for r in regions:
        if r["fallback"]:
            r["change_percent"] = global_avg
    return regions
