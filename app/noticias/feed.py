"""Feed de noticias: qué activos entran en cada filtro y titulares con sentimiento."""
from __future__ import annotations

from app.core import catalog, news
from app.noticias import images, sentiment

LIMIT = 30
MAX_TICKERS = 14

# "Todos": lo que mueve el mercado en general, más los activos del usuario.
HEADLINE_TICKERS = ("^GSPC", "^IXIC", "^DJI", "AAPL", "NVDA", "MSFT", "TSLA", "BTC-USD", "ETH-USD")

FILTERS = (("todos", "Todos"), ("mis-activos", "Mis activos")) + tuple((c.slug, c.name) for c in catalog.CATEGORIES)
FILTER_SLUGS = {slug for slug, _ in FILTERS}


def tickers_for(filtro: str, favorites: list[str]) -> list[str]:
    """Tickers cuyos titulares forman el feed de ``filtro``."""
    if filtro == "mis-activos":
        tickers = favorites
    elif filtro == "todos":
        tickers = [*favorites, *HEADLINE_TICKERS]
    else:
        tickers = catalog.tickers_in(filtro)
    return list(dict.fromkeys(tickers))[:MAX_TICKERS]


def tickers_for_scope(alcance: str, favorites: list[str]) -> list[str]:
    """Activos de una suscripción: 'favoritos' o 'todos' (y si no hay favoritos, todos)."""
    if alcance == "favoritos" and favorites:
        return tickers_for("mis-activos", favorites)
    return tickers_for("todos", favorites)


def build(tickers: list[str], names: dict[str, str] | None = None, *, limit: int = LIMIT, since: float | None = None) -> list[dict]:
    """Titulares de ``tickers`` (los más nuevos primero) con activos, sentimiento y portada."""
    names = names or {}
    items = []
    for headline, related in news.feed(tickers, limit=limit):
        if since is not None and headline.published_at <= since:
            continue
        items.append(
            {
                **headline.to_dict(),
                "activos": [{"ticker": t, "nombre": names.get(t) or catalog.name_for(t)} for t in related],
                "sentimiento": sentiment.classify(headline.title),
                # Portada reducida por nuestro proxy (``None`` → la tarjeta pinta un marcador).
                "imagen": images.proxy_urls(headline.image_url),
            }
        )
    return items
