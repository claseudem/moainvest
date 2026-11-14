"""App "Alertas": notificaciones de movimientos bruscos con contexto de noticias.

No tiene páginas propias (por eso no aparece en el sidebar): aporta la campana
de la barra superior (``templates/alertas/_bell.html``, incluida en
``core/base.html``), su CSS y su JS. Los datos van por ``api.py``.
"""
from __future__ import annotations

from flask import Blueprint

from app.core.watchlists import WATCHLISTS

bp = Blueprint(
    "alertas",
    __name__,
    url_prefix="/app/alertas",
    template_folder="templates",
    static_folder="static",
)


@bp.app_context_processor
def inject_alert_watchlists() -> dict:
    """Watchlists para los interruptores del diálogo de configuración de la campana."""
    return {"watchlists_for_alerts": WATCHLISTS}
