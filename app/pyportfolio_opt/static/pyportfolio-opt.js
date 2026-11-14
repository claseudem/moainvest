/**
 * Vista "Pyportfolio opt": pide los retornos esperados a la API de la app,
 * los muestra en una tabla (una columna por metodología) y carga la gráfica
 * de barras generada en el servidor.
 */
(function () {
  "use strict";

  const form = document.getElementById("pypfopt-form");
  if (!form) return; // esta página no está montada

  const tickersInput = document.getElementById("pypfopt-tickers");
  const methodSelect = document.getElementById("pypfopt-method");
  const periodSelect = document.getElementById("pypfopt-period");
  const spanInput = document.getElementById("pypfopt-span");
  const spanField = document.getElementById("pypfopt-span-field");
  const compoundingInput = document.getElementById("pypfopt-compounding");
  const logReturnsInput = document.getElementById("pypfopt-log-returns");
  const submitBtn = document.getElementById("pypfopt-submit");
  const statusEl = document.getElementById("pypfopt-status");
  const resultEl = document.getElementById("pypfopt-result");
  const summaryEl = document.getElementById("pypfopt-summary");
  const tableHead = document.getElementById("pypfopt-table-head");
  const tableBody = document.getElementById("pypfopt-table-body");
  const chartImg = document.getElementById("pypfopt-chart-img");
  const maxTickers = Number(form.dataset.maxTickers) || 10;
  let lastChartObjectUrl = null;

  function setStatus(message, isError) {
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("is-error", Boolean(isError));
  }

  function parseTickers(text) {
    return [...new Set(text.split(/[\s,;]+/).map((t) => t.trim().toUpperCase()).filter(Boolean))];
  }

  function fmtPercent(value) {
    if (value === null || value === undefined) return "—";
    return `${(value * 100).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`;
  }

  function fmtDate(iso) {
    return new Date(`${iso}T00:00:00`).toLocaleDateString("es-ES", { year: "numeric", month: "2-digit", day: "2-digit" });
  }

  // El span solo aplica a la EMA.
  function syncSpanField() {
    const usesEma = methodSelect.value !== "historical";
    spanField.hidden = !usesEma;
    spanInput.disabled = !usesEma;
  }
  methodSelect.addEventListener("change", syncSpanField);
  syncSpanField();

  document.querySelectorAll("#pypfopt-suggest [data-ticker]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tickers = parseTickers(tickersInput.value);
      if (tickers.includes(btn.dataset.ticker)) return;
      if (tickers.length >= maxTickers) {
        setStatus(`Máximo ${maxTickers} tickers a la vez.`, true);
        return;
      }
      tickersInput.value = [...tickers, btn.dataset.ticker].join(", ");
      setStatus("");
    });
  });

  function renderTable(data) {
    const head = ["Activo", "Desde", "Hasta", "Observaciones", ...data.methods.map((m) => m.name)];
    tableHead.replaceChildren(
      ...head.map((label) => {
        const th = document.createElement("th");
        th.textContent = label;
        return th;
      }),
    );

    const fragment = document.createDocumentFragment();
    data.assets.forEach((asset) => {
      const tr = document.createElement("tr");
      [asset.ticker, fmtDate(asset.start), fmtDate(asset.end), asset.observations.toLocaleString("es-ES")].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      data.methods.forEach((method) => {
        const td = document.createElement("td");
        const value = asset[method.id];
        const pill = document.createElement("span");
        pill.className = `pill ${value >= 0 ? "is-up" : "is-down"}`;
        pill.textContent = fmtPercent(value);
        td.appendChild(pill);
        tr.appendChild(td);
      });
      fragment.appendChild(tr);
    });
    tableBody.replaceChildren(fragment);
  }

  function describe(data) {
    const parts = [
      `${data.assets.length} activo${data.assets.length === 1 ? "" : "s"}`,
      `frecuencia ${data.frequency} días`,
      data.compounding ? "capitalización compuesta" : "sin capitalizar",
      data.log_returns ? "retornos logarítmicos" : "retornos simples",
    ];
    if (data.methods.some((m) => m.id === "ema")) parts.push(`span ${data.span}`);
    let text = parts.join(" · ");
    if (data.missing.length) text += `. Sin datos suficientes: ${data.missing.join(", ")}`;
    return text;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const tickers = parseTickers(tickersInput.value);
    if (!tickers.length) {
      setStatus("Añade al menos un ticker.", true);
      return;
    }
    if (tickers.length > maxTickers) {
      setStatus(`Máximo ${maxTickers} tickers a la vez.`, true);
      return;
    }

    const params = new URLSearchParams({
      tickers: tickers.join(","),
      period: periodSelect.value,
      method: methodSelect.value,
      span: spanInput.value || "500",
      compounding: compoundingInput.checked ? "1" : "0",
      log_returns: logReturnsInput.checked ? "1" : "0",
    });

    submitBtn.disabled = true;
    resultEl.hidden = true;
    setStatus("Descargando precios y calculando retornos esperados…");

    fetch(`/api/pyportfolio-opt/expected-returns?${params}`)
      .then(async (res) => {
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.error || "Error al calcular los retornos esperados");
        return payload;
      })
      .then((data) => {
        renderTable(data);
        summaryEl.textContent = describe(data);
        resultEl.hidden = false;
        setStatus("");
        chartImg.hidden = true;
        return fetch(`/api/pyportfolio-opt/expected-returns.png?${params}`)
          .then((res) => (res.ok ? res.blob() : null))
          .then((blob) => {
            if (!blob) return;
            if (lastChartObjectUrl) URL.revokeObjectURL(lastChartObjectUrl);
            lastChartObjectUrl = URL.createObjectURL(blob);
            chartImg.src = lastChartObjectUrl;
            chartImg.hidden = false;
          });
      })
      .catch((err) => {
        setStatus(err.message || "Ocurrió un error al calcular los retornos esperados.", true);
      })
      .finally(() => {
        submitBtn.disabled = false;
      });
  });
})();
