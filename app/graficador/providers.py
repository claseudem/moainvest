"""Proveedores de precios del Graficador (lógica sin Flask).

Cada proveedor devuelve velas en el mismo formato que ``market_data.get_candles``
(``time`` en segundos UTC, ``open``, ``high``, ``low``, ``close``, ``volume``),
así que el gráfico y los indicadores TA-Lib no saben de dónde vienen los datos.

* ``yahoo``: el proveedor de siempre (``app.core.market_data``).
* ``alphavantage``: API REST de Alpha Vantage (``TIME_SERIES_INTRADAY``,
  ``DAILY``, ``WEEKLY`` y ``MONTHLY`` según el intervalo). Necesita
  ``ALPHAVANTAGE_API_KEY``.
* ``dukascopy``: el feed público de gráficos de Dukascopy Bank. Sin clave y con
  intradía (de 1 minuto a 1 hora) de años atrás, no solo de los últimos días como
  Yahoo. Cubre divisas, cripto, índices, materias primas y acciones (CFD).

Cualquier fallo se comunica con ``ProviderError`` (mensaje en español listo para
la UI y código HTTP sugerido) para que la gráfica nunca se rompa.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import time
import requests

from app.core import market_data
from config import Config

Candle = dict[str, Any]

DEFAULT_PROVIDER = "yahoo"


class ProviderError(Exception):
    """Error de un proveedor, con mensaje para el usuario y código HTTP."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


# Intervalos que admite el Graficador con cualquier proveedor (los de los botones
# de rango); un proveedor puede ofrecer más con ``extra_intervals``.
STANDARD_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo")


class Provider:
    """Interfaz común: ``id``, ``name``, disponibilidad y ``get_candles``.

    ``interval_choices`` lista las periodicidades que el usuario puede elegir a
    mano en el Graficador; vacío = la periodicidad la fija el botón de rango.
    """

    id: str = ""
    name: str = ""
    interval_choices: tuple[dict[str, Any], ...] = ()

    def supports(self, interval: str) -> bool:
        return interval in STANDARD_INTERVALS or any(c["value"] == interval for c in self.interval_choices)

    def unavailable_reason(self) -> str | None:
        """``None`` si se puede usar; si no, el motivo en español."""
        return None

    def get_candles(self, ticker: str, range_: str, interval: str) -> list[Candle]:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        reason = self.unavailable_reason()
        return {
            "id": self.id,
            "name": self.name,
            "available": reason is None,
            "reason": reason,
            "intervals": list(self.interval_choices),
        }


class YahooProvider(Provider):
    id = "yahoo"
    name = "Yahoo Finance"

    def get_candles(self, ticker: str, range_: str, interval: str) -> list[Candle]:
        try:
            return market_data.get_candles(ticker, range_, interval)
        except Exception as error:  # yfinance lanza de todo
            raise ProviderError("Yahoo Finance no respondió. Inténtalo de nuevo.") from error


# ───────────────────────── Alpha Vantage ─────────────────────────

AV_URL = "https://www.alphavantage.co/query"
AV_TIMEOUT = 20
_NY = ZoneInfo("America/New_York")

# Intervalo del gráfico -> (function, interval de Alpha Vantage o None).
AV_FUNCTIONS: dict[str, tuple[str, str | None]] = {
    "1m": ("TIME_SERIES_INTRADAY", "1min"),
    "5m": ("TIME_SERIES_INTRADAY", "5min"),
    "15m": ("TIME_SERIES_INTRADAY", "15min"),
    "30m": ("TIME_SERIES_INTRADAY", "30min"),
    "1h": ("TIME_SERIES_INTRADAY", "60min"),
    "1d": ("TIME_SERIES_DAILY", None),
    "1wk": ("TIME_SERIES_WEEKLY", None),
    "1mo": ("TIME_SERIES_MONTHLY", None),
}
_SERIES_KEYS = {
    "TIME_SERIES_DAILY": "Time Series (Daily)",
    "TIME_SERIES_WEEKLY": "Weekly Time Series",
    "TIME_SERIES_MONTHLY": "Monthly Time Series",
}
# Días que abarca cada rango, contados hacia atrás desde la última vela.
RANGE_DAYS = {"1d": 1, "5d": 5, "1mo": 31, "3mo": 93, "6mo": 186, "1y": 366, "2y": 731, "5y": 1827}


