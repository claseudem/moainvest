"""API de la app "Pyportfolio opt": retornos esperados (JSON) y su gráfica (PNG)."""
from __future__ import annotations

import re
from typing import Any

from flask import Blueprint, Response, jsonify, request

from app.pyportfolio_opt import expected

bp = Blueprint("pyportfolio_opt_api", __name__, url_prefix="/api/pyportfolio-opt")

MAX_TICKERS = 10

# Períodos de histórico admitidos (subconjunto de ``ALLOWED_RANGES`` de core):
# con menos de un año la anualización de 252 días no tiene sentido.
ALLOWED_PERIODS = ("1y", "2y", "5y", "10y", "max")

# ``method``: una metodología o "both" para compararlas.
METHOD_CHOICES = {"both": tuple(expected.METHODS), **{m: (m,) for m in expected.METHODS}}

SPAN_MIN, SPAN_MAX = 2, 5000

# Tickers de Yahoo: letras, números y ``^ = . -`` (``^GSPC``, ``BTC-USD``, ``EURUSD=X``).
TICKER_RE = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")


def _flag(name: str, default: bool) -> bool:
    value = request.args.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "on", "si", "sí")


def _parse_args() -> tuple[dict[str, Any] | None, str | None]:
    """Valida la query string; devuelve (parámetros, None) o (None, error)."""
    tickers = list(
        dict.fromkeys(t.strip().upper() for t in request.args.get("tickers", "").split(",") if t.strip())
    )
    if not tickers:
        return None, "Indica al menos un ticker"
    if len(tickers) > MAX_TICKERS:
        return None, f"Máximo {MAX_TICKERS} tickers a la vez"
    invalid = [t for t in tickers if not TICKER_RE.match(t)]
    if invalid:
        return None, f"Ticker inválido: {', '.join(invalid)}"

    period = request.args.get("period", "5y")
    if period not in ALLOWED_PERIODS:
        return None, "period inválido"

    method = request.args.get("method", "both")
    if method not in METHOD_CHOICES:
        return None, "method inválido (historical, ema o both)"

    try:
        span = int(request.args.get("span", expected.DEFAULT_SPAN))
    except ValueError:
        return None, "span debe ser un número entero"
    if not SPAN_MIN <= span <= SPAN_MAX:
        return None, f"span debe estar entre {SPAN_MIN} y {SPAN_MAX}"

    return {
        "tickers": tickers,
        "period": period,
        "methods": METHOD_CHOICES[method],
        "span": span,
        "compounding": _flag("compounding", True),
        "log_returns": _flag("log_returns", False),
    }, None


def _compute():
    params, error = _parse_args()
    if error:
        return None, (jsonify({"error": error}), 400)
    try:
        return expected.compute_expected_returns(**params), None
    except expected.ExpectedReturnsError as exc:
        return None, (jsonify({"error": str(exc)}), 404)


@bp.get("/expected-returns")
def expected_returns():
    """Retorno esperado anualizado por ticker y metodología.

    ?tickers=AAPL,MSFT&period=5y&method=both&span=500&compounding=1&log_returns=0
    """
    result, error = _compute()
    if error:
        return error
    return jsonify(result.to_dict())


@bp.get("/expected-returns.png")
def expected_returns_chart():
    """Barras con el retorno esperado de cada ticker (mismos parámetros que el JSON)."""
    result, error = _compute()
    if error:
        return error
    return Response(expected.render_expected_returns_chart(result), mimetype="image/png")
