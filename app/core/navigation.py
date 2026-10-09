"""Registro de "apps" de primer nivel del sidebar.

Este es el nivel de extensión más alto del panel: cada ``App`` es una
sección independiente (por ejemplo "Gráficas" o "Análisis de varianza"),
con su propio icono, su propio blueprint/rutas y, opcionalmente, su propia
navegación anidada en el sidebar (ver ``kind``).

Para añadir una nueva app:

1. Añade una entrada aquí con un ``endpoint`` (el ``blueprint.vista`` de
   Flask que sirve como página principal de esa app).
2. Crea su paquete en ``app/<app>/`` (con su ``views.py``) y añádela a
   ``INSTALLED_APPS`` en ``app/__init__.py``.
3. Si la app necesita su propia navegación anidada en el sidebar (como las
   subsecciones de "Quant stats"), usa ``kind="sections"`` o añade un nuevo
   valor de ``kind`` y su bloque correspondiente en
   ``app/core/templates/core/sidebar.html``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AppKind = Literal["sections", "blank"]


@dataclass(frozen=True, slots=True)
class AppSection:
    """Subsección fija de una app de ``kind="sections"`` (una página propia)."""

    slug: str
    name: str
    icon: str
    endpoint: str


@dataclass(frozen=True, slots=True)
class App:
    slug: str
    name: str
    icon: str
    endpoint: str
    kind: AppKind = "blank"
    sections: tuple[AppSection, ...] = ()


# Orden del sidebar del área "App" (/app/): primero el graficador, luego
# Informes y después el resto de subapps. ``tests/core/test_navigation.py``
# comprueba que toda app de ``INSTALLED_APPS`` con páginas tenga su entrada.
APPS: tuple[App, ...] = (
    App(slug="graficador", name="Graficador", icon="📈", endpoint="graficador.index", kind="blank"),
    App(slug="informes", name="Informes", icon="📨", endpoint="informes.index", kind="blank"),
    App(slug="analisis-varianza", name="Análisis de varianza", icon="🧮", endpoint="varianza.index", kind="blank"),
    App(
        slug="quant-stats",
        name="Quant stats",
        icon="🧪",
        endpoint="quant_stats.index",
        kind="sections",
        sections=(
            AppSection(
                slug="fundamentales",
                name="Gráficas y fundamentales estadísticos",
                icon="📊",
                endpoint="quant_stats.fundamentales",
            ),
            AppSection(slug="revision", name="Revisión analítica", icon="🔍", endpoint="quant_stats.revision"),
        ),
    ),
    App(slug="regresion", name="Regresión ML", icon="📉", endpoint="regresion.index", kind="blank"),
)


def default_app() -> App:
    return APPS[0]


def get_app(slug: str) -> App | None:
    return next((a for a in APPS if a.slug == slug), None)
