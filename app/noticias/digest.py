"""Resumen de noticias por correo para los suscritos con ``via_email``.

Lo ejecuta ``flask noticias-digest`` (cron, p. ej. cada mañana). Cada usuario
recibe solo los titulares publicados después de su último envío (o de las
últimas 24 h la primera vez); si no hay nada nuevo, no se le escribe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.email import EmailError, send_email
from app.noticias import feed, subscriptions
from app.noticias.api import favorites_of
from config import Config

MAX_ITEMS = 10
FIRST_WINDOW = timedelta(hours=24)

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates" / "noticias" / "emails"),
    autoescape=select_autoescape(["html"]),
)


@dataclass(slots=True)
class DigestResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0


def render(items: list[dict], alcance: str, now: datetime) -> tuple[str, str]:
    subject = f"{Config.SITE_NAME} · {len(items)} noticia{'s' if len(items) != 1 else ''} de tus activos · {now:%d/%m/%Y}"
    html = _env.get_template("digest.html").render(
        subject=subject,
        site_name=Config.SITE_NAME,
        items=items,
        alcance="todos los activos" if alcance == "todos" else "tus favoritos",
        generated_at=now,
        format_time=lambda epoch: datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%d/%m %H:%M"),
    )
    return subject, html


def run(now: datetime | None = None) -> DigestResult:
    now = now or datetime.now(timezone.utc)
    result = DigestResult()
    for user_id, sub in subscriptions.email_subscribers():
        since_dt = datetime.fromisoformat(sub.ultimo_envio) if sub.ultimo_envio else now - FIRST_WINDOW
        favorites = [f["ticker"] for f in favorites_of(user_id)]
        tickers = feed.tickers_for_scope(sub.alcance, favorites)
        items = feed.build(tickers, since=since_dt.timestamp(), limit=MAX_ITEMS * 3)[:MAX_ITEMS]
        if not items or not sub.email:
            result.skipped += 1
            continue
        subject, html = render(items, sub.alcance, now)
        try:
            send_email(sub.email, subject, html)
        except EmailError:
            result.failed += 1
            continue
        subscriptions.mark_sent(user_id, now)
        result.sent += 1
    return result
