# Auditoría mínima (Insights)

- Layout: `core/base.html` (topbar + sidebar), bloques `title`, `head`, `content` y `scripts`. Se extiende sin tocarlo.
- CSS reutilizado: `core/static/css/style.css` (ya lo enlaza el layout), con los tokens `--brand #c8102e`, `--brand-deep #8f1025`, `--brand-soft #fbeef0`, `--ink #171717`, `--muted #6b6b6b`, `--paper #fff`, `--mist #f7f7f5`, `--line #e6e4df`, `--up #0f8a5f`, `--up-soft`, `--down-soft` y `--shadow-card`.
- Componentes que se reutilizan tal cual: `qs-hero`, `qs-page`, `qs-form`, `qs-input`, `qs-select`, `qs-btn`, `qs-section`, `qs-metric`, `qs-card`, `qs-table`, `qs-status`, `qs-tag` y `qs-hint`.
- Tipografías: Geist (texto), Geist Mono (cifras) e Instrument Serif itálica (acento rojo).
- Gráficos: lightweight-charts v5 en el navegador (vendorizado en core) con esos tokens, y matplotlib (Agg) en el servidor con `app.core.charts.MPL_RC` y `PALETTE`.
- Datos: solo `app.core.market_data` (`get_candles`, `get_quote` y `get_display_name`). QuantStats 0.0.81 con pandas 3.0.5; hoy lo usa `app/quant_stats/quant.py` (rf = 0, 252 periodos).
- Estilos extra: `app/insights/static/insights.css`, solo con esos tokens.
