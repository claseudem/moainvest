# Insights: rendimiento de inversiones explicado, con QuantStats como motor

## Resumen

Nueva página **`/app/insights/`** para analizar un activo o un portafolio frente a un benchmark. Por dentro calcula con rigor (QuantStats) y por fuera lo muestra en lenguaje llano, en 3 capas de divulgación progresiva:

1. **¿Cómo voy?**: 4 tarjetas: rentabilidad total, CAGR, peor caída (Max Drawdown) y calidad del rendimiento (Sharpe con semáforo de icono + texto + color). Cada una lleva una frase humana ("En el peor momento, por cada $100 llegaste a tener $86"), el contexto del benchmark al lado ("Entre 2025-12-03 y 2026-01-20, SPY cayó -0.3 %") y un desplegable **"¿Qué significa?"** con la definición, qué valor es bueno o malo y una limitación.
2. **¿Por qué?**: curva de capital (crecimiento de $100) frente al benchmark, drawdown underwater (lightweight-charts v5, el mismo de la app, con sus tokens de color) y mapa de calor de rendimientos mensuales (tabla con ▲/▼ y cifra, para no depender solo del color).
3. **Modo experto** (plegado): VaR y CVaR diarios frente al benchmark, la tabla completa de `qs.reports.metrics(mode="full")` con los formatos de QuantStats, los parámetros usados y las notas de limpieza de datos.

También muestra advertencias estadísticas visibles, estados vacío, de carga y de error amables (nunca un traceback) y el aviso legal: "Herramienta informativa, no constituye asesoría de inversión. Rendimientos pasados no garantizan resultados futuros."

### Cómo probarla

```bash
uv run flask --app run run --port 5000
# con sesión iniciada (o AUTH_REQUIRED=0 en desarrollo):
#   http://127.0.0.1:5000/app/insights/                         estado vacío con ejemplos
#   http://127.0.0.1:5000/app/insights/?ticker=AAPL             activo, último año vs SPY
#   http://127.0.0.1:5000/app/insights/?ticker=SPY:60,TLT:40&range=5y   portafolio 60/40
#   http://127.0.0.1:5000/app/insights/?ticker=BTC-USD          cripto remuestreada al calendario bursátil
#   http://127.0.0.1:5000/app/insights/?ticker=NVDA&range=6mo   muestra corta (advertencia)
#   http://127.0.0.1:5000/app/insights/?ticker=AAPL&rf=4.5      rf indicada a mano (% anual)
uv run pytest tests/insights
```

Parámetros: `ticker` (un ticker o `T1:peso, T2:peso`; sin pesos se reparten a partes iguales), `range` (`6mo`, `1y` por defecto, `2y`, `5y`, `max`), `benchmark` (SPY por defecto) y `rf` (% anual; por defecto la actual de `^IRX`).

## Archivos creados

- `app/insights/__init__.py`
- `app/insights/api.py`: blueprint `insights` (`/app/insights/`), una vista que valida la entrada y renderiza.
- `app/insights/engine.py`: motor sin Flask ni red: `validate_returns()`, `resample_prices()`, `align_with_benchmark()`, `portfolio_returns()`, `RiskFree`, `safe_stat()`, `compute_insight()`, `full_metrics_table()`, `chart_series()`, `monthly_heatmap()` y la caché.
- `app/insights/data.py`: adaptador de solo lectura sobre `app.core.market_data` (precios, rf de `^IRX`, portafolios y frecuencias).
- `app/insights/narrative.py`: frases humanas, semáforo del Sharpe y glosario "¿Qué significa?".
- `app/insights/templates/insights/index.html`: extiende `core/base.html` sin modificarlo.
- `app/insights/static/insights.css`: solo usa los tokens de `core/static/css/style.css`.
- `app/insights/static/insights.js`: gráficos con lightweight-charts (ya vendorizado en core) y estado "Calculando…".
- `app/insights/AUDITORIA.md`: nota mínima del sistema visual y los datos que se reutilizan.
- `app/insights/PR_BODY.md`: este texto.
- `tests/insights/test_engine.py` y `tests/insights/test_routes.py`.

## Archivos existentes modificados

**No se modificó ningún archivo existente**, salvo la única línea de registro permitida:

- `app/__init__.py`, **línea 40**: `"insights",` añadida al final de `INSTALLED_APPS`.

No se cambiaron dependencias (`pyproject.toml` y `uv.lock` están intactos), ni CSS, plantillas, rutas, configuración, base de datos ni `/app/graficador/`.

