"""Crecimiento de la comunidad y sus hitos de desbloqueo.

``member_count`` devuelve la cifra que muestra la página. Hoy es de
demostración: no existe una base de datos de usuarios conectada, así que no
se inventa ningún dato real. Para conectarla, reemplaza el cuerpo de
``member_count`` por una consulta a la tabla de usuarios (InsForge) y devuelve
``source="live"``.
"""
from __future__ import annotations

from dataclasses import dataclass

# DEMO: cifra de ejemplo para la barra de progreso. No son usuarios registrados.
DEMO_MEMBER_COUNT = 137


@dataclass(frozen=True, slots=True)
class Milestone:
    target: int
    title: str
    unlocks: str


MILESTONES: tuple[Milestone, ...] = (
    Milestone(100, "Lanzamiento inicial", "Lanzamiento inicial de la comunidad."),
    Milestone(250, "Nuevas herramientas", "Nuevas herramientas de análisis."),
    Milestone(500, "Contenido avanzado", "Contenido educativo avanzado."),
    Milestone(1000, "Modo comunidad", "Modo comunidad."),
    Milestone(2500, "Expansión", "Expansión de herramientas y mercados."),
)


def member_count() -> tuple[int, str]:
    """Número de integrantes y su origen: ``"demo"`` o ``"live"``."""
    return DEMO_MEMBER_COUNT, "demo"


def milestone_states(count: int) -> list[dict]:
    """Cada hito con su estado: ``completado``, ``proximo`` o ``bloqueado``.

    Solo el primer hito pendiente es ``proximo``; los siguientes quedan
    ``bloqueado``. ``percent`` es el avance hacia ese hito.
    """
    states: list[dict] = []
    next_seen = False
    for milestone in MILESTONES:
        if count >= milestone.target:
            state = "completado"
        elif not next_seen:
            state = "proximo"
            next_seen = True
        else:
            state = "bloqueado"
        states.append(
            {
                "target": milestone.target,
                "title": milestone.title,
                "unlocks": milestone.unlocks,
                "state": state,
                "percent": min(100, round(count * 100 / milestone.target)),
            }
        )
    return states


def next_target(count: int) -> int | None:
    return next((m.target for m in MILESTONES if count < m.target), None)


# DEMO: distribución por perfil de la cifra de ejemplo (suma DEMO_MEMBER_COUNT).
# Son cifras demostrativas: no corresponden a usuarios registrados.
DEMO_BY_PROFILE = {
    "inversionista": 52,
    "ingenieria": 31,
    "mercadeo": 18,
    "negocios": 14,
    "diseno": 12,
    "analisis-datos": 10,
}

# DEMO: nuevos integrantes y crecimiento de la última semana (ejemplo).
DEMO_NEW_THIS_WEEK = 9
DEMO_GROWTH_PERCENT = 7


def members() -> list[dict]:
    """Integrantes del directorio, solo los que autorizaron hacer público su perfil.

    Cada integrante trae únicamente campos públicos: ``name``, ``initial``,
    ``profile`` (slug), ``level`` (número), ``level_name``, ``interests``,
    ``bio`` y ``achievements`` (los logros que la persona decidió compartir).
    Nunca XP detallado, correo ni datos sensibles.

    Sin base de datos de usuarios no hay integrantes reales: devuelve una lista
    vacía. Para conectarla, leer de la tabla de usuarios filtrando por
    ``public = true`` y devolver solo esos campos.
    """
    return []
