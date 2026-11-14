"""Contenido de "Mi perfil": perfiles de interés, rutas de cinco niveles y XP.

El perfil representa los intereses de la persona, no necesariamente su carrera.
Cada perfil tiene su propia ruta de cinco niveles; cada nivel tiene una misión.
El progreso se guarda por usuario y por perfil en el navegador (ver
``static/mi_perfil.js``).

La progresión depende del aprendizaje y de las misiones completadas. Los XP son
puntos educativos: no representan dinero ni rentabilidad.
"""
from __future__ import annotations

from dataclasses import dataclass

# XP de cada misión según su dificultad.
XP_BY_DIFFICULTY = {"basica": 50, "intermedia": 100, "avanzada": 150}
DIFFICULTY_LABEL = {"basica": "Básica", "intermedia": "Intermedia", "avanzada": "Avanzada"}

# Cada nivel empieza cada 100 XP: el nivel n va de (n-1)·100 a n·100 XP.
XP_PER_LEVEL = 100


@dataclass(frozen=True, slots=True)
class Stage:
    """Nivel de la ruta y su misión: corta, educativa y completable."""

    name: str
    mission: str
    description: str
    objective: str
    steps: tuple[str, ...]
    difficulty: str

    @property
    def xp(self) -> int:
        return XP_BY_DIFFICULTY[self.difficulty]


@dataclass(frozen=True, slots=True)
class Profile:
    slug: str
    name: str
    icon: str
    description: str
    interest: str
    stages: tuple[Stage, ...]

    @property
    def title(self) -> str:
        return f"Tu camino como {self.name.lower()}" if self.slug == "inversionista" else f"Tu camino en {self.name.lower()}"


# Dificultad de los cinco niveles de cualquier ruta: dos básicos, dos intermedios y un avanzado.
_DIFFICULTIES = ("basica", "basica", "intermedia", "intermedia", "avanzada")


