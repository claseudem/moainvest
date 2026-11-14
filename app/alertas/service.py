"""Disparador de alertas: cotizaciones → reglas → titular de contexto → InsForge.

Se ejecuta de dos formas:

* **Bajo demanda**: ``GET /api/alertas`` (la campana lo consulta al cargar la
  página y cada pocos minutos). Para no recargar Yahoo Finance, cada usuario se
  evalúa como mucho una vez cada ``SCAN_INTERVAL`` segundos por proceso.
* **Programado**: ``flask alertas-scan`` (cron o un *schedule* de InsForge)
  evalúa a todos los usuarios que guardaron preferencias, aunque no tengan la
  app abierta.

Las cotizaciones y los titulares son comunes a todos los usuarios y ya se
cachean (``market_data`` y ``news``). Lo único por usuario son el umbral, las
watchlists silenciadas y lo ya notificado.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app.alertas import rules, store
from app.core import news
from app.alertas.rules import Settings, Trigger
from app.core import market_data
from app.core.market_data import Quote
from app.core.watchlists import WATCHLISTS

SCAN_INTERVAL = 120
MAX_WORKERS = 8

_last_scan: dict[str, float] = {}


def _safe_quote(ticker: str) -> Quote | None:
    try:
        return market_data.get_quote(ticker)
    except Exception:
        return None


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    """Cotizaciones en paralelo; los tickers que fallan simplemente no aparecen."""
    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tickers))) as pool:
        quotes = dict(zip(tickers, pool.map(_safe_quote, tickers)))
    return {t: q for t, q in quotes.items() if q is not None}


def _names() -> dict[str, str]:
    return {s.ticker: s.display_name for w in WATCHLISTS for s in w.symbols}


def headline_for(trigger: Trigger) -> dict | None:
    """Titular de contexto de la alerta, o ``None`` si no hay ninguno relevante y reciente."""
    try:
        headline = news.best_headline(trigger.ticker, trigger.name)
    except Exception:
        return None
    if headline is None:
        return None
    return {**headline.to_dict(), "published_at_iso": news.utc_iso(headline.published_at)}


def scan_user(user_id: str, settings: Settings | None = None, *, force: bool = False) -> list[Trigger]:
    """Evalúa los activos del usuario y guarda las alertas nuevas. Devuelve las creadas.

    Lanza ``store.StoreError`` si InsForge no responde.
    """
    now = time.time()
    if not force and now - _last_scan.get(user_id, 0) < SCAN_INTERVAL:
        return []
    _last_scan[user_id] = now

    if settings is None:
        settings, _ = store.get_settings(user_id)
    watched = rules.watched_tickers(WATCHLISTS, settings)
    quotes = fetch_quotes(list(watched))
    sessions = {s for s in (rules.session_key(q) for q in quotes.values()) if s}
    already = store.sent_keys(user_id, sessions)
    triggers = rules.evaluate(WATCHLISTS, settings, quotes, already, names=_names())

    created = []
    for trigger in triggers:
        try:
            store.insert_alert(user_id, trigger, headline_for(trigger))
        except store.StoreError:
            # Otro proceso (gunicorn tiene varios workers) pudo insertar la misma
            # alerta a la vez: la restricción UNIQUE la rechaza y seguimos.
            continue
        created.append(trigger)
    return created


def forget_scan(user_id: str) -> None:
    """Permite volver a evaluar enseguida (p. ej. al cambiar el umbral)."""
    _last_scan.pop(user_id, None)
