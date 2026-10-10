/*
 * Graficador: gráfico de un ticker de Yahoo Finance con lightweight-charts v5
 * (API ``addSeries`` y panes), sin framework.
 *
 * - Pane 0: la serie principal (velas, línea o área, según el selector).
 * - Pane 1: histograma de volumen.
 * - Panes 2…: los indicadores técnicos, que añade graficador-indicators.js a
 *   través de ``window.GraficadorChart`` (definido más abajo).
 * Los datos vienen de /api/candles/<ticker>?range=&interval= (core) y la
 * cabecera de /api/quote/<ticker> y la watchlist del eyebrow de /api/watchlists.
 * Los colores se leen de los tokens de marca de core/static/css/style.css
 * (tema claro MOAINVEST, como el gráfico rojo de moainvest.js); los fallbacks
 * son esos mismos valores por si la hoja no ha cargado.
 */
(function () {
  "use strict";

  const root = document.getElementById("graficador");
  const LC = window.LightweightCharts;
  if (!root || !root.dataset.ticker || !LC) return;

  const ticker = root.dataset.ticker;
  const apiUrl = (template) => template.replace("__T__", encodeURIComponent(ticker));
  const candlesUrl = apiUrl(root.dataset.providerCandlesUrl || root.dataset.candlesUrl);
  const providersUrl = root.dataset.providersUrl;
  const providerSelect = document.getElementById("graficador-provider");
  const sourceEl = document.getElementById("graficador-source");
  const PROVIDER_KEY = "graficador:provider:v1";
  const intervalWrap = document.getElementById("graficador-interval-wrap");
  const intervalSelect = document.getElementById("graficador-interval");
  const INTERVAL_KEY = "graficador:interval:v1";
  // Días que abarca cada botón de rango, para desactivar los que superan la
  // historia máxima de la periodicidad elegida (``max_days`` del proveedor).
  const RANGE_DAYS = { "1d": 1, "5d": 5, "1mo": 31, "3mo": 93, "6mo": 186, "1y": 366, "2y": 731, "5y": 1827, max: Infinity };
  const providersById = new Map();
  let intervalChoices = []; // periodicidades elegibles del proveedor actual
  let chosenInterval = ""; // "" = la del botón de rango
  let providerName = "Yahoo Finance";
  let providerId = "yahoo";
  try {
    providerId = localStorage.getItem(PROVIDER_KEY) || providerId;
  } catch (e) {
    /* sin almacenamiento: se usa el de por defecto */
  }
  const quoteUrl = apiUrl(root.dataset.quoteUrl);

  const overlayEl = document.getElementById("graficador-overlay");
  const statusEl = document.getElementById("graficador-status");
  const legendEl = document.getElementById("graficador-legend");
  const nameEl = document.getElementById("graficador-name");
  const symbolEl = document.getElementById("graficador-symbol");
  const eyebrowEl = document.getElementById("graficador-eyebrow");
  const priceEl = document.getElementById("graficador-price");
  const currencyEl = document.getElementById("graficador-currency");
  const changeEl = document.getElementById("graficador-change");
  const rangeButtons = Array.from(root.querySelectorAll("[data-range]"));
  const typeButtons = Array.from(root.querySelectorAll("[data-series-type]"));

  // ───────────────────────── Tema ─────────────────────────
  const css = getComputedStyle(document.documentElement);
  const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  const THEME = {
    bg: token("--paper", "#ffffff"),
    line: token("--line", "#e6e4df"),
    text: token("--muted", "#6b6b6b"),
    ink: token("--ink", "#171717"),
    brand: token("--brand", "#c8102e"),
    brandSoft: token("--brand-soft", "#fbeef0"),
    up: token("--up", "#0f8a5f"),
    down: token("--down", "#c8102e"),
    font: token("--font-mono", '"Geist Mono", ui-monospace, monospace'),
  };

  function withAlpha(hex, alpha) {
    const n = parseInt(hex.replace("#", ""), 16);
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alpha + ")";
  }

  // ───────────────────────── Formato ─────────────────────────
  const fmtNumber = (value, digits) =>
    value === null || value === undefined
      ? "—"
      : value.toLocaleString("es-ES", { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: "always" });
  const fmtPrice = (value) => fmtNumber(value, Math.abs(value) < 1 ? 4 : 2);

  function fmtVolume(value) {
    if (!value) return "—";
    const units = [[1e9, " B"], [1e6, " M"], [1e3, " K"]];
    for (const [size, suffix] of units) {
      if (value >= size) return fmtNumber(value / size, 2) + suffix;
    }
    return fmtNumber(value, 0);
  }

  let intraday = false;
  let withSeconds = false;
  function fmtTime(time) {
    const options = { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" };
    if (intraday) Object.assign(options, { hour: "2-digit", minute: "2-digit" });
    if (withSeconds) options.second = "2-digit";
    return new Date(time * 1000).toLocaleString("es-ES", options);
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ───────────────────────── Gráfico ─────────────────────────
  const chart = LC.createChart(document.getElementById("graficador-chart"), {
    autoSize: true,
    layout: {
      background: { type: LC.ColorType.Solid, color: THEME.bg },
      textColor: THEME.text,
      // Geist Mono en ejes y etiquetas, como el gráfico rojo: cifras en mono.
      fontFamily: THEME.font,
      fontSize: 11,
      panes: { separatorColor: THEME.line, separatorHoverColor: withAlpha(THEME.brand, 0.12), enableResize: true },
    },
    grid: { vertLines: { color: withAlpha(THEME.line, 0.55) }, horzLines: { color: withAlpha(THEME.line, 0.55) } },
    rightPriceScale: { borderColor: THEME.line },
    timeScale: { borderColor: THEME.line, timeVisible: true, secondsVisible: false },
    crosshair: {
      mode: LC.CrosshairMode.Normal,
      vertLine: { color: withAlpha(THEME.ink, 0.45), labelBackgroundColor: THEME.ink },
      horzLine: { color: withAlpha(THEME.ink, 0.45), labelBackgroundColor: THEME.ink },
    },
    localization: { locale: "es-ES" },
  });

  const SERIES = {
    candles: () =>
      chart.addSeries(
        LC.CandlestickSeries,
        { upColor: THEME.up, downColor: THEME.down, borderVisible: false, wickUpColor: THEME.up, wickDownColor: THEME.down },
        0,
      ),
    line: () => chart.addSeries(LC.LineSeries, { color: THEME.brand, lineWidth: 2 }, 0),
    // Degradado del rojo de marca al brand-soft, casi transparente abajo.
    area: () =>
      chart.addSeries(
        LC.AreaSeries,
        { lineColor: THEME.brand, topColor: withAlpha(THEME.brand, 0.22), bottomColor: withAlpha(THEME.brandSoft, 0.1), lineWidth: 2 },
        0,
      ),
  };

  let seriesType = (typeButtons.find((b) => b.getAttribute("aria-pressed") === "true") || typeButtons[0]).dataset.seriesType;
  let mainSeries = SERIES[seriesType]();
  const volumeSeries = chart.addSeries(
    LC.HistogramSeries,
    { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
    1,
  );
  // El pane de precios ocupa 3/4 de la altura y el de volumen 1/4.
  chart.panes()[0].setStretchFactor(3);
  chart.panes()[1].setStretchFactor(1);

  let candles = [];
  let byTime = new Map();

  function mainData() {
    if (seriesType === "candles") return candles;
    return candles.map((c) => ({ time: c.time, value: c.close }));
  }

  function volumeData() {
    return candles.map((c) => ({
      time: c.time,
      value: c.volume || 0,
      color: withAlpha(c.close >= c.open ? THEME.up : THEME.down, 0.3),
    }));
  }

  function setSeriesType(type) {
    if (type === seriesType || !SERIES[type]) return;
    // Se crea la nueva antes de quitar la anterior para que el pane 0 nunca quede vacío.
    const previous = mainSeries;
    seriesType = type;
    mainSeries = SERIES[type]();
    mainSeries.setData(mainData());
    chart.removeSeries(previous);
    // La nueva serie se crea la última y se dibujaría encima de las medias móviles.
    if (typeof mainSeries.setSeriesOrder === "function") mainSeries.setSeriesOrder(0);
  }

  // ───────────────────────── Leyenda OHLC ─────────────────────────
  function renderLegend(candle) {
    if (!candle) {
      legendEl.innerHTML = "";
      return;
    }
    const tone = candle.close >= candle.open ? "is-up" : "is-down";
    const item = (label, value) => '<span class="' + tone + '">' + label + " <b>" + value + "</b></span>";
    legendEl.innerHTML =
      '<span class="graficador__legend-time">' + escapeHtml(ticker) + " · " + fmtTime(candle.time) + "</span>" +
      item("O", fmtPrice(candle.open)) +
      item("H", fmtPrice(candle.high)) +
      item("L", fmtPrice(candle.low)) +
      item("C", fmtPrice(candle.close)) +
      item("Vol", fmtVolume(candle.volume));
  }

  chart.subscribeCrosshairMove((param) => {
    const candle = param && param.time !== undefined ? byTime.get(param.time) : null;
    renderLegend(candle || candles[candles.length - 1]);
  });

  // ───────────────────────── Estados ─────────────────────────
  // Estado sobre el gráfico (tarjeta blanca): "loading", "error" o "empty".
  function showStatus(text, state) {
    overlayEl.hidden = !text;
    statusEl.textContent = text || "";
    statusEl.classList.toggle("graficador__status--loading", state === "loading");
    statusEl.classList.toggle("graficador__status--error", state === "error");
  }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then((response) =>
      response.json().then((data) => {
        if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
        return data;
      }),
    );
  }

  // Cada carga lleva un número; si llega tarde la respuesta de un rango anterior, se ignora.
  let request = 0;
  let context = null; // {range, interval, candles} de la última carga correcta
  const dataListeners = [];
  function load(button) {
    const id = ++request;
    const interval = chosenInterval || button.dataset.interval;
    intraday = !/^(1d|1wk|1mo)$/.test(interval);
    withSeconds = /s$/.test(interval);
    chart.applyOptions({ timeScale: { secondsVisible: withSeconds } });
    showStatus("Cargando datos de " + providerName + "…", "loading");
    getJSON(candlesUrl + "?provider=" + encodeURIComponent(providerId) + "&range=" + button.dataset.range + "&interval=" + interval)
      .then((data) => {
        if (id !== request) return;
        candles = data;
        byTime = new Map(candles.map((c) => [c.time, c]));
        mainSeries.setData(mainData());
        volumeSeries.setData(volumeData());
        chart.timeScale().fitContent();
        renderLegend(candles[candles.length - 1]);
        context = { range: button.dataset.range, interval, candles };
        dataListeners.forEach((listener) => listener(context));
        showStatus(
          candles.length ? "" : "No hay datos de «" + ticker + "» en " + providerName + " para este rango. Revisa el ticker.",
          "empty",
        );
      })
      // Con error del proveedor se conservan la serie y los indicadores anteriores;
      // el aviso queda sobre el gráfico y se quita al cambiar de rango o proveedor.
      .catch((error) => id === request && showStatus(
        (error && error.message && !/^HTTP /.test(error.message) ? error.message : "No pudimos cargar el gráfico. Inténtalo de nuevo.") +
          " Prueba con otro proveedor o rango.",
        "error",
      ));
  }

  function currentRange() {
    return rangeButtons.find((b) => b.getAttribute("aria-pressed") === "true") || rangeButtons[0];
  }

  // ───────────────────────── Proveedor de precios ─────────────────────────
  function applyProvider(id, name) {
    providerId = id;
    providerName = name;
    if (sourceEl) sourceEl.textContent = "Datos de " + name;
    setupIntervals((providersById.get(id) || {}).intervals || []);
  }

  // ───────────────────────── Periodicidad ─────────────────────────
  // Con proveedores que la admiten (Dukascopy) se puede fijar a mano la
  // periodicidad de las velas (segundos, minutos, horas…); si no, la decide el
  // botón de rango. La elección se recuerda por proveedor.
  function savedIntervals() {
    try {
      return JSON.parse(localStorage.getItem(INTERVAL_KEY)) || {};
    } catch (e) {
      return {};
    }
  }

  function setupIntervals(choices) {
    intervalChoices = choices;
    if (!intervalSelect || !intervalWrap) return;
    intervalWrap.hidden = !choices.length;
    intervalSelect.innerHTML = '<option value="">Periodicidad: auto</option>';
    const groups = new Map();
    choices.forEach((c) => {
      if (!groups.has(c.group)) {
        const optgroup = document.createElement("optgroup");
        optgroup.label = c.group;
        groups.set(c.group, optgroup);
        intervalSelect.appendChild(optgroup);
      }
      const option = document.createElement("option");
      option.value = c.value;
      option.textContent = c.label;
      groups.get(c.group).appendChild(option);
    });
    const saved = savedIntervals()[providerId];
    chosenInterval = choices.some((c) => c.value === saved) ? saved : "";
    intervalSelect.value = chosenInterval;
    updateRanges();
  }

  // Desactiva los rangos más largos que la historia de la periodicidad elegida
  // (p. ej. 1 segundo solo llega a 1 día) y, si el pulsado queda fuera, pasa al
  // más largo permitido.
  function updateRanges() {
    const choice = intervalChoices.find((c) => c.value === chosenInterval);
    const maxDays = choice && choice.max_days ? choice.max_days : Infinity;
    rangeButtons.forEach((b) => {
      const tooLong = RANGE_DAYS[b.dataset.range] > maxDays;
      b.disabled = tooLong;
      b.title = tooLong ? "No disponible con «" + choice.label + "»" : "";
    });
    if (currentRange().disabled) {
      const allowed = rangeButtons.filter((b) => !b.disabled);
      press(rangeButtons, allowed[allowed.length - 1] || rangeButtons[0]);
    }
  }

  if (intervalSelect) {
    intervalSelect.addEventListener("change", () => {
      chosenInterval = intervalSelect.value;
      const saved = savedIntervals();
      saved[providerId] = chosenInterval;
      try {
        localStorage.setItem(INTERVAL_KEY, JSON.stringify(saved));
      } catch (e) {
        /* sin almacenamiento: solo dura esta visita */
      }
      updateRanges();
      load(currentRange());
    });
  }

  function setupProviders(list) {
    if (!providerSelect || !list.length) return;
    providerSelect.innerHTML = "";
    list.forEach((p) => {
      providersById.set(p.id, p);
      const option = document.createElement("option");
      option.value = p.id;
      option.textContent = p.available ? p.name : p.name + " (no disponible)";
      option.dataset.name = p.name;
      option.dataset.reason = p.available ? "" : p.reason || "";
      providerSelect.appendChild(option);
    });
    // Un proveedor guardado que ya no existe o no está disponible vuelve al primero.
    const saved = list.find((p) => p.id === providerId);
    const chosen = saved || list[0];
    providerSelect.value = chosen.id;
    applyProvider(chosen.id, chosen.name);
    describeProvider();
  }

  function describeProvider() {
    const option = providerSelect.selectedOptions[0];
    const hint = document.getElementById("graficador-provider-hint");
    const reason = option ? option.dataset.reason : "";
    providerSelect.title = reason || "Proveedor de precios";
    if (hint) hint.textContent = reason;
  }

  if (providerSelect) {
    providerSelect.addEventListener("change", () => {
      const option = providerSelect.selectedOptions[0];
      applyProvider(option.value, option.dataset.name || option.textContent);
      try {
        localStorage.setItem(PROVIDER_KEY, option.value);
      } catch (e) {
        /* sin almacenamiento: solo dura esta visita */
      }
      describeProvider();
      load(currentRange());
    });
  }

  function press(buttons, active) {
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b === active)));
  }

  rangeButtons.forEach((button) =>
    button.addEventListener("click", () => {
      press(rangeButtons, button);
      load(button);
    }),
  );
  typeButtons.forEach((button) =>
    button.addEventListener("click", () => {
      press(typeButtons, button);
      setSeriesType(button.dataset.seriesType);
    }),
  );

  // Contrato para graficador-indicators.js (se carga después de este fichero).
  window.GraficadorChart = {
    root, chart, LC, ticker, THEME, getJSON, getProvider: () => providerId, withAlpha, fmtNumber, fmtPrice, fmtVolume, escapeHtml,
    getContext: () => context,
    // El listener recibe {range, interval, candles} tras cada carga de velas, y
    // se llama enseguida si ya hay una cargada.
    onData(listener) {
      dataListeners.push(listener);
      if (context) listener(context);
    },
  };

  // Se conoce el catálogo antes de la primera carga para usar el proveedor recordado;
  // si el catálogo falla, se sigue con Yahoo.
  (providersUrl ? getJSON(providersUrl).then((data) => setupProviders(data.providers || [])) : Promise.resolve())
    .catch(() => {})
    .then(() => load(currentRange()));

  // Geist Mono llega de Google Fonts: al cargar, se vuelve a pintar el canvas con ella.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => chart.applyOptions({ layout: { fontFamily: THEME.font } }));
  }

  // ───────────────────────── Cabecera (precio actual) ─────────────────────────
  getJSON(quoteUrl)
    .then((q) => {
      if (q.name && q.name !== ticker) {
        nameEl.textContent = q.name;
        symbolEl.hidden = false;
      }
      if (q.price === null || q.price === undefined) return;
      priceEl.textContent = fmtPrice(q.price);
      currencyEl.textContent = q.currency || "";
      if (q.change === null || q.change === undefined) return;
      const sign = q.change >= 0 ? "+" : "";
      changeEl.dataset.tone = q.change >= 0 ? "up" : "down";
      changeEl.textContent =
        sign + fmtPrice(q.change) + (q.change_percent === null ? "" : " (" + sign + fmtNumber(q.change_percent, 2) + " %)");
    })
    .catch(() => {});

  // ───────────────────────── Eyebrow (watchlist · mercado) ─────────────────────────
  getJSON(root.dataset.watchlistsUrl)
    .then((watchlists) => {
      const list = watchlists.find((w) => w.symbols.some((s) => s.ticker === ticker));
      if (list) eyebrowEl.textContent = list.name + " · " + root.dataset.market;
    })
    .catch(() => {});
})();
