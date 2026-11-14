"""Contenido estático de PERSONAS (comunidad): equipos y propósito.

Los perfiles y las rutas viven en ``app/mi_perfil/content.py``, porque son
personales. Los equipos se muestran en la presentación de MOAINVEST; esta
sección muestra a los demás: el directorio, los filtros y los indicadores.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Team:
    name: str
    description: str
    icon: str


# Equipos, sin nombres individuales todavía: se agregarán después con sus fotografías.
TEAMS: tuple[Team, ...] = (
    Team("Equipo Ingeniería", "Desarrollo tecnológico y programación.", "smartphone"),
    Team("Equipo Negocios Internacionales", "Estrategia empresarial y mercados globales.", "layers"),
    Team("Equipo Mercadeo", "Comunicación, posicionamiento y crecimiento de comunidad.", "activity"),
    Team("Equipo Finanzas", "Análisis financiero e inversión.", "trending-up"),
    Team("Equipo Análisis de Datos", "Métricas, indicadores y visualización.", "chart-column"),
)

PILLARS: tuple[tuple[str, str, str], ...] = (
    (
        "Nuestro propósito",
        "Hacer que el conocimiento financiero sea más comprensible y accesible para las personas.",
        "target",
    ),
    (
        "Nuestra visión",
        "Construir una comunidad que aprenda a comprender los mercados, interpretar información y desarrollar habilidades financieras.",
        "eye",
    ),
    (
        "Nuestra filosofía",
        "Creemos que el crecimiento comienza con el conocimiento, la práctica y la constancia.",
        "layers",
    ),
)