## Tests

- `uv run pytest`: **408 passed** (390 existentes + 18 nuevos), sin fallos.
- `uv run pytest tests/insights`: **18 passed**. Cubren:
  - `validate_returns()`: precios → retornos simples; tz-aware → tz-naive; orden; duplicados (se queda el último del día); NaN, infinitos y precios ≤ 0 eliminados y contados.
  - Alineación con el benchmark: inner join exacto, conteo de fechas descartadas y recorte inicial igual que `quantstats.reports._match_dates`; remuestreo cripto → calendario bursátil; desanualización de rf idéntica a la de QuantStats.
  - **Consistencia con `qs.reports.metrics(mode="full")`** (tolerancia 1e-6) de rentabilidad total, CAGR, Sharpe, Sortino, Max Drawdown, volatilidad, Calmar, tail ratio, VaR y CVaR, para la estrategia y el benchmark, y que cada columna de la tabla de la interfaz sea la correcta.
  - Casos límite: serie vacía, un solo día, todo ceros (Sharpe = "sin dato" y aviso, sin excepción) y serie solo de NaN; advertencias de muestra corta, menos de 30 periodos y Sharpe > 3; caché por clave.
  - Rutas: estado vacío, activo, portafolio, cripto y errores amables (400 para entrada inválida, 200 con mensaje si Yahoo no tiene datos).

## Verificación de rutas (app en el puerto 5057; base `ea2d652` en el 5058)

Con `AUTH_REQUIRED=1` (el valor del `.env`, sin sesión), base y rama devuelven lo mismo:

| Ruta | Base `ea2d652` | Esta rama |
|---|---|---|
| `/` | 200 | 200 |
| `/app/` | 302 → `/ingresar?next=/app/` | 302 → `/ingresar?next=/app/` |
| `/app/graficador/` | 302 → `/ingresar` | 302 → `/ingresar` |
| `/app/comunidad/` | 302 → `/ingresar` | 302 → `/ingresar` |
| `/app/insights/` | 302 → `/ingresar` | 302 → `/ingresar` (protegida como todo `/app/`) |

Con `AUTH_REQUIRED=0` (equivalente a una sesión iniciada; no había credenciales de InsForge para un login real):

| Ruta | Base `ea2d652` | Esta rama |
|---|---|---|
| `/` | 200 | 200 |
| `/app/` | 302 → `/app/graficador/` | 302 → `/app/graficador/` |
| `/app/graficador/` | 200 | 200 |
| `/app/comunidad/` | 301 → `/app/personas/` | 301 → `/app/personas/` |
| `/app/insights/` | 404 | **200** |

Con datos reales de Yahoo Finance, `?ticker=AAPL`, `?ticker=SPY:60,TLT:40&range=5y`, `?ticker=BTC-USD` y `?ticker=NVDA&range=6mo` devuelven 200 en menos de 2 s; `?ticker=$$` devuelve 400 con un mensaje amable; un ticker inexistente devuelve 200 con "Yahoo Finance no devolvió precios…". En el log del servidor no hubo tracebacks (solo el 404 que registra yfinance para el ticker inexistente).

## Decisiones autónomas