def _parse_time(text: str) -> int:
    """Segundos UTC de la marca de tiempo de Alpha Vantage (intradía en hora de Nueva York)."""
    if len(text) > 10:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_NY)
    else:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def parse_series(payload: dict[str, Any], series_key: str) -> list[Candle]:
    """Normaliza una serie de Alpha Vantage a velas ascendentes y sin duplicados."""
    rows = payload.get(series_key)
    if not isinstance(rows, dict):
        raise ProviderError("Alpha Vantage devolvió una respuesta inesperada.")
    by_time: dict[int, Candle] = {}
    for stamp, row in rows.items():
        try:
            time_ = _parse_time(stamp)
            by_time[time_] = {
                "time": time_,
                "open": float(row["1. open"]),
                "high": float(row["2. high"]),
                "low": float(row["3. low"]),
                "close": float(row["4. close"]),
                "volume": int(float(row.get("5. volume", 0) or 0)),
            }
        except (KeyError, TypeError, ValueError):
            continue  # fila incompleta: se omite, como hace Yahoo con los NaN
    return [by_time[t] for t in sorted(by_time)]


def slice_range(candles: list[Candle], range_: str) -> list[Candle]:
    """Recorta a ``range_`` contando desde la última vela (``max`` = todo)."""
    days = RANGE_DAYS.get(range_)
    if not candles or days is None:
        return candles
    cutoff = candles[-1]["time"] - int(timedelta(days=days).total_seconds())
    return [c for c in candles if c["time"] > cutoff]


class AlphaVantageProvider(Provider):
    id = "alphavantage"
    name = "Alpha Vantage"

    def __init__(self, get: Callable[..., Any] | None = None) -> None:
        self._get = get

    def unavailable_reason(self) -> str | None:
        if not Config.ALPHAVANTAGE_API_KEY:
            return "Falta ALPHAVANTAGE_API_KEY en el .env (clave gratuita en alphavantage.co)."
        return None

    def get_candles(self, ticker: str, range_: str, interval: str) -> list[Candle]:
        reason = self.unavailable_reason()
        if reason:
            raise ProviderError(reason, 503)
        if interval not in AV_FUNCTIONS:
            raise ProviderError(f"Alpha Vantage no admite el intervalo «{interval}».", 422)
        if any(ch in ticker for ch in "^="):
            raise ProviderError(
                f"Alpha Vantage no admite «{ticker}» (índices y divisas de Yahoo). Usa Yahoo Finance.", 422
            )
        function, av_interval = AV_FUNCTIONS[interval]
        # La serie completa se cachea por (símbolo, función, intervalo): todos los
        # rangos y el calentamiento de los indicadores salen de una sola llamada,
        # que es lo que cuenta para el límite diario del plan gratuito.
        key = f"av:{ticker}:{function}:{av_interval}"
        candles = market_data._cached(
            key, Config.ALPHAVANTAGE_CACHE_TTL, lambda: self._fetch(ticker, function, av_interval)
        )
        return slice_range(candles, range_)

    def _fetch(self, ticker: str, function: str, av_interval: str | None) -> list[Candle]:
        params = {"function": function, "symbol": ticker, "apikey": Config.ALPHAVANTAGE_API_KEY}
        if av_interval:
            params["interval"] = av_interval
            series_key = f"Time Series ({av_interval})"
        else:
            series_key = _SERIES_KEYS[function]
        if av_interval or function == "TIME_SERIES_DAILY":
            params["outputsize"] = "full"
        payload = self._request(params)
        # ``outputsize=full`` de la serie diaria es de pago en algunos planes:
        # se reintenta con ``compact`` (últimos 100 días) antes de rendirse.
        if function == "TIME_SERIES_DAILY" and self._is_premium(payload):
            params["outputsize"] = "compact"
            # El plan gratuito admite 1 petición por segundo: sin pausa el reintento
            # chocaría con la anterior.
            time.sleep(1.1)
            payload = self._request(params)
        self._raise_for_payload(payload)
        candles = parse_series(payload, series_key)
        if not candles:
            raise ProviderError(f"Alpha Vantage no tiene datos de «{ticker}» para este intervalo.", 404)
        return candles

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        get = self._get or requests.get
        try:
            response = get(AV_URL, params=params, timeout=AV_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as error:
            raise ProviderError("Alpha Vantage tardó demasiado en responder.", 504) from error
        except (requests.RequestException, ValueError) as error:
            raise ProviderError("No se pudo contactar con Alpha Vantage.") from error
        if not isinstance(data, dict):
            raise ProviderError("Alpha Vantage devolvió una respuesta inesperada.")
        return data

    @staticmethod
    def _message(payload: dict[str, Any]) -> str:
        return str(payload.get("Note") or payload.get("Information") or "")

    def _is_premium(self, payload: dict[str, Any]) -> bool:
        text = self._message(payload).lower()
        return "premium" in text and "rate limit" not in text and "requests per" not in text

    def _raise_for_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("Error Message"):
            raise ProviderError("Alpha Vantage no reconoce ese símbolo o parámetros.", 404)
        if not self._message(payload):
            return
        if self._is_premium(payload):
            raise ProviderError("Alpha Vantage ofrece este intervalo solo con un plan premium.", 422)
        # «Note» / «Information» sobre peticiones por minuto o por día.
        raise ProviderError(
            "Alpha Vantage alcanzó su límite de peticiones (plan gratuito: 25 al día, 5 por minuto). "
            "Espera un poco o usa Yahoo Finance.",
            429,
        )


# ───────────────────────── Dukascopy ─────────────────────────

DK_URL = "https://freeserv.dukascopy.com/2.0/index.php"
DK_TIMEOUT = 20
DK_PAGE = 30_000  # máximo de velas por petición que admite el feed
DK_MAX_PAGES = 8  # por ventana
DK_WORKERS = 8
# El feed rechaza las peticiones sin cabeceras de navegador y sin el Referer de
# su propio widget de gráficos.
DK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36",
    "Referer": "https://freeserv.dukascopy.com/2.0/?path=chart/index",
}