PROFILES: tuple[Profile, ...] = (
    Profile(
        slug="inversionista",
        name="Inversionista",
        icon="trending-up",
        description="Analiza mercados, comprende inversiones y aprende a gestionar portafolios.",
        interest="Mercados bursátiles, portafolios y riesgo",
        stages=(
            Stage(
                "Explorador",
                "Identificar qué es una acción",
                "Descubre qué representa una acción y qué mueve su precio.",
                "Reconocer qué derecho te da una acción y qué mueve su precio.",
                (
                    "Busca un activo en el Graficador, por ejemplo AAPL.",
                    "Anota qué empresa es y en qué mercado cotiza.",
                    "Explica con tus palabras qué significa ser accionista.",
                ),
                _DIFFICULTIES[0],
            ),
            Stage(
                "Analista",
                "Interpretar una variación porcentual y una tendencia",
                "Calcula cuánto cambia un precio y lee hacia dónde va.",
                "Calcular un cambio porcentual y reconocer la tendencia de un gráfico.",
                (
                    "Toma un precio inicial y uno final.",
                    "Calcula (final − inicial) ÷ inicial × 100.",
                    "Indica si la tendencia en 1A es alcista, bajista o lateral.",
                ),
                _DIFFICULTIES[1],
            ),
            Stage(
                "Trader",
                "Resolver un escenario de mercado",
                "Decide ante una noticia y una caída, con dinero virtual.",
                "Analizar un escenario bursátil y decidir con dinero virtual.",
                (
                    "Describe un escenario: una noticia y una caída de precio.",
                    "Decide con un capital ficticio qué harías y por qué.",
                    "Anota qué información te faltaría para confirmar la decisión.",
                ),
                _DIFFICULTIES[2],
            ),
            Stage(
                "Gestor",
                "Construir y evaluar un portafolio virtual",
                "Reparte un capital ficticio y mide el riesgo del conjunto.",
                "Armar un portafolio simulado y evaluar su riesgo.",
                (
                    "Reparte un capital ficticio entre tres activos de sectores distintos.",
                    "Compara su volatilidad con el análisis de varianza.",
                    "Explica qué pasaría si uno cayera un 20 %.",
                ),
                _DIFFICULTIES[3],
            ),
            Stage(
                "Gran inversionista",
                "Resolver un desafío integral",
                "Combina datos, diversificación, riesgo y planificación.",
                "Combinar análisis de datos, diversificación, riesgo y planificación.",
                (
                    "Define un objetivo y un horizonte de tiempo.",
                    "Diseña un portafolio diversificado y explica sus riesgos.",
                    "Presenta un plan de revisión periódica.",
                ),
                _DIFFICULTIES[4],
            ),
        ),
    ),
    Profile(
        slug="ingenieria",
        name="Ingeniería",
        icon="flask-conical",
        description="Explora la tecnología, la programación y el desarrollo de herramientas financieras.",
        interest="Programación, datos y sistemas",
        stages=(
            Stage(
                "Explorador",
                "Entender una serie de datos financieros",
                "Aprende a leer una tabla de precios diarios.",
                "Identificar qué representa cada columna de un precio diario.",
                (
                    "Abre una tabla de precios diarios.",
                    "Identifica fecha, apertura, cierre, máximo y mínimo.",
                    "Indica qué columna usarías para medir el cambio diario.",
                ),
                _DIFFICULTIES[0],
            ),
            Stage(
                "Programador",
                "Escribir una regla simple",
                "Traduce una idea de mercado en una regla lógica.",
                "Expresar una condición con lógica clara.",
                (
                    "Define una condición: si el cierre sube dos días seguidos.",
                    "Escríbela en pseudocódigo.",
                    "Prueba la regla con un caso real de la tabla.",
                ),
                _DIFFICULTIES[1],
            ),
            Stage(
                "Analista de datos",
                "Calcular una media móvil",
                "Suaviza una serie para ver su tendencia.",
                "Calcular un promedio móvil de cinco días.",
                (
                    "Toma los últimos cinco cierres.",
                    "Súmalos y divide entre cinco.",
                    "Repite desplazando una fecha.",
                ),
                _DIFFICULTIES[2],
            ),
            Stage(
                "Desarrollador",
                "Medir la volatilidad",
                "Mide qué tanto se mueve un activo, con código.",
                "Obtener una medida de dispersión de los cambios diarios.",
                (
                    "Calcula la variación diaria de un activo.",
                    "Obtén la desviación estándar de esas variaciones.",
                    "Explica qué significa un valor alto.",
                ),
                _DIFFICULTIES[3],
            ),
            Stage(
                "Innovador",
                "Automatizar un reporte",
                "Convierte un análisis en un proceso que se repite solo.",
                "Describir los pasos de un informe que se ejecute solo.",
                (
                    "Describe qué datos incluiría un informe semanal.",
                    "Enumera los pasos que harías con código.",
                    "Identifica qué parte podría ejecutarse cada día sin ti.",
                ),
                _DIFFICULTIES[4],
            ),
        ),
    ),
    Profile(
        slug="mercadeo",
        name="Mercadeo",
        icon="activity",
        description="Analiza tendencias, comportamiento de mercados y oportunidades de negocio.",
        interest="Tendencias, comportamiento y comunicación",
        stages=(
            Stage(
                "Observador",
                "Reconocer una tendencia de mercado",
                "Compara un sector en dos periodos y describe el cambio.",
                "Comparar un sector en dos periodos y describir el cambio.",
                (
                    "Compara un sector en dos periodos distintos.",
                    "Anota qué cambió y por qué podría ser.",
                    "Resume la tendencia en una frase.",
                ),
                _DIFFICULTIES[0],
            ),
            Stage(
                "Narrador",
                "Comprender el impacto de una noticia económica",
                "Conecta una noticia con los activos que afecta.",
                "Conectar una noticia con sus efectos probables en el mercado.",
                (
                    "Elige una noticia económica reciente.",
                    "Identifica qué empresas se verían afectadas.",
                    "Describe el efecto esperado y por qué.",
                ),
                _DIFFICULTIES[1],
            ),
            Stage(
                "Estratega de datos",
                "Comunicar un análisis de manera clara",
                "Resume una cifra financiera sin perder su sentido.",
                "Resumir un dato financiero sin perder su sentido.",
                (
                    "Toma una variación porcentual de un activo.",
                    "Escríbela en una frase que cualquiera entienda.",
                    "Indica qué contexto necesita para no malinterpretarse.",
                ),
                _DIFFICULTIES[2],
            ),
            Stage(
                "Explorador de oportunidades",
                "Identificar una oportunidad de negocio",
                "Distingue una oportunidad clara de una moda pasajera.",
                "Distinguir una oportunidad clara de una moda pasajera.",
                (
                    "Busca un sector con crecimiento sostenido.",
                    "Lista tres riesgos de invertir o competir ahí.",
                    "Decide si la oportunidad es clara y explica por qué.",
                ),
                _DIFFICULTIES[3],
            ),
            Stage(
                "Líder de comunicación",
                "Presentar un análisis en un plan de comunicación",
                "Redacta una conclusión con un dato y su fuente.",
                "Redactar una conclusión con un dato y su fuente.",
                (
                    "Escribe un titular con la conclusión.",
                    "Incluye un dato y su fuente.",
                    "Revísalo con una persona que no conozca el tema.",
                ),
                _DIFFICULTIES[4],
            ),
        ),
    ),
    Profile(
        slug="negocios",
        name="Negocios",
        icon="layers",
        description="Comprende empresas, economía y mercados nacionales e internacionales.",
        interest="Empresas, economía y mercados internacionales",
        stages=(
            Stage(
                "Lector de balances",
                "Leer el balance de una empresa",
                "Identifica las partes básicas de un balance.",
                "Identificar las partes básicas de un balance.",
                (
                    "Abre el informe de una empresa cotizada.",
                    "Identifica activos, pasivos y patrimonio.",
                    "Indica si la empresa tiene más deuda o más capital.",
                ),
                _DIFFICULTIES[0],
            ),
            Stage(
                "Observador económico",
                "Comprender el impacto de la economía en los mercados",
                "Mira a quién favorece y a quién perjudica una decisión.",
                "Explicar a quién favorece y a quién perjudica una decisión económica.",
                (
                    "Elige una decisión reciente sobre tasas de interés.",
                    "Describe a quién favorece y a quién perjudica.",
                    "Explica su efecto en los mercados.",
                ),
                _DIFFICULTIES[1],
            ),
            Stage(
                "Explorador global",
                "Comparar mercados de distintos países",
                "Compara dos índices de países distintos.",
                "Comparar dos índices y proponer una explicación de la diferencia.",
                (
                    "Elige dos índices de países distintos.",
                    "Compara sus variaciones en el último año.",
                    "Anota un factor que explique la diferencia.",
                ),
                _DIFFICULTIES[2],
            ),
            Stage(
                "Analista de divisas",
                "Entender el tipo de cambio",
                "Relaciona una divisa con el resultado de una empresa.",
                "Relacionar una divisa con el resultado de una exportadora.",
                (
                    "Consulta el precio de una divisa frente al dólar.",
                    "Explica cómo afecta a una empresa exportadora.",
                    "Compara su efecto con el de una importadora.",
                ),
                _DIFFICULTIES[3],
            ),
            Stage(
                "Estratega global",
                "Analizar una empresa internacional",
                "Concluye con riesgos y oportunidades de una empresa global.",
                "Concluir con riesgos y oportunidades de una empresa global.",
                (
                    "Elige una empresa con operaciones en varios países.",
                    "Revisa su evolución y su sector.",
                    "Presenta una conclusión con riesgos y oportunidades.",
                ),
                _DIFFICULTIES[4],
            ),
        ),
    ),
    Profile(
        slug="diseno",
        name="Diseño",
        icon="layers",
        description="Transforma información financiera en experiencias visuales claras y útiles.",
        interest="Visualización, experiencia y comunicación visual",
        stages=(
            Stage(
                "Observador visual",
                "Leer una gráfica de precios",
                "Distingue si un precio sube, baja o se mantiene.",
                "Distinguir si un precio sube, baja o se mantiene lateral.",
                (
                    "Abre la gráfica de un activo.",
                    "Cambia el rango a 1A y observa el sentido general.",
                    "Indica si la tendencia es alcista, bajista o lateral.",
                ),
                _DIFFICULTIES[0],
            ),
            Stage(
                "Lector de gráficas",
                "Elegir el gráfico adecuado para un dato",
                "Relaciona cada dato con el gráfico que mejor lo muestra.",
                "Relacionar un tipo de dato con el gráfico que mejor lo muestra.",
                (
                    "Lista tres datos financieros distintos.",
                    "Asigna a cada uno un tipo de gráfico y justifica la elección.",
                    "Descarta el gráfico que confunda al lector.",
                ),
                _DIFFICULTIES[1],
            ),
            Stage(
                "Diseñador de datos",
                "Diseñar una visualización con colores con significado",
                "Usa el color para subidas y bajadas sin confundir.",
                "Usar color para comunicar subidas y bajadas sin confundir.",
                (
                    "Elige dos colores para subidas y bajadas.",
                    "Comprueba que se distinguen también en escala de grises.",
                    "Añade una leyenda que explique cada color.",
                ),
                _DIFFICULTIES[2],
            ),
            Stage(
                "Comunicador visual",
                "Presentar un dato con su contexto",
                "Acompaña una cifra con la base de comparación.",
                "Acompañar una cifra con la base de comparación que le da sentido.",
                (
                    "Toma una variación porcentual de un activo.",
                    "Muestra el valor inicial y el final junto al porcentaje.",
                    "Indica el periodo de comparación en el título.",
                ),
                _DIFFICULTIES[3],
            ),
            Stage(
                "Director de experiencia",
                "Diseñar un panel de indicadores",
                "Organiza varios indicadores para leerlos de un vistazo.",
                "Organizar varios indicadores en un panel que se lea de un vistazo.",
                (
                    "Elige cuatro indicadores para un panel.",
                    "Ordénalos del más importante al menos importante.",
                    "Revisa que cada uno tenga unidad y fecha.",
                ),
                _DIFFICULTIES[4],
            ),
        ),
    ),
    Profile(
        slug="analisis-datos",
        name="Análisis de Datos",
        icon="chart-column",
        description="Interpreta métricas, indicadores y patrones para comprender mejor los mercados.",
        interest="Métricas, estadística e indicadores",
        stages=(
            Stage(
                "Recolector",
                "Preparar una serie de precios",
                "Revisa una serie antes de analizarla.",
                "Ordenar y revisar una serie de precios antes de analizarla.",
                (
                    "Abre una serie de precios diarios.",
                    "Revisa que no falten fechas ni haya valores repetidos.",
                    "Anota cuántos datos quedan después de la revisión.",
                ),
                _DIFFICULTIES[0],
            ),
            Stage(
                "Explorador estadístico",
                "Calcular rendimientos diarios",
                "Obtiene la variación diaria de un activo y la resume.",
                "Obtener la variación diaria de un activo y resumirla.",
                (
                    "Calcula la variación porcentual de cada día.",
                    "Obtén el promedio de esas variaciones.",
                    "Explica qué dice el promedio y qué no dice.",
                ),
                _DIFFICULTIES[1],
            ),
            Stage(
                "Modelador",
                "Medir la relación entre dos activos",
                "Interpreta la correlación entre dos series.",
                "Interpretar una correlación entre dos series de precios.",
                (
                    "Elige dos activos de un mismo sector.",
                    "Calcula su correlación con los rendimientos diarios.",
                    "Explica qué significa un valor cercano a 1.",
                ),
                _DIFFICULTIES[2],
            ),
            Stage(
                "Validador",
                "Probar una regla con datos pasados",
                "Comprueba si una regla simple habría funcionado.",
                "Comprobar si una regla simple habría funcionado en el pasado.",
                (
                    "Define una regla simple con condiciones claras.",
                    "Aplícala a un periodo histórico.",
                    "Anota los aciertos y los errores, y di qué limitación tiene.",
                ),
                _DIFFICULTIES[3],
            ),
            Stage(
                "Analista experto",
                "Presentar un análisis con sus limitaciones",
                "Comunica conclusiones junto con los límites de los datos.",
                "Comunicar conclusiones con los datos y sus límites.",
                (
                    "Escribe tres conclusiones con sus datos.",
                    "Indica una limitación de cada conclusión.",
                    "Propón qué dato adicional mejoraría el análisis.",
                ),
                _DIFFICULTIES[4],
            ),
        ),
    ),
)

PROFILES_BY_SLUG = {profile.slug: profile for profile in PROFILES}


def level_for_xp(xp: int, total_levels: int) -> tuple[int, int | None]:
    """Nivel alcanzado con ``xp`` y XP del siguiente nivel (``None`` en el último)."""
    level = min(total_levels, xp // XP_PER_LEVEL + 1)
    next_threshold = None if level >= total_levels else level * XP_PER_LEVEL
    return level, next_threshold


def profiles_payload() -> list[dict]:
    """Perfiles, niveles y misiones en el formato que lee ``static/mi_perfil.js``."""
    return [
        {
            "slug": profile.slug,
            "name": profile.name,
            "title": profile.title,
            "icon": profile.icon,
            "description": profile.description,
            "interest": profile.interest,
            "stages": [
                {
                    "name": stage.name,
                    "mission": stage.mission,
                    "description": stage.description,
                    "objective": stage.objective,
                    "steps": list(stage.steps),
                    "difficulty": DIFFICULTY_LABEL[stage.difficulty],
                    "xp": stage.xp,
                }
                for stage in profile.stages
            ],
        }
        for profile in PROFILES
    ]
