"""Mercados: las categorías de la página ``/mercados`` (sin Flask).

Cada ``Market`` agrupa símbolos de Yahoo Finance bajo un tema (índices,
acciones, cripto, divisas, materias primas, bonos, ETF) con una explicación
corta de qué mide, pensada para quien empieza a invertir.

``kind`` decide cómo se pinta la categoría:

- ``price``: tarjetas con precio, variación del día y línea del último mes.
- ``yield``: rendimientos (en %) de la deuda pública de EE. UU. y su
  **curva de rendimiento**, que avisa si está invertida.
- ``bonds``: bonos corporativos a través de ETF (Yahoo no publica bonos
  corporativos uno a uno), en una tabla filtrable por plazo y calidad.

Para añadir una categoría basta con otra entrada en ``MARKETS``: aparece sola
en la navegación de la página, con su sección y su endpoint de precios.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.watchlists import Symbol

Kind = Literal["price", "yield", "bonds"]


@dataclass(frozen=True, slots=True)
class Instrument(Symbol):
    """Un símbolo con datos extra para algunas categorías."""

    # Bonos corporativos: etiqueta del grupo (Corto plazo, Alto rendimiento...).
    group: str | None = None
    # Curva de rendimiento: vencimiento en años (eje X de la curva).
    years: float | None = None


@dataclass(frozen=True, slots=True)
class Market:
    slug: str
    name: str
    icon: str
    about: str
    symbols: tuple[Instrument, ...]
    kind: Kind = "price"
    groups: tuple[str, ...] = field(default=())

    @property
    def tickers(self) -> list[str]:
        return [s.ticker for s in self.symbols]


def _i(ticker: str, label: str, **extra) -> Instrument:
    return Instrument(ticker, label, **extra)


CORP_GROUPS = ("Corto plazo", "Largo plazo", "Grado de inversión", "Alto rendimiento", "Emergentes")

MARKETS: tuple[Market, ...] = (
    Market(
        slug="indices",
        name="Índices",
        icon="chart-column",
        about="Un índice resume en un número cómo se mueve un grupo de empresas: si sube, la mayoría de esas acciones sube.",
        symbols=(
            _i("^GSPC", "S&P 500"),
            _i("^IXIC", "Nasdaq"),
            _i("^DJI", "Dow Jones"),
            _i("^RUT", "Russell 2000"),
            _i("^STOXX50E", "Euro Stoxx 50"),
            _i("^N225", "Nikkei 225"),
            _i("^BVSP", "Bovespa"),
            _i("^MXX", "IPC México"),
        ),
    ),
    Market(
        slug="acciones",
        name="Acciones",
        icon="briefcase",
        about="Una acción es una parte de una empresa. Aquí, las colombianas que cotizan en Nueva York y las grandes tecnológicas.",
        symbols=(
            _i("EC", "Ecopetrol"),
            _i("CIB", "Bancolombia"),
            _i("AVAL", "Grupo Aval"),
            _i("AAPL", "Apple"),
            _i("MSFT", "Microsoft"),
            _i("NVDA", "NVIDIA"),
            _i("AMZN", "Amazon"),
            _i("TSLA", "Tesla"),
        ),
    ),
    Market(
        slug="cripto",
        name="Cripto",
        icon="activity",
        about="Monedas digitales que cotizan 24/7. Son mucho más volátiles que las acciones: un 5 % en un día es normal.",
        symbols=(
            _i("BTC-USD", "Bitcoin"),
            _i("ETH-USD", "Ethereum"),
            _i("SOL-USD", "Solana"),
            _i("XRP-USD", "XRP"),
            _i("BNB-USD", "BNB"),
            _i("ADA-USD", "Cardano"),
        ),
    ),
    Market(
        slug="divisas",
        name="Divisas",
        icon="refresh-cw",
        about="Cuántas unidades de una moneda cuesta otra. Si USD/COP sube, el dólar está más caro en pesos.",
        symbols=(
            _i("USDCOP=X", "Dólar / Peso colombiano"),
            _i("EURUSD=X", "Euro / Dólar"),
            _i("USDMXN=X", "Dólar / Peso mexicano"),
            _i("USDJPY=X", "Dólar / Yen"),
            _i("GBPUSD=X", "Libra / Dólar"),
            _i("DX-Y.NYB", "Índice dólar (DXY)"),
        ),
    ),
    Market(
        slug="materias-primas",
        name="Materias primas",
        icon="layers",
        about="Futuros de petróleo, metales y agrícolas. El petróleo y el café pesan mucho en la economía colombiana.",
        symbols=(
            _i("CL=F", "Petróleo WTI"),
            _i("BZ=F", "Petróleo Brent"),
            _i("KC=F", "Café"),
            _i("GC=F", "Oro"),
            _i("SI=F", "Plata"),
            _i("HG=F", "Cobre"),
            _i("NG=F", "Gas natural"),
        ),
    ),
    Market(
        slug="bonos-publicos",
        name="Bonos públicos",
        icon="chart-spline",
        about="Lo que paga al año el Tesoro de EE. UU. por prestarle dinero a cada plazo. Es la tasa de referencia del mundo.",
        kind="yield",
        symbols=(
            _i("^IRX", "Letra a 3 meses", years=0.25),
            _i("^FVX", "Bono a 5 años", years=5),
            _i("^TNX", "Bono a 10 años", years=10),
            _i("^TYX", "Bono a 30 años", years=30),
        ),
    ),
    Market(
        slug="bonos-corporativos",
        name="Bonos corporativos",
        icon="file-text",
        about="Deuda emitida por empresas. Se sigue con ETF que reúnen cientos de bonos: más riesgo de impago paga más interés.",
        kind="bonds",
        groups=CORP_GROUPS,
        symbols=(
            _i("VCSH", "Vanguard bonos corporativos corto plazo", group="Corto plazo"),
            _i("IGSB", "iShares bonos corporativos 1-5 años", group="Corto plazo"),
            _i("VCLT", "Vanguard bonos corporativos largo plazo", group="Largo plazo"),
            _i("IGLB", "iShares bonos corporativos 10+ años", group="Largo plazo"),
            _i("LQD", "iShares bonos con grado de inversión", group="Grado de inversión"),
            _i("VCIT", "Vanguard bonos corporativos plazo medio", group="Grado de inversión"),
            _i("HYG", "iShares bonos de alto rendimiento", group="Alto rendimiento"),
            _i("JNK", "SPDR bonos de alto rendimiento", group="Alto rendimiento"),
            _i("EMB", "iShares bonos de mercados emergentes", group="Emergentes"),
        ),
    ),
    Market(
        slug="etf",
        name="ETF",
        icon="list",
        about="Fondos que cotizan como una acción y replican un índice o un tema: una forma barata de diversificar.",
        symbols=(
            _i("SPY", "SPDR S&P 500"),
            _i("QQQ", "Invesco QQQ (Nasdaq-100)"),
            _i("VT", "Vanguard Total World"),
            _i("EEM", "iShares mercados emergentes"),
            _i("GLD", "SPDR Gold"),
            _i("IWM", "iShares Russell 2000"),
        ),
    ),
)

_BY_SLUG = {m.slug: m for m in MARKETS}


def get_market(slug: str) -> Market | None:
    return _BY_SLUG.get(slug)


def curve_shape(yields: dict[float, float | None]) -> dict[str, str]:
    """Forma de la curva de rendimiento según el tramo corto (≤ 1 año) y el de 10 años.

    ``yields`` va de años a rendimiento en %. Una curva **invertida** (el corto
    paga más que el largo) ha anticipado muchas recesiones en EE. UU.
    """
    short = next((v for y, v in sorted(yields.items()) if y <= 1 and v is not None), None)
    ten = yields.get(10)
    if short is None or ten is None:
        return {"estado": "sin-datos", "texto": "Sin datos suficientes para leer la curva."}
    spread = ten - short
    if spread < -0.05:
        return {"estado": "invertida", "texto": f"Curva invertida: el plazo corto paga {abs(spread):.2f} pp más que el de 10 años. Históricamente ha anticipado recesiones."}
    if spread <= 0.25:
        return {"estado": "plana", "texto": f"Curva plana: apenas {spread:.2f} pp entre el plazo corto y el de 10 años. El mercado duda del crecimiento."}
    return {"estado": "normal", "texto": f"Curva normal: el bono a 10 años paga {spread:.2f} pp más que el plazo corto, como es habitual."}
