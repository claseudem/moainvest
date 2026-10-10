"""API del Graficador: catálogo de indicadores técnicos y su cálculo con TA-Lib."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.api import ALLOWED_INTERVALS, ALLOWED_RANGES
from app.graficador import indicators, providers
from app.graficador.views import TICKER_RE

# Los de ``core`` más los que añade algún proveedor (segundos, 10m y 4h de Dukascopy).
INTERVALS = ALLOWED_INTERVALS | providers.ALL_INTERVALS

bp = Blueprint("graficador_api", __name__, url_prefix="/api/graficador")


@bp.get("/indicators")
def indicator_catalog():
    """Indicadores disponibles: parámetros, salidas, categoría y paleta."""
    return jsonify(indicators.catalog())


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def _fetch_candles(provider_id: str | None, ticker: str, range_: str, interval: str):
    """Velas del proveedor elegido; lanza ``ProviderError`` si no puede darlas."""
    provider = providers.get_provider(provider_id)
    reason = provider.unavailable_reason()
    if reason:
        raise providers.ProviderError(reason, 503)
    if not provider.supports(interval):
        raise providers.ProviderError(f"{provider.name} no admite la periodicidad «{interval}».", 422)
    return provider.get_candles(ticker, range_, interval)


@bp.get("/providers")
def provider_catalog():
    """Proveedores de precios: id, nombre, si están disponibles y por qué no."""
    return jsonify({"default": providers.DEFAULT_PROVIDER, "providers": providers.catalog()})


@bp.get("/<ticker>/candles")
def candles(ticker: str):
    """Velas OHLCV de ``ticker`` con el proveedor elegido (``?provider=alphavantage``)."""
    ticker = ticker.strip().upper()
    range_ = request.args.get("range", "6mo")
    interval = request.args.get("interval", "1d")
    if not TICKER_RE.match(ticker):
        return _error(f"«{ticker[:20]}» no es un ticker válido", 400)
    if range_ not in ALLOWED_RANGES or interval not in INTERVALS:
        return _error("range o interval inválidos", 400)
    try:
        return jsonify(_fetch_candles(request.args.get("provider"), ticker, range_, interval))
    except providers.ProviderError as error:
        return _error(error.message, error.status)


@bp.get("/<ticker>/indicators")
def compute_indicators(ticker: str):
    """Calcula uno o varios indicadores sobre las velas de ``ticker``.

    ?range=6mo&interval=1d&ind=sma:20&ind=macd:12,26,9

    Devuelve ``{"time": [...], "indicators": [{"spec", "outputs": {clave: [...]}}]}``
    con los valores alineados con ``time`` (``null`` mientras el indicador se
    calienta). Los indicadores se calculan sobre más historia que la visible
    para que una SMA(200) ya tenga valor en la primera vela del gráfico.
    """
    ticker = ticker.strip().upper()
    range_ = request.args.get("range", "6mo")
    interval = request.args.get("interval", "1d")
    specs = request.args.getlist("ind")

    if not TICKER_RE.match(ticker):
        return jsonify({"error": f"«{ticker[:20]}» no es un ticker válido"}), 400
    if range_ not in ALLOWED_RANGES or interval not in INTERVALS:
        return jsonify({"error": "range o interval inválidos"}), 400
    if not specs:
        return jsonify({"error": "Indica al menos un indicador (ind=sma:20)"}), 400
    if len(specs) > indicators.MAX_INDICATORS:
        return jsonify({"error": f"Máximo {indicators.MAX_INDICATORS} indicadores a la vez"}), 400

    try:
        for spec in specs:
            indicators.parse_spec(spec)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    provider_id = request.args.get("provider")
    try:
        visible = _fetch_candles(provider_id, ticker, range_, interval)
        if not visible:
            return jsonify(indicators.compute_series([], specs))
        warm = indicators.warmup_range(range_, interval)
        history = visible if warm == range_ else _fetch_candles(provider_id, ticker, warm, interval)
    except providers.ProviderError as error:
        return _error(error.message, error.status)
    return jsonify(indicators.compute_series(history or visible, specs, since=visible[0]["time"]))