# Intervalo del gráfico -> intervalo de Dukascopy.
DK_INTERVALS = {
    "1s": "1SEC", "10s": "10SEC", "30s": "30SEC",
    "1m": "1MIN", "5m": "5MIN", "10m": "10MIN", "15m": "15MIN", "30m": "30MIN",
    "1h": "1HOUR", "4h": "4HOUR",
    "1d": "1DAY", "1wk": "1WEEK", "1mo": "1MONTH",
}
# Días de historia como máximo por intervalo, para no descargar cientos de
# miles de velas (``max`` a 1 minuto); los rangos más largos se recortan.
DK_MAX_DAYS = {
    "1s": 1, "10s": 5, "30s": 14,
    "1m": 31, "5m": 366, "10m": 366, "15m": 366, "30m": 366, "1h": 1827,
}
# A 1-30 minutos el feed devuelve como mucho ~1 mes por petición (pocos miles de
# velas aunque se pida más): el rango se parte en ventanas que se descargan en
# paralelo. A 1 hora o más, una petición trae hasta 30 000 velas y basta con paginar.
DK_WINDOW_DAYS = {"1s": 0.5, "10s": 2, "30s": 4, "1m": 14, "5m": 28, "10m": 28, "15m": 28, "30m": 28}
# Periodicidades que se ofrecen en el selector del Graficador, agrupadas como en
# la plataforma de Dukascopy (los ticks sueltos no son velas y no se ofrecen).
_DK_LABELS = (
    ("Segundos", (("1s", "1 segundo"), ("10s", "10 segundos"), ("30s", "30 segundos"))),
    ("Minutos", (("1m", "1 minuto"), ("5m", "5 minutos"), ("10m", "10 minutos"), ("15m", "15 minutos"), ("30m", "30 minutos"))),
    ("Horas", (("1h", "1 hora"), ("4h", "4 horas"))),
    ("Días y más", (("1d", "1 día"), ("1wk", "1 semana"), ("1mo", "1 mes"))),
)
DK_CHOICES = tuple(
    {"value": value, "label": label, "group": group, "max_days": DK_MAX_DAYS.get(value)}
    for group, items in _DK_LABELS
    for value, label in items
)
DK_EPOCH = datetime(2003, 5, 1, tzinfo=timezone.utc)  # inicio del histórico de Dukascopy
# Margen para que «1d» o «5d» tengan velas aunque se pidan en fin de semana o
# festivo: se descarga de más y se recorta desde la última vela, como con Yahoo.
DK_PADDING_DAYS = 5
DK_PADDING_DAYS_SECONDS = 3  # a segundos cada día extra pesa mucho: basta con saltar el fin de semana

