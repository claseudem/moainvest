"""Radar de noticias del Inicio: termómetro de sentimiento y noticias vs. precio.

Módulo sin Flask (la "lógica" de la app, como un model de Django). Reúne en
una sola respuesta lo que pinta la sección «Radar de noticias» de ``/``:

- **Termómetro** (``pulse``): índice de 0 (miedo) a 100 (euforia) con el
  sentimiento de los titulares recientes. Cada titular pesa más cuanto más
  nuevo es (vida media de ``HALF_LIFE_HOURS`` horas): una noticia de hace una
  hora mueve el índice más que una de hace dos días.
- **Noticias vs. precio** (``asset_signal``): para cada activo, si el tono de
  sus noticias *confirma* el movimiento del precio de hoy o *diverge* de él
  (noticias buenas y el precio cae, o al revés). Una divergencia no es una
  señal de compra o venta: es una pregunta para investigar.
- **Titulares** con el porqué de su sentimiento (las palabras que lo deciden,
  de ``noticias.sentiment.signals``), para que el clasificador sea explicable.

El sentimiento es una estimación por palabras clave, no un modelo de IA ni una
recomendación de inversión; la interfaz lo dice así.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from app.core import news
from app.core.watchlists import Watchlist
from app.noticias import sentiment

HALF_LIFE_HOURS = 12
HEADLINE_LIMIT = 24
# Por encima de este tono medio (en valor absoluto) las noticias "opinan".
TONE_THRESHOLD = 0.2
# Movimientos de precio menores que este (en %) se consideran planos.
FLAT_MOVE_PCT = 0.15

SCORES = {"alcista": 1, "bajista": -1, "neutral": 0}

# (límite superior incluido, etiqueta, descripción corta)
PULSE_LEVELS = (
    (20, "Miedo extremo", "Dominan los titulares de caídas, recortes y temores."),
    (40, "Miedo", "Pesan más las noticias negativas que las positivas."),
    (60, "Neutral", "Las noticias buenas y malas se equilibran."),
    (80, "Optimismo", "Pesan más las noticias de subidas y buenos resultados."),
    (100, "Euforia", "Casi todos los titulares hablan de subidas y récords."),
)


def recency_weight(published_at: int, now: float) -> float:
    """1 para un titular de ahora mismo; 0,5 a las ``HALF_LIFE_HOURS`` horas; etc."""
    age_hours = max(0.0, (now - published_at) / 3600)
    return 0.5 ** (age_hours / HALF_LIFE_HOURS)


def weighted_tone(items: list[dict]) -> float | None:
    """Tono medio ponderado de ``items`` entre -1 (bajista) y 1 (alcista); ``None`` si no hay."""
    total = sum(i["peso"] for i in items)
    if not total:
        return None
    return sum(SCORES[i["sentimiento"]] * i["peso"] for i in items) / total


def pulse(items: list[dict]) -> dict[str, Any]:
    """Índice de 0 a 100, su etiqueta y el conteo por sentimiento."""
    counts = {label: sum(1 for i in items if i["sentimiento"] == label) for label in SCORES}
    tone = weighted_tone(items)
    value = None if tone is None else round(50 + 50 * tone)
    label, description = ("Sin datos", "Todavía no hay titulares recientes para medir el ánimo del mercado.")
    if value is not None:
        label, description = next((l, d) for limit, l, d in PULSE_LEVELS if value <= limit)
    return {"valor": value, "etiqueta": label, "descripcion": description, "conteo": counts, "total": len(items)}


def asset_signal(tone: float | None, change_percent: float | None) -> dict[str, str]:
    """Compara el tono de las noticias de un activo con su variación de hoy."""
    if tone is None:
        return {"estado": "sin-noticias", "texto": "Sin titulares recientes para este activo."}
    if change_percent is None:
        return {"estado": "sin-precio", "texto": "No tenemos el precio de hoy para compararlo."}
    news_up, news_down = tone >= TONE_THRESHOLD, tone <= -TONE_THRESHOLD
    price_up, price_down = change_percent >= FLAT_MOVE_PCT, change_percent <= -FLAT_MOVE_PCT
    if (news_up and price_up) or (news_down and price_down):
        return {"estado": "confirma", "texto": "El precio se mueve en la dirección de sus noticias."}
    if news_up and price_down:
        return {"estado": "divergencia", "texto": "Noticias positivas, pero el precio cae: ¿el mercado no se las cree?"}
    if news_down and price_up:
        return {"estado": "divergencia", "texto": "Noticias negativas, pero el precio sube: el mercado parece ignorarlas."}
    if not (news_up or news_down):
        return {"estado": "neutral", "texto": "Noticias mixtas: no marcan una dirección clara."}
    return {"estado": "neutral", "texto": "El precio apenas se mueve pese al tono de las noticias."}


def build(
    watchlist: Watchlist,
    quote_for: Callable[[str], Any],
    *,
    now: float | None = None,
    limit: int = HEADLINE_LIMIT,
) -> dict[str, Any]:
    """Termómetro, señales por activo y titulares de ``watchlist``.

    ``quote_for(ticker)`` devuelve un objeto con ``change_percent`` (por ejemplo
    ``market_data.get_quote``); si falla, ese activo queda "sin precio".
    """
    now = time.time() if now is None else now
    names = {s.ticker: s.display_name for s in watchlist.symbols}
    tickers = list(names)

    items = []
    for headline, related in news.feed(tickers, limit=limit, now=now):
        found = sentiment.signals(headline.title)
        items.append(
            {
                "id": headline.id,
                "titulo": headline.title,
                "fuente": headline.publisher,
                "url": headline.url,
                "publicado": news.utc_iso(headline.published_at),
                "activos": [{"ticker": t, "nombre": names.get(t, t)} for t in related if t in names],
                "sentimiento": sentiment.classify(headline.title),
                "senales": found,
                "peso": round(recency_weight(headline.published_at, now), 4),
            }
        )

    activos = []
    for ticker, name in names.items():
        own = [i for i in items if any(a["ticker"] == ticker for a in i["activos"])]
        tone = weighted_tone(own)
        try:
            change = quote_for(ticker).change_percent
        except Exception:  # Yahoo cae a menudo: el radar sigue sin ese precio
            change = None
        activos.append(
            {
                "ticker": ticker,
                "nombre": name,
                "tono": None if tone is None else round(tone, 3),
                "noticias": len(own),
                "variacion": None if change is None else round(change, 2),
                **asset_signal(tone, change),
            }
        )

    return {"pulso": pulse(items), "activos": activos, "noticias": items, "actualizado": news.utc_iso(int(now))}
