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
   subsecciones del Graficador: "Gráfico", "Quant stats" y "Comparar"), usa ``kind="sections"`` o añade un nuevo
   valor de ``kind`` y su bloque correspondiente en
   ``app/core/templates/core/sidebar.html``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AppKind = Literal["sections", "blank"]

# Agrupación del sidebar: primero las herramientas financieras, luego las
# secciones de comunidad y personales. El orden de los grupos es el de esta tupla.
GROUPS: tuple[tuple[str, str], ...] = (
    ("herramientas", "Herramientas"),
    ("nuevas", "Nuevas secciones"),
)


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
    group: str = "herramientas"


# Orden del sidebar del área "App" (/app/): primero el graficador y después el
# resto de subapps. ``tests/core/test_navigation.py`` comprueba que toda app de
# ``INSTALLED_APPS`` con páginas tenga su entrada (como app o como subsección).
#
# Quant stats no es una app del sidebar: vive dentro del Graficador como sus
# subsecciones "Quant stats" y "Comparar", y comparte con él el activo elegido
# (las vistas pasan ``section_args={"ticker": ...}``).
APPS: tuple[App, ...] = (
    App(
        slug="graficador",
        name="Graficador",
        icon="📈",
        endpoint="graficador.index",
        kind="sections",
        sections=(
            AppSection(slug="grafico", name="Gráfico", icon="📈", endpoint="graficador.index"),
            AppSection(slug="quant-stats", name="Quant stats", icon="🧪", endpoint="quant_stats.fundamentales"),
            AppSection(slug="comparar", name="Comparar", icon="🔍", endpoint="quant_stats.revision"),
        ),
    ),
    App(slug="analisis-varianza", name="Análisis de varianza", icon="🧮", endpoint="varianza.index", kind="blank"),
    App(slug="pyportfolio-opt", name="Pyportfolio opt", icon="📐", endpoint="pyportfolio_opt.index", kind="blank"),
    App(slug="favoritos", name="Mis activos", icon="⭐", endpoint="favoritos.index", kind="blank"),
    App(slug="noticias", name="Noticias", icon="📰", endpoint="noticias.index", kind="blank"),
    App(slug="que-piensas-tu", name="¿Qué piensas tú?", icon="💬", endpoint="comunidad.index", kind="blank"),
    App(slug="pronosticador", name="Pronosticador", icon="🔮", endpoint="pronosticador.index", kind="blank"),
    App(slug="mi-perfil", name="Mi perfil", icon="👤", endpoint="mi_perfil.index", kind="blank", group="nuevas"),
    App(slug="personas", name="Personas", icon="👥", endpoint="personas.index", kind="blank", group="nuevas"),
)


def default_app() -> App:
    return APPS[0]


def get_app(slug: str) -> App | None:
    return next((a for a in APPS if a.slug == slug), None)