# Tickers de Yahoo sin equivalente directo por reglas.
DK_SYMBOLS = {
    "^GSPC": "USA500.IDX/USD",
    "^NDX": "USATECH.IDX/USD",
    "^DJI": "USA30.IDX/USD",
    "^GDAXI": "DEU.IDX/EUR",
    "^FTSE": "GBR.IDX/GBP",
    "^N225": "JPN.IDX/JPY",
    "^IBEX": "ESP.IDX/EUR",
    "^STOXX50E": "EUS.IDX/EUR",
    "^FCHI": "FRA.IDX/EUR",
    "GC=F": "XAU/USD",
    "SI=F": "XAG/USD",
    "CL=F": "LIGHT.CMD/USD",
    "BZ=F": "BRENT.CMD/USD",
    "NG=F": "GAS.CMD/USD",
}
# Sufijo de bolsa de Yahoo -> mercado y divisa de Dukascopy (``SAN.MC`` -> ``SAN.ES/EUR``).
DK_EXCHANGES = {
    "MC": "ES/EUR", "DE": "DE/EUR", "PA": "FR/EUR", "AS": "NL/EUR",
    "MI": "IT/EUR", "SW": "CH/CHF", "L": "GB/GBX",
}
_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "USDT"}


def dukascopy_instrument(ticker: str) -> str:
    """Instrumento de Dukascopy para un ticker de Yahoo (``AAPL`` -> ``AAPL.US/USD``)."""
    if ticker in DK_SYMBOLS:
        return DK_SYMBOLS[ticker]
    if len(ticker) == 8 and ticker.endswith("=X"):  # divisas: EURUSD=X
        return f"{ticker[:3]}/{ticker[3:6]}"
    if any(ch in ticker for ch in "^="):
        raise ProviderError(f"Dukascopy no tiene un equivalente de «{ticker}». Usa Yahoo Finance.", 422)
    base, _, quote = ticker.partition("-")
    if quote in _CURRENCIES:  # cripto: BTC-USD
        return f"{base}/{quote}"
    symbol, _, exchange = ticker.replace("-", "").partition(".")  # BRK-B -> BRKB
    if not exchange:
        return f"{symbol}.US/USD"
    if exchange in DK_EXCHANGES:
        return f"{symbol}.{DK_EXCHANGES[exchange]}"
    raise ProviderError(f"Dukascopy no cubre la bolsa «.{exchange}» de «{ticker}». Usa Yahoo Finance.", 422)


def parse_dukascopy(text: str) -> list[list[Any]] | None:
    """Filas ``[ms, open, high, low, close, volume]`` de la respuesta JSONP.

    ``None`` si Dukascopy no conoce el instrumento (responde ``[null]``).
    """
    start, end = text.find("("), text.rfind(")")
    if start < 0 or end < start:
        raise ProviderError("Dukascopy devolvió una respuesta inesperada.")
    try:
        rows = json.loads(text[start + 1 : end])
    except ValueError as error:
        raise ProviderError("Dukascopy devolvió una respuesta inesperada.") from error
    if rows == [None]:
        return None
    if not isinstance(rows, list):
        raise ProviderError("Dukascopy devolvió una respuesta inesperada.")
    return rows


