"""Contenido estático: los equipos de MOAINVEST (se muestran en su presentación).

Los perfiles y las rutas viven en ``app/mi_perfil/content.py``, porque son
personales.
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