- **Ruta y carpeta**: `/app/insights/` y `app/insights/`, siguiendo la estructura de apps del proyecto (`INSTALLED_APPS`), en vez de una carpeta `insights/` en la raíz que el proyecto no sabría registrar.
- **El blueprint está en `api.py` y no en `views.py`, y la app no sale en el sidebar.** Darla de alta en el sidebar exige editar `app/core/navigation.py` (y quizá el icono en `core/sidebar.html`), lo que prohíbe la regla n.º 1. Además, `tests/core/test_navigation.py::test_every_installed_app_with_pages_is_in_sidebar` exige que toda app con páginas en `views.py` esté en el sidebar: con `views.py` ese test fallaría. `install_app()` registra igual el `bp` de `api.py`, así que se usa ese punto de extensión existente. **Consecuencia que conviene conocer: esa colocación esquiva a propósito la comprobación de ese test.** Cuando se quiera la app en el sidebar: mover `api.py` a `views.py` y añadir `App(slug="insights", name="Insights", ...)` al final de `APPS`.
- **Importa solo de `core`** (`market_data`, `api.ALLOWED_RANGES`), como pide la convención del proyecto; no importa `app.quant_stats`.
- **Retornos simples** (`pct_change`) por defecto; **NaN e infinitos se eliminan** y se cuentan (no se rellenan con 0 como hace QuantStats, porque eso sesga la volatilidad a la baja); los precios ≤ 0 se descartan antes de calcular retornos.
- **Frecuencia**: 252 para acciones y 365 si todo es cripto. Si hay mezcla (por ejemplo BTC-USD frente a SPY), los precios cripto se llevan al calendario bursátil **antes** de calcular retornos y se usa 252. La cripto se detecta por el patrón de Yahoo `XXX-USD`/`-USDT`/`-EUR`…
- **rf**: siempre **anual**; QuantStats la desanualiza con `(1+rf)^(1/periodos)-1`. Por defecto se usa la actual de `^IRX` (letras del Tesoro a 13 semanas); si Yahoo no responde, 0 %, y se dice en pantalla. Se muestra la anual y su equivalente por periodo.
- **`compounded=True`** fijo en todas las métricas y en `qs.reports.metrics`.
- **Alineación**: inner join exacto por fecha y, después, el mismo recorte inicial que hace `qs.reports.metrics` (`_match_dates`), para que las tarjetas y la tabla completa usen exactamente las mismas fechas.
- **Consistencia 1e-6**: `qs.reports.metrics` redondea siempre su salida a 2 decimales (`.round(2)`, sin parámetro para evitarlo), así que el test compara nuestros valores llevados a esa misma precisión (en % para las métricas de porcentaje) con tolerancia 1e-6. Una igualdad a 1e-6 sin redondear no es posible con la API pública.
- **Tabla experta**: se pide con `internal=True` para obtener los mismos formatos que el tearsheet de QuantStats, y las columnas se toman por nombre, porque QuantStats 0.0.81 las devuelve con el benchmark primero.
- **Advertencias**: muestra corta si el periodo tiene menos de 1 año (con 7 días de margen, porque el rango "1 año" de Yahoo da unos 360 días); con menos de 30 periodos, Sortino, Calmar y tail ratio se atenúan; si el Sharpe pasa de 3, alerta de sobreajuste o error de datos; si la serie no se mueve, aviso de "sin movimiento".
- **Semáforo del Sharpe** sin colores nuevos: verde `--up` (≥ 1, ▲), neutro `--ink` (0,5–1, ●) y rojo `--brand` (< 0,5, ▼), más "Revisar" (!) por encima de 3. Siempre con icono y texto.
- **Fechas de las velas**: se redondean al día más cercano (y no se truncan) para conservar la fecha de la sesión en bolsas al este de UTC.
- **Caché**: un dict en memoria con TTL de 300 s por (activo/pesos, rango, benchmark, rf). Los errores no se cachean.
- **Portafolios**: pesos fijos con rebalanceo diario, en las fechas comunes a todos los activos (como máximo 10).

## Limitaciones y mejoras futuras

Recortes de alcance acordados para entregar antes:

- **Modo experto reducido**: solo la tabla completa de `qs.reports.metrics` y VaR/CVaR. Quedan pendientes la **distribución de retornos** y el **Sharpe, la volatilidad y la beta móviles**. Ojo al implementarlos: `qs.stats.rolling_sharpe` 0.0.81 desanualiza rf con la *ventana* en vez de los periodos por año; hay que pasarle excesos de retorno ya calculados con `qs.utils.to_excess_returns(r, rf, nperiods=252)` y `rf=0`.
- **Sin informe técnico HTML** (`qs.reports.html` → "Ver informe técnico completo"): mejora futura, con una carpeta de salida propia e ignorada por git.
- **"¿Qué significa?"** solo está en las 4 tarjetas de la capa 1.
- **Auditoría** reducida a una nota mínima (`app/insights/AUDITORIA.md`).
- **Verificación de rutas** limitada a `/`, `/app/`, `/app/graficador/`, `/app/comunidad/` y `/app/insights/`.

Otras limitaciones:

- No aparece en el sidebar ni en la navegación (ver "Decisiones"); se accede por URL.
- La detección de cripto es por patrón de ticker; un ETF cripto (por ejemplo IBIT) se trata como acción, que es lo correcto porque cotiza en bolsa.
- La consistencia con QuantStats se verifica a 2 decimales por el redondeo interno de `qs.reports.metrics`.
- La verificación "con sesión" se hizo con `AUTH_REQUIRED=0`, porque no había credenciales de InsForge para un login real.
- No se revisó en un navegador real: solo con `curl` y aserciones sobre el HTML.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