class DukascopyProvider(Provider):
    id = "dukascopy"
    name = "Dukascopy"
    interval_choices = DK_CHOICES

    def __init__(self, get: Callable[..., Any] | None = None, now: Callable[[], datetime] | None = None) -> None:
        self._get = get
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get_candles(self, ticker: str, range_: str, interval: str) -> list[Candle]:
        if interval not in DK_INTERVALS:
            raise ProviderError(f"Dukascopy no admite el intervalo «{interval}».", 422)
        instrument = dukascopy_instrument(ticker)
        days = RANGE_DAYS.get(range_)
        cap = DK_MAX_DAYS.get(interval)
        if cap is not None and (days is None or days > cap):
            days = cap
        key = f"dk:{instrument}:{interval}:{days}"
        candles = market_data._cached(
            key, Config.DUKASCOPY_CACHE_TTL, lambda: self._fetch(ticker, instrument, interval, days)
        )
        return _slice_days(candles, days)

    def _fetch(self, ticker: str, instrument: str, interval: str, days: int | None) -> list[Candle]:
        now = self._now()
        padding = DK_PADDING_DAYS_SECONDS if interval.endswith("s") else DK_PADDING_DAYS
        start = DK_EPOCH if days is None else now - timedelta(days=days + padding)
        step = timedelta(days=DK_WINDOW_DAYS.get(interval) or (now - start).days + 1)
        windows = []
        while start < now:
            windows.append((int(start.timestamp() * 1000), int(min(start + step, now).timestamp() * 1000)))
            start += step

        dk_interval = DK_INTERVALS[interval]
        with ThreadPoolExecutor(max_workers=min(DK_WORKERS, len(windows))) as pool:
            pages = list(pool.map(lambda w: self._fetch_window(instrument, dk_interval, *w), windows))
        if any(rows is None for rows in pages):
            raise ProviderError(f"Dukascopy no tiene datos de «{ticker}» ({instrument}).", 404)

        by_time: dict[int, Candle] = {}
        for rows in pages:
            for row in rows:
                try:
                    ms, open_, high, low, close, volume = row[:6]
                    time_ = int(ms) // 1000
                    by_time[time_] = {
                        "time": time_,
                        "open": float(open_),
                        "high": float(high),
                        "low": float(low),
                        "close": float(close),
                        "volume": float(volume or 0),
                    }
                except (TypeError, ValueError):
                    continue  # fila incompleta: se omite, como hace Yahoo con los NaN
        candles = [by_time[t] for t in sorted(by_time)]
        if not candles:
            raise ProviderError(f"Dukascopy no tiene datos de «{ticker}» ({instrument}) para este rango.", 404)
        return candles

    def _fetch_window(self, instrument: str, interval: str, start: int, end: int) -> list[list[Any]] | None:
        """Velas entre ``start`` y ``end`` (ms), paginando; ``None`` si no existe el instrumento."""
        cursor, rows = start, []
        for _ in range(DK_MAX_PAGES):
            page = self._request(instrument, interval, cursor)
            if page is None:
                return None
            rows.extend(page)
            last = int(page[-1][0]) if page else cursor
            if last >= end or last <= cursor:  # ventana completa o sin más datos
                break
            cursor = last
        return [r for r in rows if r and start <= int(r[0]) <= end]

    def _request(self, instrument: str, interval: str, cursor: int) -> list[list[Any]] | None:
        params = {
            "path": "chart/json3",
            "instrument": instrument,
            "interval": interval,
            "offer_side": "B",
            "time_direction": "N",
            "last_update": str(cursor),
            "limit": str(DK_PAGE),
            "splits": "true",
            "stocks": "true",
            "jsonp": "_callback",
        }
        get = self._get or requests.get
        try:
            response = get(DK_URL, params=params, headers=DK_HEADERS, timeout=DK_TIMEOUT)
            if response.status_code == 429:
                raise ProviderError("Dukascopy está limitando las peticiones. Espera un poco o usa Yahoo Finance.", 429)
            response.raise_for_status()
        except requests.Timeout as error:
            raise ProviderError("Dukascopy tardó demasiado en responder.", 504) from error
        except requests.RequestException as error:
            raise ProviderError("No se pudo contactar con Dukascopy.") from error
        return parse_dukascopy(response.text)


def _slice_days(candles: list[Candle], days: int | None) -> list[Candle]:
    """Recorta a ``days`` días contando desde la última vela (``None`` = todo)."""
    if not candles or days is None:
        return candles
    cutoff = candles[-1]["time"] - days * 86400
    return [c for c in candles if c["time"] > cutoff]


# ───────────────────────── Registro ─────────────────────────

PROVIDERS: dict[str, Provider] = {p.id: p for p in (YahooProvider(), AlphaVantageProvider(), DukascopyProvider())}


ALL_INTERVALS = frozenset(STANDARD_INTERVALS) | {c["value"] for p in PROVIDERS.values() for c in p.interval_choices}


def get_provider(provider_id: str | None) -> Provider:
    """El proveedor ``provider_id`` (o el de por defecto si viene vacío)."""
    pid = (provider_id or DEFAULT_PROVIDER).strip().lower()
    provider = PROVIDERS.get(pid)
    if provider is None:
        raise ProviderError(f"Proveedor «{pid[:20]}» desconocido.", 400)
    return provider


def catalog() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PROVIDERS.values()]
