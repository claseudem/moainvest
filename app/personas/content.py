"""Contenido de la sección PERSONAS: equipo, niveles, misiones y progreso.

Todo lo de aquí es de demostración y educativo. Los nombres del equipo son
marcadores hasta que se definan los integrantes reales, y el progreso
(``DEMO_PROGRESS``) no se guarda en ningún sitio: cuando exista una base de
datos de usuarios, sustituye ``DEMO_PROGRESS`` por la consulta del usuario.

Los personajes son representaciones educativas. Completar niveles no garantiza
riqueza ni éxito financiero.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# XP que se gana al completar la misión de un nivel (y que hace falta para
# desbloquear el siguiente).
XP_PER_LEVEL = 100


@dataclass(frozen=True, slots=True)
class TeamMember:
    name: str
    career: str
    role: str


# DEMO: integrantes de marcador. Reemplazar por los reales (nombre, foto o avatar).
TEAM: tuple[TeamMember, ...] = (
    TeamMember("Nombre por definir", "Ingeniería", "Desarrollo de la plataforma"),
    TeamMember("Nombre por definir", "Negocios Internacionales", "Estrategia y mercados globales"),
    TeamMember("Nombre por definir", "Mercadeo", "Comunicación y crecimiento de la comunidad"),
    TeamMember("Nombre por definir", "Finanzas", "Contenido sobre inversión"),
    TeamMember("Nombre por definir", "Análisis de Datos", "Métricas e indicadores"),
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


@dataclass(frozen=True, slots=True)
class Level:
    number: int
    name: str
    profile: str
    icon: str
    description: str
    mission: str
    mission_example: str


LEVELS: tuple[Level, ...] = (
    Level(
        1,
        "El Estudiante",
        "Estudiante universitario de Ingeniería",
        "file-text",
        "Representa la curiosidad, la tecnología, la lógica y el interés por comprender cómo funcionan los datos.",
        "Conocer la plataforma y aprender los conceptos básicos de los mercados financieros.",
        "Identificar qué es una acción.",
    ),
    Level(
        2,
        "El Estratega",
        "Estudiante de Negocios Internacionales",
        "layers",
        "Representa la visión empresarial, los mercados globales y la comprensión de la economía.",
        "Comprender cómo los acontecimientos económicos pueden influir en los mercados.",
        "Comprender el impacto de una noticia económica.",
    ),
    Level(
        3,
        "El Creador",
        "Estudiante de Mercadeo",
        "send",
        "Representa la comunicación, el análisis del comportamiento y la capacidad de identificar oportunidades.",
        "Aprender a interpretar información financiera y comunicar un análisis de manera clara.",
        "Interpretar una variación porcentual.",
    ),
    Level(
        4,
        "El Analista",
        "Analista financiero",
        "search",
        "Representa la lectura de datos y la capacidad de convertir gráficos en conclusiones.",
        "Interpretar gráficos, identificar tendencias y comprender indicadores financieros.",
        "Reconocer una tendencia en un gráfico.",
    ),
    Level(
        5,
        "El Estratega Financiero",
        "Analista de inversiones",
        "chart-column",
        "Representa el paso de analizar activos sueltos a pensar en conjuntos de inversiones.",
        "Construir un portafolio simulado y comprender la diversificación y la gestión del riesgo.",
        "Identificar los riesgos de una inversión.",
    ),
    Level(
        6,
        "El Trader",
        "Operador profesional de mercados",
        "candlestick-chart",
        "Representa la toma de decisiones con información incompleta y bajo presión de tiempo.",
        "Analizar escenarios bursátiles y tomar decisiones en un simulador con dinero virtual.",
        "Resolver un escenario de mercado.",
    ),
    Level(
        7,
        "El Gestor",
        "Gestor de inversiones",
        "sigma",
        "Representa la administración de portafolios a largo plazo y la evaluación de resultados.",
        "Administrar un portafolio simulado, evaluar resultados y desarrollar estrategias de largo plazo.",
        "Evaluar el resultado de un portafolio frente a su objetivo.",
    ),
    Level(
        8,
        "El Gran Inversionista",
        "Máximo nivel de desarrollo financiero",
        "star",
        "Inspirado en grandes figuras históricas de las finanzas, como J. P. Morgan. Transmite liderazgo, visión estratégica y capacidad de gestionar grandes inversiones.",
        "Resolver un desafío integral que combine análisis de datos, diversificación, gestión de riesgos y planificación financiera.",
        "Diseñar un plan financiero completo con un escenario de riesgo.",
    ),
)

LEVELS_BY_NUMBER = {level.number: level for level in LEVELS}


@dataclass(frozen=True, slots=True)
class Progress:
    """Progreso de una persona: niveles con misión completada y XP parcial."""

    completed: frozenset[int] = field(default_factory=frozenset)
    partial_xp: int = 0

    @property
    def xp(self) -> int:
        return len(self.completed) * XP_PER_LEVEL + self.partial_xp

    @property
    def current(self) -> int | None:
        """Primer nivel sin completar, o ``None`` si ya están todos."""
        return next((n for n in LEVELS_BY_NUMBER if n not in self.completed), None)


# DEMO: progreso de ejemplo para mostrar los tres estados (completado, actual y
# bloqueado) y la barra de XP. No es un usuario real.
DEMO_PROGRESS = Progress(completed=frozenset({1}), partial_xp=20)


def level_state(number: int, progress: Progress) -> str:
    """Estado de un nivel: ``desbloqueado``, ``actual`` o ``bloqueado``."""
    if number in progress.completed:
        return "desbloqueado"
    if number == progress.current:
        return "actual"
    return "bloqueado"


def level_requirement(number: int) -> str:
    if number == 1:
        return "Punto de partida: no requiere nada."
    return f"Completar la misión de «{LEVELS_BY_NUMBER[number - 1].name}» (+{XP_PER_LEVEL} XP)."
