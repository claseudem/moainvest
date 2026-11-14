// Pronosticador: pide los datos a la API y pinta semáforo, KPIs, gráficos Plotly y auditoría.
(function () {
  "use strict";

  const page = document.getElementById("pron-page");
  if (!page) return;

  const $ = (id) => document.getElementById(id);
  const lagsSelect = $("pron-lags");
  const retrainBtn = $("pron-retrain");
  const statusEl = $("pron-status");
  const errorEl = $("pron-error");
  const bodyEl = $("pron-body");

  // Colores de la marca (core/static/css/style.css).
  const css = getComputedStyle(document.documentElement);
  const color = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  const C = {
    ink: color("--ink", "#171717"),
    muted: color("--muted", "#6b6b6b"),
    line: color("--line", "#e6e4df"),
    brand: color("--brand", "#c8102e"),
    brandDeep: color("--brand-deep", "#8f1025"),
    up: color("--up", "#0f8a5f"),
    amber: "#b7791f",
  };
  const font = { family: color("--font-sans", "sans-serif"), color: C.muted, size: 11 };
  const baseLayout = () => ({
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font,
    margin: { l: 50, r: 16, t: 12, b: 40 },
    xaxis: { gridcolor: C.line, zerolinecolor: C.line },
    yaxis: { gridcolor: C.line, zerolinecolor: C.line },
  });
  const plotConfig = { responsive: true, displayModeBar: false };

  const pct = (v, d = 2) => (v == null ? "—" : (v * 100).toFixed(d) + "%");
  const usd = (v) => (v == null ? "—" : "$" + Number(v).toFixed(2));

  function showStatus(text) {
    statusEl.textContent = text;
    statusEl.hidden = !text;
  }

  function showError(message) {
    $("pron-error-msg").textContent = message;
    errorEl.hidden = false;
    bodyEl.hidden = true;
    showStatus("");
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options);
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      /* respuesta no JSON */
    }
    if (!res.ok) throw new Error((data && data.error) || `Error ${res.status} del servidor.`);
    return data;
  }

  function renderDecision(data) {
    const card = $("pron-decision");
    card.classList.remove("is-green", "is-yellow", "is-red");
    card.classList.add("is-" + data.decision_color);
    $("pron-decision-text").textContent = data.decision;
    $("pron-decision-desc").textContent = data.decision_desc;
    $("pron-acierto").textContent = data.tasa_acierto.toFixed(1) + "%";
    $("pron-prob").textContent = data.prob_ganancia.toFixed(1) + "%";
  }

  function renderKpis(data) {
    const m = data.metricas;
    $("kpi-cierre").textContent = usd(m.ultimo_cierre);
    $("kpi-precio").textContent = usd(m.precio_esperado_t1);
    $("kpi-retorno").textContent = "μ(t+1): " + pct(m.mu_t1, 4);
    $("kpi-vol").textContent = pct(m.sigma_t1 * Math.sqrt(252));
    $("kpi-var95").textContent = pct(m.var_95);
    $("kpi-cvar95").textContent = pct(m.cvar_95);
    $("kpi-coint").textContent = data.coint_pval == null ? "—" : data.coint_pval.toFixed(3);
    $("kpi-adf").textContent = "ADF p-val: " + (data.adf_pval == null ? "—" : data.adf_pval.toExponential(2));
  }

  function renderCharts(data) {
    const m = data.metricas;

    // 1. Serie + cono de confianza a t+1
    const fechas = data.historico.fechas;
    const precios = data.historico.precios;
    const lastDate = fechas[fechas.length - 1];
    const lastPrice = precios[precios.length - 1];
    const next = "t+1";
    const pEsp = m.precio_esperado_t1;
    const pUp = pEsp * Math.exp(1.96 * m.sigma_t1);
    const pDown = pEsp * Math.exp(-1.96 * m.sigma_t1);
    Plotly.react(
      "chart-serie",
      [
        { x: fechas, y: precios, type: "scatter", mode: "lines", name: "Spot", line: { color: C.ink, width: 2 } },
        {
          x: [lastDate, next, next, lastDate],
          y: [lastPrice, pUp, pDown, lastPrice],
          type: "scatter",
          fill: "toself",
          fillcolor: "rgba(200, 16, 46, 0.12)",
          line: { color: "transparent" },
          name: "Banda 95%",
        },
        { x: [lastDate, next], y: [lastPrice, pEsp], mode: "lines+markers", name: "Esperado", line: { color: C.brand, dash: "dot", width: 2 } },
      ],
      { ...baseLayout(), showlegend: true, legend: { orientation: "h", y: -0.2 } },
      plotConfig,
    );

    // 2. Monte Carlo
    Plotly.react(
      "chart-montecarlo",
      data.montecarlo.trayectorias.map((tray) => ({
        x: data.montecarlo.dias,
        y: tray,
        type: "scatter",
        mode: "lines",
        line: { width: 1, color: C.brand },
        opacity: 0.3,
        showlegend: false,
        hoverinfo: "y",
      })),
      { ...baseLayout(), xaxis: { ...baseLayout().xaxis, title: { text: "Días futuros" } } },
      plotConfig,
    );

    // 3. Distribución de retornos con VaR 95/99
    const var95 = -(m.var_95 * 100);
    const var99 = -(m.var_99 * 100);
    Plotly.react(
      "chart-densidad",
      [{ x: data.retornos_hist, type: "histogram", nbinsx: 35, marker: { color: "rgba(23, 23, 23, 0.55)" }, name: "Retornos (%)" }],
      {
        ...baseLayout(),
        bargap: 0.04,
        shapes: [
          { type: "line", x0: var95, x1: var95, y0: 0, y1: 1, yref: "paper", line: { color: C.brand, width: 2, dash: "dash" } },
          { type: "line", x0: var99, x1: var99, y0: 0, y1: 1, yref: "paper", line: { color: C.brandDeep, width: 2, dash: "dot" } },
        ],
        annotations: [
          { x: var95, y: 0.95, yref: "paper", text: "VaR 95%", showarrow: false, xanchor: "left", font: { color: C.brand, size: 10 } },
          { x: var99, y: 0.8, yref: "paper", text: "VaR 99%", showarrow: false, xanchor: "right", font: { color: C.brandDeep, size: 10 } },
        ],
      },
      plotConfig,
    );

    // 4. Volatilidad condicional GARCH
    Plotly.react(
      "chart-garch",
      [
        {
          x: data.garch_vol.fechas,
          y: data.garch_vol.valores,
          type: "scatter",
          mode: "lines",
          fill: "tozeroy",
          fillcolor: "rgba(183, 121, 31, 0.12)",
          line: { color: C.amber, width: 1.5 },
          name: "Vol. condicional (%)",
        },
      ],
      { ...baseLayout(), yaxis: { ...baseLayout().yaxis, title: { text: "Vol. anualizada %" } } },
      plotConfig,
    );
  }

  function renderAudit(records) {
    const tbody = $("pron-audit-body");
    tbody.replaceChildren();
    if (!records || records.length === 0) {
      const tr = tbody.insertRow();
      const td = tr.insertCell();
      td.colSpan = 6;
      td.textContent = "Sin registros en audit_pipeline_runs.";
      return;
    }
    const num = (v, d) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(d));
    for (const r of records) {
      const tr = tbody.insertRow();
      const cells = [
        String(r.run_timestamp ?? "").replace("T", " ").slice(0, 19),
        r.status ?? "—",
        num(r.r_squared, 5),
        r.var_95 == null ? "—" : pct(Number(r.var_95)),
        r.var_99 == null ? "—" : pct(Number(r.var_99)),
        num(r.precio_esperado, 4),
      ];
      cells.forEach((text, i) => {
        const td = tr.insertCell();
        if (i === 1) {
          const pill = document.createElement("span");
          pill.className = "pill" + (String(text).toLowerCase() === "success" ? " is-up" : "");
          pill.textContent = text;
          td.append(pill);
        } else {
          td.textContent = text;
        }
      });
    }
  }

  async function load(lags) {
    showStatus("Cargando datos y estimando el modelo…");
    errorEl.hidden = true;
    try {
      const data = await fetchJson(`${page.dataset.apiUrl}?lags=${encodeURIComponent(lags)}`);
      bodyEl.hidden = false;
      renderDecision(data);
      renderKpis(data);
      renderCharts(data);
      renderAudit(data.audit_records);
      $("pron-fuente").textContent = "Fuente: " + data.fuente;
      $("pron-audit-note").hidden = data.fuente === "MotherDuck";
      showStatus("");
    } catch (err) {
      showError(err.message);
    }
  }

  async function retrain(event) {
    event.preventDefault();
    const lags = lagsSelect.value;
    const label = retrainBtn.querySelector("span");
    retrainBtn.disabled = true;
    label.textContent = "Entrenando…";
    try {
      await fetchJson(page.dataset.trainUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lags: parseInt(lags, 10) }),
      });
      await load(lags);
    } catch (err) {
      showError(err.message);
    } finally {
      retrainBtn.disabled = false;
      label.textContent = "Re-estimar modelo";
    }
  }

  $("pron-controls").addEventListener("submit", retrain);
  lagsSelect.addEventListener("change", () => load(lagsSelect.value));

  if (typeof Plotly === "undefined") {
    showError("No se pudo cargar la librería de gráficos (Plotly). Revisa tu conexión.");
    return;
  }
  load(lagsSelect.value);
})();
