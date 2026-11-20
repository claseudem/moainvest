# MoaiInvest

Panel de precios en vivo, estilo TradingView, construido solo con **Flask**
(organizado en **apps con blueprints, al estilo Django**) y **UV** para la
gestión del proyecto/dependencias (sin Node). El sitio principal,
**MOAINVEST** (Resumen y Gráficas), se sirve en la raíz con su
diseño rojo.
Descarga los precios de **Yahoo Finance** (vía `yfinance`) y los dibuja con
[lightweight-charts](https://github.com/tradingview/lightweight-charts), la
propia librería open-source de gráficos de TradingView.

![sidebar](https://img.shields.io/badge/UI-sidebar%20izquierdo-2962ff)

## Arquitectura

Como en Django, hay un **proyecto** (`app/`) que solo ensambla y varias
**apps**, cada una en su paquete con la misma estructura. `app/__init__.py`
crea la app Flask y registra las de `INSTALLED_APPS`: de cada una carga
`views.py` (páginas), `api.py` (endpoints bajo `/api`) y `commands.py`
(comandos de `flask`) si existen.

```
config.py                    # Configuración (variables de entorno), como settings.py
run.py                       # Punto de entrada: `uv run run.py`
app/
  __init__.py                # create_app() + INSTALLED_APPS
  core/                      # Lo compartido por todas las apps
    market_data.py             # Descarga + caché de precios/velas (yfinance)
    watchlists.py              # Registro de watchlists (Resumen y Gráficas)
    email.py                   # Envío de emails vía Resend
    navigation.py              # Entradas del sidebar de las páginas oscuras
    charts.py                  # Paleta de las gráficas generadas en el servidor
    views.py                   # Blueprint sin páginas: layout, sidebar, iconos, estáticos
    api.py                     # /api/watchlists, /api/quote, /api/candles, /api/email/send...
    templates/core/            # base.html (layout con sidebar), sidebar.html, icons.html, section_tabs.html
    static/                    # css/style.css, js/app.js, js/vendor/lightweight-charts
  cuentas/                   # Login con InsForge: "/ingresar", "/registro", "/verificar", "/recuperar", "/salir"
    insforge.py                # Cliente REST de /api/auth (sign-up, sign-in, verificación, reset)
    views.py                   # Sesión en la cookie de Flask + guarda de /app/ (AUTH_REQUIRED)
  moainvest/                 # Sitio principal (diseño rojo): "/" y "/graficas/..."
    views.py
    commands.py                # flask build-css (Tailwind sin Node)
    templates/moainvest/
    static/                    # moainvest.css (compilado), moainvest.js, src/, logos
  varianza/                  # Análisis de Varianza: "/app/analisis-varianza/"
    views.py, api.py           # Página y /api/volatility-chart
    analysis.py                # Volatilidad mensual + histogramas (seaborn)
    templates/varianza/, static/
  quant_stats/               # QUANT STATS, dentro del Graficador: "/app/graficador/quant-stats/..."
    views.py, api.py           # Páginas y /api/quant/<ticker>/...
    quant.py                   # quantstats: stats, Monte Carlo, plots, reports y earnings
    explain.py                 # Resúmenes en lenguaje llano de cada gráfica y tabla
    templates/quant_stats/, static/quant_stats.css
  favoritos/                 # Mis activos: "/app/favoritos/"
    views.py                   # Página con la tabla de activos guardados, agregar/quitar
    store.py                   # Lectura/escritura en InsForge (tabla activos_favoritos)
    templates/favoritos/, static/
tests/                       # pytest, una carpeta por app (tests/<app>/...)
```

- **Lógica (los "models" de Django)**: módulos de cada app sin Flask, por
  ejemplo `core/market_data.py`, el único que habla con `yfinance`.
- **Vistas**: `views.py` y `api.py` de cada app, con su `bp` (Blueprint).
- **Plantillas**: `app/<app>/templates/<app>/...`; el nombre de la app en la
  ruta evita choques entre apps (`render_template("varianza/index.html")`).
- **Estáticos**: `app/<app>/static/`, con `url_for("<app>.static", filename=...)`.

## Cómo extenderla

El sidebar tiene dos niveles:

1. **Apps**: para añadir una nueva (por ejemplo "Backtesting"), crea el
   paquete `app/backtesting/` con un `views.py` que defina su `bp`, y sus
   `templates/backtesting/`; añade `"backtesting"` a `INSTALLED_APPS` en
   `app/__init__.py` y su entrada en el sidebar (`app/core/navigation.py`):

   ```python
   App(slug="backtesting", name="Backtesting", icon="🧪", endpoint="backtesting.index", kind="blank"),
   ```

   Con `kind="blank"` no hace falta tocar la plantilla del sidebar: solo
   aparece el enlace.

2. **Watchlists** (`app/core/watchlists.py`): las listas de tickers que
   usan las Gráficas de MOAINVEST. Para añadir una nueva (por
   ejemplo "Bancos"):

   ```python
   Watchlist(
       slug="bancos",
       name="Bancos",
       icon="🏦",
       symbols=(
           Symbol("JPM", "JPMorgan"),
           Symbol("BAC", "Bank of America"),
       ),
   ),
   ```

   No hace falta tocar plantillas, vistas ni JavaScript: la nueva
   watchlist aparece automáticamente en Gráficas, con su propia ruta
   `/graficas/bancos` y su propio endpoint `/api/watchlist/bancos/quotes`.

### Análisis de Varianza

Además de la tabla de precios, esta app calcula la **volatilidad mensual
anualizada** (desviación estándar de los retornos diarios dentro de cada
mes calendario, multiplicada por `sqrt(252)`) de uno o varios tickers y
muestra, por cada uno, un histograma con la distribución de esas
volatilidades a lo largo del período elegido. El histograma se genera en
el servidor con **seaborn/matplotlib** (`app/varianza/analysis.py`) y se
sirve como PNG desde `GET /api/volatility-chart?tickers=AAPL,MSFT&period=5y`.

### QUANT STATS

Análisis cuantitativo con [quantstats](https://github.com/ranaroussi/quantstats)
de **cualquier activo de Yahoo Finance** (`?ticker=AAPL`, `^GSPC`, `BTC-USD`...;
UEC por defecto), sobre los retornos diarios del período elegido (1, 2 o 5
años, o todo). No es una app propia del sidebar: vive **dentro del
Graficador** (`/app/graficador/quant-stats/`) como dos de sus subsecciones, y
comparte con él el activo por la query string (`?ticker=`), así que desde el
gráfico de un activo se abre su análisis sin volver a escribirlo:

- **Quant stats** (`/app/graficador/quant-stats/fundamentales`): el activo por
  sí solo. Resumen con las 5 métricas clave (retorno, volatilidad, Sharpe,
  Sortino y máximo drawdown, cada una con una línea que explica qué es), las
  gráficas de `qs.plots` (6 destacadas y 8 más plegadas en «Más gráficas»), la
  **simulación Monte Carlo** (`qs.stats.montecarlo`, con simulaciones y umbrales
  de bust y goal en «Ajustar la simulación»), 26 métricas detalladas en 4
  tablas y el tearsheet HTML de `qs.reports.html` (abrir o descargar).
- **Comparar** (`/app/graficador/quant-stats/revision`): todo lo comparativo.
  - **Contra un índice** (cualquier ticker como benchmark): gráficas
    superpuestas, beta móvil, métricas lado a lado y tearsheet con benchmark.
  - **Entre períodos**: la misma gráfica en dos períodos, lado a lado.
  - **Resultados trimestrales**: últimos 4 earnings (EPS estimado vs.
    reportado, días, variación de EPS y de precio entre reportes).

Las URLs antiguas (`/app/quant-stats/...` y `/quant-stats/...`) redirigen con
**301** a `/app/graficador/quant-stats/...`, conservando subruta y query string
(`LEGACY_REDIRECTS` en `app/core/views.py`).

La API sirve las gráficas para cualquier ticker:
`GET /api/quant/<ticker>/plot/<gráfica>.png?period=2y&benchmark=SPY&window=126`,
`GET /api/quant/<ticker>/montecarlo.png?period=2y&sims=1000&bust=-20&goal=50`,
`GET /api/quant/<ticker>/earnings.png?count=4` y las versiones propias de
`drawdown.png` y `monthly-heatmap.png`.

### Resúmenes en lenguaje llano (Quant stats)

Cada gráfica y tabla de Quant stats lleva debajo un bloque **«En pocas
palabras»** (2-4 frases) que explica qué muestra y qué significa para ESE
activo con SUS números, sin jerga o explicándola (drawdown, Sharpe,
volatilidad, Monte Carlo, beta...). Por ejemplo: «En el peor momento llegó a
perder un 35 % desde su máximo (una caída fuerte) y tardó 8 meses en
recuperarse» o «Por cada unidad de riesgo obtuvo un rendimiento bueno (Sharpe
1,1; por encima de 1 se considera bueno)».

- **Métricas** (`quant.asset_facts(ticker, returns, window)`): resume los
  retornos en un `explain.AssetFacts` de números planos (retorno, CAGR,
  volatilidad, Sharpe, peores baches con su duración y recuperación, mejor y
  peor mes, años, VaR, métricas móviles...). `quant.benchmark_facts` añade el
  benchmark con su beta y correlación.
- **Redacción** (`app/quant_stats/explain.py`): funciones puras, sin Flask,
  pandas ni llamadas a LLM: `overview`, `stat_group(título)`, `plot(slug,
  facts, benchmark)`, `montecarlo`, `compare_periods`, `comparison_group` y
  `earnings`. Los umbrales están arriba del módulo como constantes
  (`SHARPE_TIERS`: <0 negativo, 0-0,5 pobre, 0,5-1 razonable, 1-2 bueno, ≥2
  excelente; `VOLATILITY_TIERS`, `DRAWDOWN_TIERS`, `CALMAR_TIERS`,
  `BUST_TIERS`, `BETA_TIERS`...). Con menos de `MIN_TRADING_DAYS` sesiones
  devuelven `INSUFFICIENT`, un aviso de datos insuficientes.
- **Plantillas**: el macro `summary(texto, clave)` de
  `quant_stats/_summary.html` pinta el bloque con `data-summary="<clave>"`.
- **Nueva gráfica**: al añadir un `PlotSpec` a `quant.PLOTS`, escribe su
  función `_plot_<slug>(facts)` y regístrala en `explain._PLOT_WRITERS`
  (`test_every_plot_has_its_own_summary` falla si falta). Una tabla nueva de
  `STAT_GROUPS` necesita su entrada en `_GROUP_WRITERS` (y en
  `_COMPARISON_WRITERS` para la comparación con benchmark).
- Tests por tramos en `tests/quant_stats/test_explain.py` (bueno/regular/malo,
  positivo/negativo y datos insuficientes).

### Mis activos

App `app/favoritos/` en `/app/favoritos/` (única entrada "Mis activos" del
sidebar; absorbe a la antigua "Mi universo de acciones", y `/app/universo/`
redirige aquí con 301). Muestra **solo** los activos que el usuario tiene
guardados en InsForge, sin listas genéricas ni datos de ejemplo: una tabla con
ticker, nombre, fecha de alta, precio y variación del día en vivo
(`/api/quote/<ticker>`, pedidos desde `app/favoritos/static/favoritos.js`, 8 en
paralelo), con búsqueda y ordenación, y enlaces al **Graficador** y a **Quant
stats**. Desde la misma página se agregan y quitan activos (máx. 50).

Los activos se leen en `app/favoritos/store.py` por la API REST de base de
datos de InsForge (`GET {INSFORGE_URL}/api/database/records/activos_favoritos`
con `user_id=eq.<id de la sesión>`), autenticada con `INSFORGE_API_KEY` (solo
servidor, en `.env`). Sin sesión o sin credenciales no se muestra ningún activo.

### Nombres del sidebar

Los textos de los enlaces del sidebar (apps de `app/core/navigation.py`, sus
`sections` y las watchlists de `watchlists.py`) se escriben en formato frase:
primera letra en mayúscula y el resto en minúscula ("Quant stats", "Análisis de
varianza"). Se escriben así en su origen, sin `text-transform`;
`tests/core/test_navigation.py` lo comprueba.

### Iconos de línea

Las páginas del área App usan iconos de línea (trazados de
[Lucide](https://lucide.dev), licencia ISC) como SVG inline desde el macro
`app/core/templates/core/icons.html`, sin CDN ni dependencias:

```jinja
{% import "core/icons.html" as icons %}
{{ icons.icon("send") }}                      {# decorativo: aria-hidden #}
{{ icons.icon("eye", label="Ver") }}          {# con significado: role="img" #}
```

Heredan el color del texto (`stroke="currentColor"`) y miden `1em` (clase
`.ui-icon`). Para añadir uno, anexa su trazado al diccionario `_paths`.

### Nombre de la marca

El nombre visible de la app (**MoaiInvest**) vive en un único sitio:
`Config.SITE_NAME` en `config.py`. Un context processor lo inyecta en todas
las plantillas como `site_name` (títulos de página y sidebar). Para renombrar
la app basta con cambiar esa línea. El `name` de `pyproject.toml`
(`market-dashboard`) es un identificador técnico y no se muestra al usuario.

### Sitio MOAINVEST

El sitio principal, con el diseño rojo de MOAINVEST, se sirve en la raíz:

| Ruta | En el navbar | Contenido |
|---|---|---|
| `/` | **Inicio** | **Resumen**: watchlist «Resumen» con precios en vivo y la línea del último mes |
| `/app/` | **App** (y botón «Abrir app») | Redirige a la primera app del sidebar (`default_app()`) |
| `/graficas/<watchlist>/<ticker>` | — (atajo del Resumen) | **Gráficas**: velas, rangos de 1D a Todo y precios del resto de la watchlist (`/graficas` y `/graficas/<watchlist>` redirigen al primer símbolo) |

Cualquier ruta inexistente muestra el 404 con este mismo diseño. El
Graficador (con Quant stats dentro), Análisis de varianza, Pyportfolio opt y
Mis activos viven en el área App
(`/app/...`), con el layout de sidebar.

- App `app/moainvest/`: `views.py` y plantillas en `templates/moainvest/`.
- `app/moainvest/static/moainvest.js` (sin framework) refresca los precios
  cada 15 s y dibuja sparklines y el gráfico de velas, usando la
  API JSON `/api/...`.
- El CSS es Tailwind v4, pero **sin Node**: el compilado
  `app/moainvest/static/moainvest.css` se commitea, y para regenerarlo tras
  cambiar clases en las plantillas o en el JS se usa el binario standalone de
  Tailwind que instala uv (dependencia de desarrollo `pytailwindcss`):

  ```bash
  uv run flask --app run build-css          # o --watch mientras desarrollas
  ```

### Mercados

`/mercados` reúne en una sola página **índices, acciones, cripto, divisas,
materias primas, bonos públicos, bonos corporativos y ETF**. Cada categoría
trae una frase que explica qué mide, tarjetas con precio, variación y línea
del último mes (que se piden al acercarse a la pantalla), y una barra de
categorías fija que marca la sección visible. Arriba, el **panorama del día**
cuenta cuántos activos suben y muestra los tres que más suben y bajan.

- **Bonos públicos**: rendimientos del Tesoro de EE. UU. (3 meses, 5, 10 y 30
  años) y su **curva de rendimiento**, que dice si está normal, plana o
  invertida (`markets.curve_shape`).
- **Bonos corporativos**: Yahoo no publica bonos corporativos uno a uno, así
  que se siguen con ETF (VCSH, LQD, HYG...) en una tabla filtrable por corto
  plazo, largo plazo, grado de inversión, alto rendimiento y emergentes.

Las categorías viven en `MARKETS` de `app/moainvest/markets.py` (sin Flask):
añadir una es añadir una entrada. APIs públicas:
`GET /api/mercados/<slug>/quotes` y `GET /api/mercados/curva`.

### Radar de noticias del Inicio

Bajo los precios del Inicio, `app/moainvest/radar.py` y `GET /api/radar`
pintan el **termómetro del mercado** (0 = miedo, 100 = euforia, con el
sentimiento de los titulares ponderado por recencia), **noticias vs. precio**
(si el precio de hoy confirma o diverge del tono de las noticias de cada
activo) y los titulares con las palabras que deciden su sentimiento
(`noticias.sentiment.signals`). Es una estimación por palabras clave, no una
recomendación de inversión.

### Navbar

El navbar del sitio rojo (cabecera, menú móvil y pie) sale de `MAIN_NAV` en
`app/moainvest/views.py` y tiene tres enlaces: **Inicio** (`/`), **Mercados**
(`/mercados`) y **App** (`/app/`). El botón de la cabecera y del menú móvil, «Abrir app», también
apunta a `/app/`.

`/app/` (endpoint `moainvest.app_home`, también responde en `/app`) no tiene
página propia: redirige (302) a `url_for(default_app().endpoint)` de
`app/core/navigation.py`, así que siempre lleva a la primera app de `APPS`
aunque cambie el orden del sidebar. Para añadir otro enlace al navbar, añade
una tupla `(endpoint, etiqueta)` a `MAIN_NAV`; `nav_link` (en
`moainvest/_macros.html`) lo marca como activo cuando la ruta actual empieza
por su URL.

### Área App

Todo lo que se ve con el layout oscuro de sidebar cuelga de `/app/`:

| Ruta | Subapp |
|---|---|
| `/app/graficador/` | Graficador |
| `/app/graficador/quant-stats/` (`fundamentales`, `revision`, `tearsheet`) | Quant stats, dentro del Graficador |
| `/app/analisis-varianza/` | Análisis de varianza |
| `/app/pyportfolio-opt/` | Pyportfolio opt (retornos esperados) |
| `/app/favoritos/` | Mis activos (`/app/universo/` redirige aquí) |

Las APIs siguen en `/api/...`. Las rutas antiguas redirigen con **301**,
conservando subruta y query string (`LEGACY_REDIRECTS` en `app/core/views.py`):
`/analisis-varianza/...` a `/app/analisis-varianza/...`, y `/quant-stats/...`
y `/app/quant-stats/...` a `/app/graficador/quant-stats/...`.

La app **Informes** (informe de mercado por email, con Cloudinary) se eliminó:
`/informes/...`, `/app/informes/...`, `/informe` y sus APIs
(`/api/report/...`, `/api/email/send-assets-report`) responden con el **404**
del sitio, porque ya no hay una página equivalente a la que redirigir.

- El orden del sidebar es el de `APPS` en `app/core/navigation.py`: primero
  el Graficador (con sus subsecciones Gráfico, Quant stats y Comparar) y
  después el resto de subapps.
- `tests/core/test_navigation.py` recorre `INSTALLED_APPS` y falla si una app
  con páginas propias (salvo `core`, `moainvest` y `cuentas`) no está en
  `APPS`, como app o como subsección de otra: una subapp nueva no puede
  quedarse fuera del sidebar. Dale también un `url_prefix="/app/<slug>"` a su
  blueprint de páginas.
- El logo de la barra superior enlaza a **Inicio** (`moainvest.resumen`, `/`)
  para volver al sitio rojo (ver «Estética del área App»).

### Graficador

App `app/graficador/` (layout oscuro con sidebar) en `/app/graficador/`: el
gráfico de **cualquier ticker de Yahoo Finance** (`?ticker=AAPL`, `^GSPC`,
`BTC-USD`, `EURUSD=X`...; por defecto, el primer símbolo de la watchlist por
defecto). Es la primera entrada del sidebar y sustituye al antiguo enlace
«Gráficas» a `/graficas`. Sus pestañas **Gráfico | Quant stats | Comparar**
(`core/section_tabs.html`, las mismas subsecciones que el sidebar) llevan el
`?ticker=` actual a Quant stats, y bajo el gráfico una tarjeta abre el análisis
de ese activo.

- Controles agrupados con etiqueta: **Período** y **Vista** (velas, línea,
  área) a la izquierda; **Indicadores** y proveedor de precios a la derecha.
  En móvil cada grupo ocupa su fila y los chips se desplazan en horizontal.

- Velas, línea o área en el pane principal y el **volumen** como histograma en
  un pane propio (panes de lightweight-charts v5).
- Rangos 1D, 5D, 1M, 6M, 1A, 5A y Todo (`CHART_RANGES` en
  `app/graficador/views.py`, cada uno con su intervalo), buscador de ticker,
  leyenda OHLC + volumen que sigue al crosshair y redimensionado con `autoSize`.
- Un ticker con caracteres no válidos responde 400 con el mensaje de error; uno
  válido sin datos en Yahoo muestra «No hay datos…» sobre el gráfico.
- Los datos vienen de `GET /api/candles/<ticker>?range=&interval=` (`core`),
  que ya devuelve `volume`; el JS está en `app/graficador/static/graficador.js`
  y toma los colores de los tokens de `core/static/css/style.css`.

**lightweight-charts**: vendorizada la **v5.2.1** (standalone production,
descargada de `https://unpkg.com/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js`)
en `app/core/static/js/vendor/`. Desde la v5 las series se crean con
`chart.addSeries(LightweightCharts.CandlestickSeries, opciones, paneIndex)` en
vez de `addCandlestickSeries(...)`, y los markers con
`LightweightCharts.createSeriesMarkers(series, markers)` en vez de
`series.setMarkers(...)`. Un test (`tests/graficador/test_routes.py`) comprueba
que ningún JS propio usa la API de la v4.

#### Indicadores técnicos (TA-Lib)

El botón **Indicadores** del Graficador abre un diálogo, como el de TradingView,
con **28 indicadores** de [TA-Lib](https://ta-lib.org) (`ta-lib` en
`pyproject.toml`; el wheel ya incluye la librería C, no hace falta compilar nada),
buscador sin tildes y cuatro categorías: Tendencia, Momentum, Volatilidad y Volumen.

- Se pueden añadir **1 o N** indicadores, incluso el mismo con distintos
  parámetros (SMA 20 y SMA 50). Máximo 20 en el gráfico.
- Los de tendencia (medias móviles, Bollinger, SAR) van **sobre el precio**; el
  resto, cada uno en **su propio panel** bajo el volumen (panes de
  lightweight-charts v5). El gráfico crece en alto con cada panel nuevo.
- Cada indicador tiene su leyenda con los valores bajo el cursor y los botones
  de **ocultar**, **ajustes** (parámetros y colores) y **quitar**.
- La lista (con parámetros, colores y visibilidad) se guarda en el navegador
  (`localStorage`, clave `graficador:indicators:v1`) y se aplica a cualquier ticker.
- Se calculan en el servidor sobre **más historia que la visible** (5 años en
  diario, 1 mes en intradía, etc.; ver `warmup_range`), así que una SMA(200)
  ya tiene valor en la primera vela del gráfico, como en TradingView.

| Ruta | Contenido |
|---|---|
| `GET /api/graficador/indicators` | Catálogo: parámetros (con límites), salidas, categoría y paleta |
| `GET /api/graficador/<ticker>/indicators?range=6mo&interval=1d&ind=sma:20&ind=macd:12,26,9` | `{"time": [...], "indicators": [{"spec", "outputs": {clave: [...]}}]}`; `null` mientras el indicador se calienta |

`ind` es `<id>:<parámetros por orden>`; los que falten toman su valor por
defecto. Una petición inválida (indicador desconocido, parámetro fuera de
rango, más de 25) responde 400 sin descargar nada de Yahoo.

**Añadir un indicador**: una entrada más en `INDICATORS` de
`app/graficador/indicators.py` (módulo sin Flask), con sus `Param` (y límites),
sus `Output` (`line`, `dashed`, `dots` o `histogram`), si es `overlay`, y la
función que llama a TA-Lib. Aparece solo en el diálogo y en la API; un test
comprueba que las claves que devuelve coinciden con las declaradas.

El JS está en `app/graficador/static/graficador-indicators.js` y usa
`window.GraficadorChart`, que expone `graficador.js` (gráfico, tema y un
`onData` que avisa cuando llegan velas). Sus estilos llevan el prefijo `gind-`.
No hay patrones de velas, Ichimoku, Supertrend ni VWAP: TA-Lib no los trae.

### Proveedores de precios del Graficador

El Graficador permite elegir de dónde vienen las velas con el selector junto a
los botones de rango (la elección se recuerda en `localStorage`, clave
`graficador:provider:v1`). La lógica, sin Flask, está en
`app/graficador/providers.py`: cada proveedor implementa `Provider`
(`unavailable_reason()` y `get_candles(ticker, range_, interval)`), devuelve
las mismas columnas OHLCV que `market_data.get_candles` (así los indicadores
TA-Lib funcionan igual) y avisa de los fallos con `ProviderError`.

| Proveedor | Notas |
|---|---|
| `yahoo` (por defecto) | `app.core.market_data` (yfinance); admite índices, divisas, futuros y cripto |
| `alphavantage` | `TIME_SERIES_INTRADAY` (1m-1h), `DAILY`, `WEEKLY` y `MONTHLY` según el intervalo; no admite `^GSPC` ni `EURUSD=X` |

**Configurar Alpha Vantage**: pide una clave gratuita en
<https://www.alphavantage.co/support/#api-key> y ponla en el `.env`
(`ALPHAVANTAGE_API_KEY=...`; opcional `ALPHAVANTAGE_CACHE_TTL`, 300 s por
defecto). Sin clave el proveedor aparece como "(no disponible)" y la API
responde 503 con el motivo. El plan gratuito permite ~25 peticiones al día y 5
por minuto: las respuestas `Note`/`Information` de límite se traducen a un 429
con mensaje claro, y la serie completa se cachea por símbolo e intervalo (un
cambio de rango o el cálculo de indicadores no gasta otra petición). Si el
`outputsize=full` diario es premium, se reintenta con `compact` (100 días).

| Ruta | Contenido |
|---|---|
| `GET /api/graficador/providers` | `{"default", "providers": [{id, name, available, reason}]}` |
| `GET /api/graficador/<ticker>/candles?provider=&range=&interval=` | Velas del proveedor elegido; errores `{"error"}` con 400/404/422/429/502/503/504 |
| `GET /api/graficador/<ticker>/indicators?provider=...` | Igual que antes, calculado sobre las velas de ese proveedor |

**Añadir un proveedor**: una subclase de `Provider` registrada en `PROVIDERS`.
Aparece sola en el selector y en la API.

### Pyportfolio opt

App `app/pyportfolio_opt/` (layout de sidebar) en `/app/pyportfolio-opt/`:
**retornos esperados anualizados** de 1 a 10 activos de Yahoo Finance con
[PyPortfolioOpt](https://pyportfolioopt.readthedocs.io) (`pyportfolioopt` en
`pyproject.toml`, módulo `pypfopt.expected_returns`), con dos metodologías:

| Metodología | Función | Cálculo (frecuencia 252) |
|---|---|---|
| Media histórica | `mean_historical_return` | Con capitalización, CAGR `(∏(1 + r))^(252/N) − 1`; sin ella, `media(r) · 252` |
| EMA | `ema_historical_return` | Media móvil exponencial de los retornos con ventana `span` (500 por defecto); con capitalización `(1 + EMA)^252 − 1` |

La lógica, sin Flask, está en `app/pyportfolio_opt/expected.py`: toma los
cierres diarios de `market_data.get_candles` (con su caché), cada activo usa
su propia historia dentro del período y los tickers sin datos se devuelven en
`missing`. La gráfica de barras se dibuja con `MPL_RC` y los colores de
`app/core/charts.py` dentro de `rc_context`.

| Ruta | Contenido |
|---|---|
| `GET /api/pyportfolio-opt/expected-returns?tickers=AAPL,MSFT&period=5y&method=both&span=500&compounding=1&log_returns=0` | JSON con `assets` (`ticker`, `start`, `end`, `observations` y el retorno de cada metodología en tanto por uno) y `missing` |
| `GET /api/pyportfolio-opt/expected-returns.png?...` | Barras agrupadas por activo y metodología (mismos parámetros) |

`method` es `historical`, `ema` o `both`; `period`, `1y`, `2y`, `5y`, `10y` o
`max`; `span`, de 2 a 5000. Una entrada inválida responde 400 sin descargar
nada y, si ningún ticker tiene precios, 404.

### Estética de Análisis de varianza

`/app/analisis-varianza/` sigue la marca del sitio rojo
(blancos, rojos y negros, Geist): cabecera con eyebrow mono y título grande,
tarjetas blancas con borde `line` y botones pill rojos. Sus estilos están solo
en la sección "Análisis de Varianza" de `app/core/static/css/style.css`, sobre
los tokens del `:root`.

- Las clases base `.varianza-page`, `.varianza-form*`, `.varianza-table*`,
  `.varianza-status` y `.volatility-*` también las usa Quant stats: conserva
  su estructura. Lo propio de cada página lleva su prefijo (`.varianza-hero`,
  `.varianza-chip`...).
- El campo de tickers de la volatilidad crea chips con Intro, coma o espacio
  (`varianza.js`); el máximo sale de `MAX_VOLATILITY_TICKERS` de `api.py`.
- Las gráficas del servidor (`varianza/analysis.py`) usan `PALETTE`, `MPL_RC`,
  `UP` y `DOWN` de `app/core/charts.py` dentro de `rc_context`, sin cambiar el
  tema global de matplotlib.

### Estética del área App

Las páginas de `/app/...` usan el mismo lenguaje visual que el sitio rojo
(`moainvest/base.html`): blancos, rojos y negros, Geist, bordes `line` y pills.

- **Shell** (`app/core/templates/core/base.html`): carga las mismas fuentes de
  Google (Geist, Geist Mono, Instrument Serif), los favicons de
  `moainvest.static` y `theme-color` blanco. Arriba, una **barra superior**
  fija (`.topbar`) con el logo `moainvest/static/logo/moainvest-compact.png`
  enlazado a Inicio y el navbar de `moainvest_nav` (Inicio / App, con App
  activo y subrayado rojo). Bloques: `title`, `head`, `content` y `scripts`.
- **Sidebar** (`core/sidebar.html`): blanco con borde `line`, iconos de línea
  de `core/icons.html` por slug (`nav_icons`; una app sin entrada usa el emoji
  de `App.icon`) y la app activa con fondo `brand-soft`, texto `brand` y barra
  lateral roja. En escritorio se colapsa (`#sidebar-toggle`, recordado en
  `localStorage`); por debajo de 760px es un **cajón** que abre el botón de
  menú de la barra (`#sidebar-open`) y se cierra con el fondo o Escape
  (`core/static/js/app.js`).
- **Tokens** (`:root` de `core/static/css/style.css`): `--brand`,
  `--brand-deep`, `--brand-soft`, `--brand-bright`, `--logo`, `--ink`,
  `--muted`, `--paper`, `--mist`, `--line`, `--up`/`--up-soft`,
  `--down`/`--down-soft`, `--font-sans/mono/serif`, `--radius`,
  `--radius-pill`, `--shadow-card`, `--ease-out-soft` y, para el shell,
  `--topbar-height`, `--sidebar-width` y `--sidebar-width-collapsed`. Los
  alias antiguos (`--bg`, `--bg-panel`, `--text`, `--accent`...) apuntan a ellos.
- **Componentes genéricos** (sección «Contenido principal» de `style.css`),
  para que cualquier página se vea de la familia sin Tailwind:

  | Clase | Aspecto |
  |---|---|
  | `.page` | contenedor de página (máx. 1120px, márgenes del sitio rojo) |
  | `.page-head`, `.eyebrow`, `.page-title`, `.page-lead` | cabecera como `resumen.html`: eyebrow en mono uppercase con guion rojo, título grande con tracking `-0.04em` y entradilla gris |
  | `.accent` | una palabra en Instrument Serif itálica y roja dentro del título |
  | `.card`, `.card--mist` | tarjeta blanca con borde `line`, radio 16px y `--shadow-card` (o fondo mist) |
  | `.btn.btn--primary`, `.btn.btn--secondary`, `.btn--sm` | pill rojo para la acción primaria y outline negro para la secundaria |
  | `.input`, `.select` | campos pill con borde `line` y foco rojo |
  | `.table-wrap`, `.table` | tabla con cabecera mist en mono uppercase |
  | `.pill.is-up` / `.pill.is-down` | variación de precio en verde o rojo |

  Ejemplo:

  ```html
  <div class="page">
    <header class="page-head">
      <p class="eyebrow">Herramientas · Yahoo Finance</p>
      <h1 class="page-title">Análisis de <span class="accent">varianza</span>.</h1>
      <p class="page-lead">Descarga el histórico de un activo.</p>
    </header>
    <div class="card">
      <input class="input" placeholder="AAPL">
      <button class="btn btn--primary">Descargar</button>
    </div>
  </div>
  ```

### Estética de Quant stats

Las páginas de `app/quant_stats/` (`/app/graficador/quant-stats/fundamentales`,
`/revision` y el tearsheet) siguen la marca MOAINVEST del sitio rojo, con una
jerarquía pensada para quien no es experto: pestañas del Graficador, cabecera
del activo con su selector (ticker y período en chips) y secciones con
tarjetas; lo avanzado (más gráficas, ajustes de Monte Carlo, todas las métricas
comparadas) va plegado en `<details class="qs-more">`.

- Plantillas: `quant_stats/_base.html` extiende `core/base.html`, pinta las
  pestañas (`core/section_tabs.html`, con el enlace al tearsheet) y la cabecera;
  las páginas rellenan los bloques `hero_eyebrow`, `hero_lead`, `asset_form` y
  `page`. Estilos propios con prefijo `qs-` en
  `app/quant_stats/static/quant_stats.css` (no en `style.css`, salvo
  `.is-up`/`.is-down`, compartidos con el Graficador).
- Gráficas del servidor (`quant.py`): todo se dibuja dentro de
  `_brand_theme()`, que bajo `_QS_PLOT_LOCK` aplica `MPL_RC` de
  `app/core/charts.py` con `matplotlib.rc_context`, cambia la paleta de
  quantstats por `QS_COLORS` (benchmark en gris, activo en rojo de marca) y lo
  restaura al salir. `_brand_figure()` sustituye los colores fijos de
  quantstats (`_QS_FIXED_COLORS`) y pasa los heatmaps a `HEATMAP_CMAP`
  (rojo ↔ blanco ↔ verde, centrado en 0).
- Tearsheet: `brand_tearsheet()` inyecta `TEARSHEET_CSS` (Geist, acentos
  rojos, tablas con filas separadas) antes de `</head>` del HTML de
  `qs.reports.html`; sus gráficas SVG salen ya con el tema de marca.

## Puesta en marcha

Requiere [uv](https://docs.astral.sh/uv/) y Python 3.12+.

```bash
uv sync                 # instala dependencias (y crea el .venv)
cp .env.example .env    # opcional: ajustar TTLs de caché, etc.
uv run run.py           # http://localhost:5000
```

## Tests

```bash
uv run pytest
```

### CI/CD

El workflow `.github/workflows/tests.yml` (GitHub Actions) ejecuta la suite en
cada **pull request hacia `stg` o `main`**, y también a mano desde la pestaña
Actions (`workflow_dispatch`). Instala uv, Python según `.python-version` y
las dependencias exactas de `uv.lock` (`uv sync --locked`), y corre
`uv run pytest`. Si llegan commits nuevos al PR, cancela la ejecución
anterior. No necesita `.env` ni secretos: los tests no tocan la red.

Para que un PR no se pueda mergear con los tests en rojo, en GitHub ve a
*Settings → Branches* y añade una regla de protección para `main` y `stg`
con el check **Tests / pytest** como obligatorio.

## Notas

- Los precios se cachean en memoria (`QUOTE_CACHE_TTL` / `CANDLE_CACHE_TTL`
  en `.env`) para no saturar Yahoo Finance; ajusta los valores según lo
  necesites.
- El servidor de desarrollo de Flask no es apto para producción; para
  desplegar, sirve `app` (la factory `create_app()`) con Gunicorn/uWSGI
  detrás de un proxy.

## Login (InsForge)

La autenticación usa [InsForge](https://insforge.dev) vía su API REST
(`app/cuentas/`). Registro con verificación por código de correo, login,
recuperación de contraseña y logout. Con `AUTH_REQUIRED=1` (por defecto) todo
`/app/` exige sesión; el sitio público sigue abierto.

```
INSFORGE_URL=<oss_host de .insforge/project.json>
INSFORGE_ANON_KEY=<npx @insforge/cli secrets get ANON_KEY>
```
