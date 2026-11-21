/*
 * Insights: curva de capital y drawdown con lightweight-charts v5 (la misma
 * librería y los mismos tokens de color que el Graficador), más el estado
 * "Calculando…" del formulario. Sin framework.
 */
(function () {
  "use strict";

  // Estado de carga al enviar el formulario o usar un ejemplo.
  const loading = document.querySelector("[data-insights-loading]");
  const showLoading = () => { if (loading) loading.hidden = false; };
  const form = document.querySelector("[data-insights-form]");
  if (form) form.addEventListener("submit", showLoading);
  document.querySelectorAll("[data-insights-link]").forEach((a) => a.addEventListener("click", showLoading));

  const dataEl = document.getElementById("insights-data");
  const LC = window.LightweightCharts;
  if (!dataEl || !LC) return;

  let data;
  try {
    data = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }

  const css = getComputedStyle(document.documentElement);
  const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  const THEME = {
    bg: token("--paper", "#ffffff"),
    line: token("--line", "#e6e4df"),
    text: token("--muted", "#6b6b6b"),
    ink: token("--ink", "#171717"),
    brand: token("--brand", "#c8102e"),
    brandSoft: token("--brand-soft", "#fbeef0"),
    font: token("--font-mono", "monospace"),
  };

  function makeChart(el, suffix) {
    el.textContent = "";
    return LC.createChart(el, {
      autoSize: true,
      layout: { background: { type: LC.ColorType.Solid, color: THEME.bg }, textColor: THEME.text, fontFamily: THEME.font, fontSize: 11 },
      grid: { vertLines: { color: THEME.line }, horzLines: { color: THEME.line } },
      rightPriceScale: { borderColor: THEME.line },
      timeScale: { borderColor: THEME.line },
      crosshair: { vertLine: { labelBackgroundColor: THEME.ink }, horzLine: { labelBackgroundColor: THEME.ink } },
      localization: { locale: "es-ES", priceFormatter: (v) => v.toFixed(1) + suffix },
    });
  }

  function empty(el, text) {
    el.innerHTML = "";
    const p = document.createElement("p");
    p.className = "insights-chart__loading";
    p.textContent = text;
    el.appendChild(p);
  }

  const equityEl = document.getElementById("insights-equity");
  if (equityEl && data.equity && data.equity.strategy.length) {
    const chart = makeChart(equityEl, "");
    chart.addSeries(LC.LineSeries, { color: THEME.brand, lineWidth: 2 }).setData(data.equity.strategy);
    chart.addSeries(LC.LineSeries, { color: THEME.ink, lineWidth: 2, lineStyle: LC.LineStyle.Dashed }).setData(data.equity.benchmark);
    chart.timeScale().fitContent();
  } else if (equityEl) {
    empty(equityEl, "Sin datos para dibujar la curva.");
  }

  const ddEl = document.getElementById("insights-drawdown");
  if (ddEl && data.drawdown && data.drawdown.strategy.length) {
    const chart = makeChart(ddEl, " %");
    chart
      .addSeries(LC.AreaSeries, { lineColor: THEME.brand, topColor: THEME.brandSoft, bottomColor: THEME.brand, lineWidth: 2, invertFilledArea: true })
      .setData(data.drawdown.strategy);
    chart.addSeries(LC.LineSeries, { color: THEME.ink, lineWidth: 1, lineStyle: LC.LineStyle.Dashed }).setData(data.drawdown.benchmark);
    chart.timeScale().fitContent();
  } else if (ddEl) {
    empty(ddEl, "Sin datos para dibujar las caídas.");
  }
})();
