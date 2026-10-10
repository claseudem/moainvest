/**
 * "Mi universo de acciones": precios en vivo (/api/quote/<ticker>), filtro por
 * sector, búsqueda y ordenación de la tabla. Todo en el cliente.
 */
(function () {
  "use strict";

  const root = document.getElementById("universo");
  if (!root) return; // esta página no está montada

  const tbody = root.querySelector("#universo-table tbody");
  const rows = Array.from(tbody.rows);
  const search = document.getElementById("universo-search");
  const chips = Array.from(root.querySelectorAll("#universo-sectors [data-sector]"));
  const emptyEl = document.getElementById("universo-empty");
  const quoteUrl = root.dataset.quoteUrl;
  const MAX_PARALLEL = 8;

  let sector = "";

  // --- Filtros -------------------------------------------------------------
  function applyFilters() {
    const q = search.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const show = (!sector || row.dataset.sector === sector) && (!q || row.dataset.search.includes(q));
      row.hidden = !show;
      if (show) visible += 1;
    });
    emptyEl.hidden = visible > 0;
  }

  chips.forEach((chip) =>
    chip.addEventListener("click", () => {
      sector = chip.dataset.sector;
      chips.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
      applyFilters();
    })
  );
  search.addEventListener("input", applyFilters);

  // --- Ordenación ----------------------------------------------------------
  let sortKey = null;
  let sortDir = 1;

  function sortValue(row, key, type) {
    const raw = key === "ticker" ? row.dataset.ticker : row.dataset[key];
    if (type === "text") return (raw || "").toLowerCase();
    return raw === undefined || raw === "" ? null : Number(raw);
  }

  root.querySelectorAll("[data-sort]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const { sort: key, type } = btn.dataset;
      sortDir = sortKey === key ? -sortDir : type === "num" ? -1 : 1;
      sortKey = key;
      root.querySelectorAll("th[aria-sort]").forEach((th) => th.removeAttribute("aria-sort"));
      btn.parentElement.setAttribute("aria-sort", sortDir > 0 ? "ascending" : "descending");
      const sorted = rows.slice().sort((a, b) => {
        const va = sortValue(a, key, type);
        const vb = sortValue(b, key, type);
        if (va === null) return vb === null ? 0 : 1; // sin dato, siempre al final
        if (vb === null) return -1;
        return (va < vb ? -1 : va > vb ? 1 : 0) * sortDir;
      });
      sorted.forEach((row) => tbody.appendChild(row));
    })
  );

  // --- Precios en vivo -----------------------------------------------------
  const fmtPrice = (v) => v.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function paint(row, quote) {
    const priceEl = row.querySelector('[data-field="price"]');
    const changeEl = row.querySelector('[data-field="change"]');
    if (!quote || quote.price == null) {
      priceEl.textContent = "—";
      changeEl.textContent = "Sin datos";
      changeEl.dataset.tone = "none";
      return;
    }
    priceEl.textContent = fmtPrice(quote.price);
    row.dataset.price = quote.price;
    if (quote.change_percent == null) {
      changeEl.textContent = "—";
      changeEl.dataset.tone = "none";
      return;
    }
    const pct = quote.change_percent;
    changeEl.textContent = (pct >= 0 ? "+" : "") + pct.toFixed(2) + " %";
    changeEl.dataset.tone = pct > 0 ? "up" : pct < 0 ? "down" : "none";
    row.dataset.change = pct;
  }

  async function loadQuote(row) {
    try {
      const res = await fetch(quoteUrl.replace("__T__", encodeURIComponent(row.dataset.ticker)));
      paint(row, res.ok ? await res.json() : null);
    } catch (_err) {
      paint(row, null);
    }
  }

  async function loadAll() {
    const queue = rows.slice();
    const worker = async () => {
      while (queue.length) await loadQuote(queue.shift());
    };
    await Promise.all(Array.from({ length: MAX_PARALLEL }, worker));
  }

  loadAll();
})();
