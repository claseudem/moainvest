# MoaiInvest

Panel de precios en vivo, estilo TradingView, construido solo con **Flask**
(organizado en **apps con blueprints, al estilo Django**) y **UV** para la
gestión del proyecto/dependencias (sin Node). El sitio principal,
**MOAINVEST** (Resumen, Gráficas e Informe), se sirve en la raíz con su
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
    watchlists.py              # Registro de watchlists (Resumen, Gráficas, Informe)
    email.py                   # Envío de emails vía Resend
    navigation.py              # Entradas del sidebar de las páginas oscuras
    charts.py                  # Paleta de las gráficas generadas en el servidor
    views.py                   # Blueprint sin páginas: layout, sidebar, iconos, estáticos
    api.py                     # /api/watchlists, /api/quote, /api/candles, /api/email/send...
    templates/core/            # base.html (layout con sidebar), sidebar.html, icons.html
    static/                    # css/style.css, js/app.js, js/vendor/lightweight-charts
  moainvest/                 # Sitio principal (diseño rojo): "/", "/graficas/..." e "/informe"
    views.py
    commands.py                # flask build-css (Tailwind sin Node)
    templates/moainvest/
    static/                    # moainvest.css (compilado), moainvest.js, src/, logos
  varianza/                  # Análisis de Varianza: "/app/analisis-varianza/"
    views.py, api.py           # Página y /api/volatility-chart
    analysis.py                # Volatilidad mensual + histogramas (seaborn)
    templates/varianza/, static/
  quant_stats/               # QUANT STATS: "/app/quant-stats/..."
    views.py, api.py           # Páginas y /api/quant/<ticker>/...
    quant.py                   # quantstats: stats, Monte Carlo, plots, reports y earnings
    templates/quant_stats/
  informes/                  # Informes por email: "/app/informes/"
    views.py, api.py           # Página y /api/report/..., /api/email/send-assets-report
    commands.py                # flask cloudinary-upload
    report.py                  # Informe HTML de cotizaciones
    report_charts.py           # Gráfico por watchlist del informe
    media.py                   # Imágenes optimizadas vía Cloudinary
    templates/informes/        # index.html y emails/market_report.html
    static/                    # js/, img/informes/, video/
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
   usan las Gráficas y el Informe de MOAINVEST. Para añadir una nueva (por
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
   `/graficas/bancos` y su propio endpoint `/api/watchlist/bancos/quotes`,
   y en el Informe.

### Análisis de Varianza

Además de la tabla de precios, esta app calcula la **volatilidad mensual
anualizada** (desviación estándar de los retornos diarios dentro de cada
mes calendario, multiplicada por `sqrt(252)`) de uno o varios tickers y
muestra, por cada uno, un histograma con la distribución de esas
volatilidades a lo largo del período elegido. El histograma se genera en
el servidor con **seaborn/matplotlib** (`app/varianza/analysis.py`) y se
sirve como PNG desde `GET /api/volatility-chart?tickers=AAPL,MSFT&period=5y`.

### Informe de mercado por email

`app/informes/report.py` obtiene las cotizaciones de las watchlists, construye
un informe HTML (resumen de subidas/bajadas, mayores movimientos y una tabla
por watchlist) con la plantilla `app/informes/templates/informes/emails/market_report.html` y lo
envía vía Resend:

```python
from app.models.report import build_market_report, send_market_report

report = build_market_report(["overview"])   # .subject y .html listos para enviar
send_market_report("destino@ejemplo.com")      # todas las watchlists
```

También por HTTP: `GET /api/report/preview?watchlists=overview` para verlo
en el navegador y `POST /api/email/send-assets-report` con
`{"to": "destino@ejemplo.com", "watchlists": ["overview"]}` para enviarlo
(`watchlists` es opcional).

Desde la app, el apartado **📨 Informes** (`/app/informes/`) permite elegir las
watchlists, ver el informe con "Ver informe" y enviarlo con "Enviar por correo".

### Imágenes con Cloudinary

Los fondos de la página de Informes llevan una imagen servida desde
[Cloudinary](https://cloudinary.com) con `f_auto,q_auto` (AVIF/WebP/JPEG y
calidad elegidos por Cloudinary para cada navegador) y un `srcset` de 640,
1280 y 1920 px. La lógica vive en `app/informes/media.py`.

1. Copia tu URL de API desde la [consola de Cloudinary](https://console.cloudinary.com/settings/api-keys)
   y ponla en el `.env`: `CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>`.
2. Sube las imágenes (una sola vez, o cada vez que cambies las de
   `app/informes/static/img/informes/`): `uv run flask --app run cloudinary-upload`.

Sin `CLOUDINARY_URL`, la página usa las copias locales de `app/informes/static/img/informes/`.

### QUANT STATS

Análisis cuantitativo con [quantstats](https://github.com/ranaroussi/quantstats)
de **cualquier activo de Yahoo Finance** (`?ticker=AAPL`, `^GSPC`, `BTC-USD`...;
UEC por defecto) en `/app/quant-stats/`, sobre los retornos diarios del período
elegido (1, 2 o 5 años, o todo). Tiene dos subsecciones en el sidebar que no
se solapan:

- **Gráficas y fundamentales estadísticos** (`/app/quant-stats/fundamentales`):
  el activo por sí solo, según los 3 módulos principales de quantstats.
  - **stats**: 5 métricas de resumen y 26 más agrupadas (rendimiento, riesgo,
    ajustado por riesgo y operativa diaria), más la **simulación Monte Carlo**
    (`qs.stats.montecarlo`) con número de simulaciones y umbrales de bust y
    goal configurables. Al barajar retornos el resultado final no cambia, así
    que goal siempre es 0% o 100%; bust y los drawdowns son lo informativo.
  - **plots**: 14 gráficas nativas de `qs.plots`.
  - **reports**: tearsheet HTML de `qs.reports.html` (abrir o descargar).
- **Revisión analítica** (`/app/quant-stats/revision`): todo lo comparativo.
  - **Activo vs. benchmark** (cualquier ticker): gráficas superpuestas, beta
    móvil, todas las métricas lado a lado y tearsheet con benchmark.
  - **Período vs. período**: la misma gráfica en dos períodos, lado a lado.
  - **Reporte vs. reporte**: últimos 4 earnings (EPS estimado vs. reportado,
    días, variación de EPS y de precio entre reportes).

La API sirve las gráficas para cualquier ticker:
`GET /api/quant/<ticker>/plot/<gráfica>.png?period=2y&benchmark=SPY&window=126`,
`GET /api/quant/<ticker>/montecarlo.png?period=2y&sims=1000&bust=-20&goal=50`,
`GET /api/quant/<ticker>/earnings.png?count=4` y las versiones propias de
`drawdown.png` y `monthly-heatmap.png`.

### Nombres del sidebar

Los textos de los enlaces del sidebar (apps de `apps.py`, sus `sections` y las
watchlists de `watchlists.py`) se escriben en formato frase: primera letra en
mayúscula y el resto en minúscula ("Quant stats", "Análisis de varianza"). Se
escriben así en su origen, sin `text-transform`; `tests/test_apps.py` lo
comprueba.

### Iconos de Informes

La página de Informes usa iconos de línea (trazados de
[Lucide](https://lucide.dev), licencia ISC) como SVG inline desde el macro
`app/core/templates/core/icons.html`, sin CDN ni dependencias:

```jinja
{% import "partials/icons.html" as icons %}
{{ icons.icon("send") }}                      {# decorativo: aria-hidden #}
{{ icons.icon("eye", label="Ver") }}          {# con significado: role="img" #}
```

Heredan el color del texto (`stroke="currentColor"`) y miden `1em` (clase
`.ui-icon`). Para añadir uno, anexa su trazado al diccionario `_paths`; el
icono de cada watchlist se elige por slug en `watchlist_icons` (las que no
estén usan `list`).

### Nombre de la marca

El nombre visible de la app (**MoaiInvest**) vive en un único sitio:
`Config.SITE_NAME` en `config.py`. Un context processor lo inyecta en todas
las plantillas como `site_name` (títulos de página y sidebar) y
`app/informes/report.py` lo usa en el asunto y la cabecera del informe por
email. Para renombrar la app basta con cambiar esa línea. El `name` de
`pyproject.toml` (`market-dashboard`) y el prefijo de Cloudinary son
identificadores técnicos y no se muestran al usuario.

### Sitio MOAINVEST

El sitio principal, con el diseño rojo de MOAINVEST, se sirve en la raíz:

| Ruta | En el navbar | Contenido |
|---|---|---|
| `/` | **Inicio** | **Resumen**: watchlist «Resumen» con precios en vivo y la línea del último mes |
| `/app/` | **App** (y botón «Abrir app») | Redirige a la primera app del sidebar (`default_app()`) |
| `/graficas/<watchlist>/<ticker>` | — (atajo del Resumen) | **Gráficas**: velas, rangos de 1D a Todo y precios del resto de la watchlist (`/graficas` y `/graficas/<watchlist>` redirigen al primer símbolo) |
| `/informe` | — (atajo del Resumen) | **Informe**: elegir watchlists, vista previa y envío por correo |

Cualquier ruta inexistente muestra el 404 con este mismo diseño. El
Graficador, Informes, Análisis de varianza y Quant stats viven en el área App
(`/app/...`), con el layout de sidebar.

- App `app/moainvest/`: `views.py` y plantillas en `templates/moainvest/`.
- `app/moainvest/static/moainvest.js` (sin framework) refresca los precios
  cada 15 s y dibuja sparklines, el gráfico de velas y el informe, usando la
  API JSON `/api/...`.
- El CSS es Tailwind v4, pero **sin Node**: el compilado
  `app/moainvest/static/moainvest.css` se commitea, y para regenerarlo tras
  cambiar clases en las plantillas o en el JS se usa el binario standalone de
  Tailwind que instala uv (dependencia de desarrollo `pytailwindcss`):

  ```bash
  uv run flask --app run build-css          # o --watch mientras desarrollas
  ```

### Navbar

El navbar del sitio rojo (cabecera, menú móvil y pie) sale de `MAIN_NAV` en
`app/moainvest/views.py` y solo tiene dos enlaces: **Inicio** (`/`) y **App**
(`/app/`). El botón de la cabecera y del menú móvil, «Abrir app», también
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
| `/app/informes/` | Informes |
| `/app/analisis-varianza/` | Análisis de varianza |
| `/app/quant-stats/` (`fundamentales`, `revision`, `tearsheet`) | Quant stats |

Las APIs siguen en `/api/...`. Las rutas antiguas (`/analisis-varianza/...`,
`/quant-stats/...`, `/informes/...`) redirigen con **301** a su equivalente
bajo `/app/`, conservando subruta y query string (`LEGACY_APP_PREFIXES` en
`app/core/views.py`).

- El orden del sidebar es el de `APPS` en `app/core/navigation.py`: primero
  el graficador, luego Informes y después el resto de subapps.
- `tests/core/test_navigation.py` recorre `INSTALLED_APPS` y falla si una app
  con páginas propias (salvo `core` y `moainvest`) no tiene su `App(...)` en
  `APPS`: una subapp nueva no puede quedarse fuera del sidebar. Dale también
  un `url_prefix="/app/<slug>"` a su blueprint de páginas.
- El logo de la barra superior enlaza a **Inicio** (`moainvest.resumen`, `/`)
  para volver al sitio rojo (ver «Estética del área App»).

### Graficador

App `app/graficador/` (layout oscuro con sidebar) en `/app/graficador/`: el
gráfico de **cualquier ticker de Yahoo Finance** (`?ticker=AAPL`, `^GSPC`,
`BTC-USD`, `EURUSD=X`...; por defecto, el primer símbolo de la watchlist por
defecto). Es la primera entrada del sidebar y sustituye al antiguo enlace
«Gráficas» a `/graficas`.

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
| `dukascopy` | Feed público de Dukascopy Bank, sin clave. Intradía de 1m a 1h con mucha más historia que Yahoo (hasta 1 mes a 1m, 1 año a 5-30m y 5 años a 1h); divisas, cripto, índices, materias primas y acciones (CFD, precio *bid*) |

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

**Dukascopy** traduce el ticker de Yahoo a su instrumento
(`dukascopy_instrument`): `AAPL` → `AAPL.US/USD`, `EURUSD=X` → `EUR/USD`,
`BTC-USD` → `BTC/USD`, `SAN.MC` → `SAN.ES/EUR` (también `.DE`, `.PA`, `.AS`,
`.MI`, `.SW` y `.L`) y una tabla `DK_SYMBOLS` para índices y futuros (`^GSPC` →
`USA500.IDX/USD`, `GC=F` → `XAU/USD`...). Lo que no tiene equivalente (`^IXIC`,
bolsas asiáticas) responde 422 con el aviso de usar Yahoo. A 1-30 minutos el
feed devuelve como mucho ~1 mes por petición, así que el rango se parte en
ventanas de 2-4 semanas que se descargan en paralelo (1 año a 5m, unas 70 000
velas, tarda ~3-4 s); el resultado se cachea `DUKASCOPY_CACHE_TTL` segundos
(60 por defecto). Como con Yahoo, el rango se cuenta desde la última vela: «1D»
en fin de semana muestra el último día con mercado.

**Periodicidad (solo Dukascopy)**: con Dukascopy aparece un segundo selector,
*Periodicidad*, agrupado como en su plataforma: **segundos** (1s, 10s, 30s),
**minutos** (1m, 5m, 10m, 15m, 30m), **horas** (1h, 4h) y **días y más** (1D,
1S, 1M). En *auto* la periodicidad la decide el botón de rango, como con los
demás proveedores. Cada periodicidad tiene una historia máxima (`max_days`: 1
día a 1s, 5 a 10s, 14 a 30s, 1 mes a 1m, 1 año a 5-30m, 5 años a 1h, sin límite
a 4h o más) y los botones de rango que la superan se desactivan. La elección se
recuerda por proveedor en `localStorage` (`graficador:interval:v1`). Un
proveedor ofrece periodicidades propias con `interval_choices` (lo publica
`/api/graficador/providers` en `intervals`); pedir a otro proveedor una que no
admite (`?provider=yahoo&interval=1s`) responde 422.

**Añadir un proveedor**: una subclase de `Provider` registrada en `PROVIDERS`.
Aparece sola en el selector y en la API.

### Estética de Informes y Análisis de varianza

`/app/informes/` y `/app/analisis-varianza/` siguen la marca del sitio rojo
(blancos, rojos y negros, Geist): cabecera con eyebrow mono y título grande,
tarjetas blancas con borde `line` y botones pill rojos. Sus estilos están solo
en las secciones "Análisis de Varianza" e "Informes" de
`app/core/static/css/style.css`, sobre los tokens del `:root`.

- Las clases base `.varianza-page`, `.varianza-form*`, `.varianza-table*`,
  `.varianza-status` y `.volatility-*` también las usa Quant stats: conserva
  su estructura. Lo propio de cada página lleva su prefijo (`.varianza-hero`,
  `.varianza-chip`, `.informes-card`, `.informes-btn`...).
- El campo de tickers de la volatilidad crea chips con Intro, coma o espacio
  (`varianza.js`); el máximo sale de `MAX_VOLATILITY_TICKERS` de `api.py`.
- Los fondos de vídeo/imagen de Informes se pasan a blanco y negro y llevan
  un overlay negro→rojo; el canvas de respaldo usa los mismos colores.
- Las gráficas del servidor (`varianza/analysis.py` e
  `informes/report_charts.py`) usan `PALETTE`, `MPL_RC`, `UP` y `DOWN` de
  `app/core/charts.py` dentro de `rc_context`, sin cambiar el tema global de
  matplotlib. El email (`informes/emails/market_report.html`) usa los mismos
  colores con estilos en línea y tablas.

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

Las páginas de `app/quant_stats/` (`/app/quant-stats/fundamentales`,
`/revision` y el tearsheet) siguen la marca MOAINVEST del sitio rojo:

- Plantillas: `quant_stats/_base.html` extiende `core/base.html`, carga Geist y
  pinta la cabecera (eyebrow mono, ticker y nombre grandes); las páginas
  rellenan los bloques `hero_eyebrow`, `hero_lead`, `hero_extra` y `page`.
  Estilos propios con prefijo `qs-` (pestañas pill, tarjetas de métricas,
  tablas, formularios y botones pill rojos) en las secciones «Análisis UEC» y
  «QUANT STATS» de `app/core/static/css/style.css`; no usan las clases
  `varianza-*`.
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
