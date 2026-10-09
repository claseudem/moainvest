(function () {
  "use strict";

  const form = document.getElementById("regresion-form");
  if (!form) return;

  const status = document.getElementById("regresion-status");
  const trainButton = document.getElementById("train-button");
  const results = document.getElementById("regresion-results");
  const resultsBody = document.getElementById("results-body");
  const featureBody = document.getElementById("feature-drift-body");
  const modelSelect = document.getElementById("drift-model-select");
  const driftChart = document.getElementById("drift-chart");

  function setStatus(message, isError) {
    status.hidden = !message;
    status.textContent = message || "";
    status.classList.toggle("is-error", Boolean(isError));
  }

  function format(value, digits = 6) {
    return Number.isFinite(value) ? value.toFixed(digits) : "—";
  }

  function addCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.appendChild(cell);
  }

  function showChart(data) {
    const selected = data.resultados.find((item) => item.modelo === modelSelect.value);
    if (selected && selected.grafico) driftChart.src = selected.grafico;
  }

  function render(data) {
    resultsBody.replaceChildren();
    featureBody.replaceChildren();
    modelSelect.replaceChildren();
    const chartModels = data.resultados.filter((item) => item.grafico);

    data.resultados.forEach((item) => {
      const row = document.createElement("tr");
      addCell(row, item.modelo);
      ["train", "test"].forEach((split) => {
        const metrics = item[split];
        addCell(row, format(metrics.mae));
        addCell(row, format(metrics.rmse));
        addCell(row, format(metrics.r2, 4));
        addCell(row, `${format(metrics.acierto_direccional * 100, 1)}%`);
        addCell(row, `${format(metrics.mae_vs_paseo_aleatorio, 3)}×`);
      });
      addCell(row, item.drift ? format(item.drift.ks, 4) : "—");
      addCell(row, item.drift ? format(item.drift.p_value, 4) : "—");
      addCell(row, item.drift ? format(item.drift.psi, 4) : "—");
      addCell(row, item.drift ? (item.alerta_drift ? "Sí" : "No") : "—");
      resultsBody.appendChild(row);
    });

    data.drift_features && Object.entries(data.drift_features).forEach(([feature, metrics]) => {
      const row = document.createElement("tr");
      addCell(row, feature);
      addCell(row, format(metrics.ks, 4));
      addCell(row, format(metrics.p_value, 4));
      addCell(row, format(metrics.psi, 4));
      featureBody.appendChild(row);
    });

    chartModels.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.modelo;
      option.textContent = item.modelo;
      modelSelect.appendChild(option);
    });
    modelSelect.onchange = () => showChart(data);
    showChart(data);

    document.getElementById("results-title").textContent = `${data.ticker} · horizonte ${data.horizonte} días`;
    document.getElementById("sample-count").textContent = `${data.periodo} · ${data.n_train} train · ${data.n_test} test`;
    results.hidden = false;
    setStatus("");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    trainButton.disabled = true;
    results.hidden = true;
    setStatus("Entrenando modelos y registrando resultados…");

    try {
      const response = await fetch("/api/regression/train", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: document.getElementById("ticker-input").value.trim(),
          period: document.getElementById("period-select").value,
          horizon: Number(document.getElementById("horizon-input").value),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No se pudo completar el entrenamiento.");
      render(payload);
    } catch (error) {
      setStatus(error.message || "Ocurrió un error al entrenar los modelos.", true);
    } finally {
      trainButton.disabled = false;
    }
  });
})();