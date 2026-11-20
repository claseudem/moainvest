/**
 * Vista "Análisis de Varianza": pide el histórico de un ticker a la API
 * (la misma que usa el gráfico), lo muestra en tabla y permite exportarlo
 * a CSV.
 */
(function () {
  "use strict";

  const form = document.getElementById("varianza-form");
  if (!form) return; // esta página no está montada

  const tickerInput = document.getElementById("ticker-input");
  const rangeSelect = document.getElementById("range-select");
  const fetchBtn = document.getElementById("fetch-btn");
  const statusEl = document.getElementById("varianza-status");
  const resultEl = document.getElementById("varianza-result");
  const tableBody = document.getElementById("varianza-table-body");
  const summaryEl = document.getElementById("result-summary");
  const downloadBtn = document.getElementById("download-csv-btn");

  let currentTicker = "";
  let currentRows = [];

  function setStatus(message, isError) {
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("is-error", Boolean(isError));
  }

  function fmtNumber(value) {
    return Number(value).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }

  function fmtDate(unixSeconds) {
    return new Date(unixSeconds * 1000).toLocaleDateString("es-ES", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  }

  function renderTable(rows) {
    const fragment = document.createDocumentFragment();
    // Más reciente primero.
    [...rows].reverse().forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${fmtDate(row.time)}</td>
        <td>${fmtNumber(row.open)}</td>
        <td>${fmtNumber(row.high)}</td>
        <td>${fmtNumber(row.low)}</td>
        <td>${fmtNumber(row.close)}</td>
        <td>${row.volume.toLocaleString("es-ES")}</td>
      `;
      fragment.appendChild(tr);
    });
    tableBody.replaceChildren(fragment);
  }

  function toCsv(rows) {
    const header = "Fecha,Apertura,Maximo,Minimo,Cierre,Volumen";
    const lines = rows.map((row) => [fmtDate(row.time), row.open, row.high, row.low, row.close, row.volume].join(","));
    return [header, ...lines].join("\n");
  }

  function triggerDownload(filename, content) {
    const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const ticker = tickerInput.value.trim().toUpperCase();
    if (!ticker) return;

    fetchBtn.disabled = true;
    resultEl.hidden = true;
    setStatus(`Descargando ${ticker}…`);

    fetch(`/api/candles/${encodeURIComponent(ticker)}?range=${rangeSelect.value}&interval=1d`)
      .then((res) => {
        if (!res.ok) throw new Error("api-error");
        return res.json();
      })
      .then((rows) => {
        if (!Array.isArray(rows) || rows.length === 0) {
          setStatus(`No se encontraron datos para "${ticker}". Verifica el ticker.`, true);
          return;
        }
        currentTicker = ticker;
        currentRows = rows;
        renderTable(rows);
        summaryEl.textContent = `${ticker} · ${rows.length} registros`;
        resultEl.hidden = false;
        setStatus("");
      })
      .catch(() => {
        setStatus(`Ocurrió un error al descargar "${ticker}". Verifica el ticker e inténtalo de nuevo.`, true);
      })
      .finally(() => {
        fetchBtn.disabled = false;
      });
  });

  downloadBtn.addEventListener("click", () => {
    if (!currentRows.length) return;
    triggerDownload(`${currentTicker}_precios.csv`, toCsv(currentRows));
  });

  // -----------------------------------------------------------------
  // Histograma de volatilidad mensual (imagen generada con seaborn)
  // -----------------------------------------------------------------
  const volatilityForm = document.getElementById("volatility-form");
  const tickersInput = document.getElementById("tickers-input");
  const periodSelect = document.getElementById("volatility-period-select");
  const volatilityBtn = document.getElementById("volatility-btn");
  const volatilityStatus = document.getElementById("volatility-status");
  const chartWrap = document.getElementById("volatility-chart-wrap");
  const chartImg = document.getElementById("volatility-chart-img");
  let lastChartObjectUrl = null;

  function setVolatilityStatus(message, isError) {
    volatilityStatus.hidden = !message;
    volatilityStatus.textContent = message || "";
    volatilityStatus.classList.toggle("is-error", Boolean(isError));
  }

  // --- Campo de tickers con chips ----------------------------------
  // Cada ticker escrito (Intro, coma o espacio) se convierte en un chip; lo
  // que quede a medio escribir se añade al enviar el formulario.
  const chipsField = document.getElementById("tickers-field");
  const chipsList = document.getElementById("tickers-chips");
  const suggestBtns = document.querySelectorAll("#tickers-suggest [data-ticker]");
  const maxTickers = Number(volatilityForm.dataset.maxTickers) || 6;
  const tickers = [];

  function renderChips() {
    const fragment = document.createDocumentFragment();
    tickers.forEach((ticker) => {
      const li = document.createElement("li");
      li.className = "varianza-chip";
      li.textContent = ticker;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "varianza-chip__remove";
      remove.setAttribute("aria-label", `Quitar ${ticker}`);
      remove.textContent = "✕";
      remove.addEventListener("click", () => removeTicker(ticker));
      li.appendChild(remove);
      fragment.appendChild(li);
    });
    chipsList.replaceChildren(fragment);
    suggestBtns.forEach((btn) => {
      btn.disabled = tickers.includes(btn.dataset.ticker) || tickers.length >= maxTickers;
    });
    tickersInput.placeholder = tickers.length ? "Añadir otro…" : "Tickers, p. ej. AAPL, MSFT, GOOG";
  }

  function addTickers(text) {
    let added = false;
    text
      .split(/[\s,;]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean)
      .forEach((ticker) => {
        if (tickers.includes(ticker)) return;
        if (tickers.length >= maxTickers) {
          setVolatilityStatus(`Máximo ${maxTickers} tickers a la vez.`, true);
          return;
        }
        tickers.push(ticker);
        added = true;
      });
    if (added) setVolatilityStatus("");
    renderChips();
  }

  function removeTicker(ticker) {
    const index = tickers.indexOf(ticker);
    if (index >= 0) tickers.splice(index, 1);
    renderChips();
    tickersInput.focus();
  }

  tickersInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === "," || event.key === " ") {
      if (!tickersInput.value.trim()) {
        if (event.key !== "Enter") event.preventDefault();
        return; // Intro con el campo vacío envía el formulario
      }
      event.preventDefault();
      addTickers(tickersInput.value);
      tickersInput.value = "";
    } else if (event.key === "Backspace" && !tickersInput.value && tickers.length) {
      removeTicker(tickers[tickers.length - 1]);
    }
  });

  // Pegar "AAPL, MSFT" o salir del campo también crea los chips.
  tickersInput.addEventListener("paste", (event) => {
    event.preventDefault();
    addTickers(event.clipboardData.getData("text"));
  });
  tickersInput.addEventListener("blur", () => {
    if (!tickersInput.value.trim()) return;
    addTickers(tickersInput.value);
    tickersInput.value = "";
  });

  chipsField.addEventListener("click", (event) => {
    if (event.target === chipsField || event.target === chipsList) tickersInput.focus();
  });

  suggestBtns.forEach((btn) => {
    btn.addEventListener("click", () => addTickers(btn.dataset.ticker));
  });

  volatilityForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (tickersInput.value.trim()) {
      addTickers(tickersInput.value);
      tickersInput.value = "";
    }
    if (!tickers.length) {
      setVolatilityStatus("Añade al menos un ticker.", true);
      tickersInput.focus();
      return;
    }

    volatilityBtn.disabled = true;
    chartWrap.hidden = true;
    setVolatilityStatus("Calculando volatilidad mensual…");

    const url = `/api/volatility-chart?tickers=${encodeURIComponent(tickers.join(","))}&period=${periodSelect.value}`;

    fetch(url)
      .then(async (res) => {
        if (!res.ok) {
          const payload = await res.json().catch(() => ({}));
          throw new Error(payload.error || "Error al generar el histograma");
        }
        return res.blob();
      })
      .then((blob) => {
        if (lastChartObjectUrl) URL.revokeObjectURL(lastChartObjectUrl);
        lastChartObjectUrl = URL.createObjectURL(blob);
        chartImg.src = lastChartObjectUrl;
        chartWrap.hidden = false;
        setVolatilityStatus("");
      })
      .catch((err) => {
        setVolatilityStatus(err.message || "Ocurrió un error al generar el histograma.", true);
      })
      .finally(() => {
        volatilityBtn.disabled = false;
      });
  });

  // -----------------------------------------------------------------
  // Deep links (?ticker= / ?tickers=): el servidor rellena los campos y
  // aquí se lanza el análisis sin que el usuario tenga que pulsar nada.
  // -----------------------------------------------------------------
  if (form.hasAttribute("data-autorun") && tickerInput.value.trim()) form.requestSubmit();
  if (volatilityForm.dataset.initialTickers) {
    addTickers(volatilityForm.dataset.initialTickers);
    volatilityForm.requestSubmit();
  }
})();
