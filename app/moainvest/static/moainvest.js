/*
 * MOAINVEST: comportamiento de las páginas de moainvest/templates/moainvest/ (precios en
 * vivo, sparklines, gráfico de velas y menú móvil), sin framework.
 * Cada bloque se activa solo si su página contiene el elemento
 * correspondiente (data-*).
 *
 * Las clases de Tailwind que se ponen o quitan aquí deben escribirse enteras:
 * Tailwind lee este fichero al compilar moainvest/static/moainvest.css.
 */
(function () {
  "use strict";

  const QUOTE_POLL_MS = 15000;

  const PILL_TONES = {
    none: "bg-mist text-muted",
    up: "bg-up-soft text-up",
    down: "bg-brand-soft text-brand-deep",
  };
  const TEXT_TONES = { none: "text-muted", up: "text-up", down: "text-brand" };

  // ───────────────────────── Formato ─────────────────────────
  function fmtPrice(value) {
    if (value === null || value === undefined) return "—";
    // "always" para que también se agrupen los precios de 4 cifras (7.722,72).
    return value.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 4, useGrouping: "always" });
  }

  function fmtPercent(value) {
    if (value === null || value === undefined) return "—";
    return (value >= 0 ? "+" : "") + value.toFixed(2) + "%";
  }

  function fmtChange(q) {
    if (q.change === null || q.change_percent === null) return "—";
    const sign = q.change >= 0 ? "+" : "";
    return sign + fmtPrice(q.change) + " (" + sign + q.change_percent.toFixed(2) + "%)";
  }

  function toneOf(value) {
    if (value === null || value === undefined) return "none";
    return value >= 0 ? "up" : "down";
  }

  /** Cambia un grupo de clases por otro (los valores de un mapa de tonos). */
  function setTone(el, tones, key) {
    Object.values(tones).forEach((cls) => el.classList.remove(...cls.split(" ")));
    el.classList.add(...tones[key].split(" "));
  }

  function setText(root, selector, text) {
    const el = root.querySelector(selector);
    if (el) el.textContent = text;
    return el;
  }

  function getJSON(url) {
    return fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
  }

  function poll(load) {
    load();
    return setInterval(load, QUOTE_POLL_MS);
  }

  // ───────────────────────── Animación al hacer scroll ─────────────────────────
  function initReveal() {
    const els = document.querySelectorAll("[data-reveal]:not([data-visible]), [data-scene]:not([data-visible])");
    if (!("IntersectionObserver" in window)) {
      els.forEach((el) => el.setAttribute("data-visible", ""));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.setAttribute("data-visible", "");
            io.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
    );
    els.forEach((el) => io.observe(el));
  }

  // ───────────────────────── Menú móvil ─────────────────────────
  function initMobileNav() {
    const toggle = document.querySelector("[data-menu-toggle]");
    const panel = document.getElementById("menu-movil");
    if (!toggle || !panel) return;

    function setOpen(open) {
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
      toggle.querySelector('[data-menu-icon="open"]').hidden = open;
      toggle.querySelector('[data-menu-icon="close"]').hidden = !open;
      document.body.style.overflow = open ? "hidden" : "";
    }

    toggle.addEventListener("click", () => setOpen(panel.hidden));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !panel.hidden) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  // ───────────────────────── Precios de una watchlist ─────────────────────────
  const PULSE_TONES = { live: "bg-up", off: "bg-muted", error: "bg-brand" };

  /** Pulso del mercado ([data-market-pulse]): estado, cuántos suben/bajan y barra de amplitud. */
  function paintPulse(root, quotes, ok) {
    const pulse = root.querySelector("[data-market-pulse]");
    if (!pulse) return;
    const dot = pulse.querySelector('[data-pulse="dot"]');
    const ping = pulse.querySelector('[data-pulse="ping"]');
    [dot, ping].forEach((el) => el && setTone(el, PULSE_TONES, ok ? "live" : "error"));
    if (ping) ping.hidden = !ok;
    if (!ok) {
      setText(pulse, '[data-pulse="status"]', "Sin conexión");
      return;
    }
    const changes = Object.values(quotes)
      .map((q) => q && q.change_percent)
      .filter((v) => v !== null && v !== undefined);
    const up = changes.filter((v) => v >= 0).length;
    const down = changes.length - up;
    const time = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    setText(pulse, '[data-pulse="status"]', "En vivo · " + time);
    setText(pulse, '[data-pulse="up"]', String(up));
    setText(pulse, '[data-pulse="down"]', String(down));
    const bar = pulse.querySelector('[data-pulse="bar"]');
    if (bar && changes.length) bar.style.width = ((up / changes.length) * 100).toFixed(0) + "%";
  }

  /** Destello verde/rojo en el precio cuando cambia respecto al refresco anterior. */
  function flashTick(el, previous, current) {
    if (!el || previous === undefined || previous === current) return;
    el.classList.remove("tick-up", "tick-down");
    void el.offsetWidth; // reinicia la animación
    el.classList.add(current > previous ? "tick-up" : "tick-down");
  }

  /** Rellena cada [data-quote="TICKER"] con su precio; se refresca cada 15 s. */
  function initWatchlistQuotes() {
    document.querySelectorAll("[data-watchlist-quotes]").forEach((root) => {
      const slug = root.dataset.watchlistQuotes;
      const failed = root.querySelector("[data-quotes-failed]");
      const lastPrice = {};
      poll(() =>
        getJSON("/api/watchlist/" + encodeURIComponent(slug) + "/quotes")
          .then((quotes) => {
            if (failed) failed.hidden = true;
            paintPulse(root, quotes, true);
            root.querySelectorAll("[data-quote]").forEach((card) => {
              const q = quotes[card.dataset.quote];
              if (!q) return;
              flashTick(card.querySelector('[data-field="price"]'), lastPrice[card.dataset.quote], q.price);
              lastPrice[card.dataset.quote] = q.price;
              setText(card, '[data-field="price"]', fmtPrice(q.price));
              setText(card, '[data-field="currency"]', q.currency || "");
              const pill = setText(card, '[data-field="change-pill"]', fmtPercent(q.change_percent));
              if (pill) setTone(pill, PILL_TONES, toneOf(q.change_percent));
              const tone = setText(card, '[data-field="change-tone"]', fmtPercent(q.change_percent));
              if (tone) setTone(tone, TEXT_TONES, toneOf(q.change_percent));
            });
          })
          // Se mantienen en pantalla los últimos valores.
          .catch(() => {
            if (failed) failed.hidden = false;
            paintPulse(root, {}, false);
          }),
      );
    });
  }

  // ───────────────────────── Sparklines ─────────────────────────
  /** Línea de cierres del último mes como SVG plano (sin librería de gráficos). */
  function renderSparkline(box, closes) {
    if (closes.length < 2) {
      box.innerHTML = '<div class="h-16" aria-hidden="true"></div>';
      return;
    }
    const W = 240;
    const H = 64;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const line = closes
      .map((v, i) => (i ? "L" : "M") + ((i / (closes.length - 1)) * W).toFixed(1) + " " + (H - 4 - ((v - min) / span) * (H - 8)).toFixed(1))
      .join(" ");
    const color = closes[closes.length - 1] >= closes[0] ? "var(--color-up)" : "var(--color-brand)";
    const gid = "spark-" + box.dataset.sparkline.replace(/[^a-z0-9]/gi, "");
    box.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" class="h-16 w-full" aria-hidden="true">' +
      '<defs><linearGradient id="' + gid + '" x1="0" x2="0" y1="0" y2="1">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity="0.18"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/>' +
      "</linearGradient></defs>" +
      '<path d="' + line + " L" + W + " " + H + " L0 " + H + ' Z" fill="url(#' + gid + ')"/>' +
      '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="1.75" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>' +
      "</svg>";
  }

  function initSparklines() {
    document.querySelectorAll("[data-sparkline]").forEach((box) => {
      getJSON("/api/candles/" + encodeURIComponent(box.dataset.sparkline) + "?range=1mo&interval=1d")
        .then((candles) => renderSparkline(box, candles.map((c) => c.close)))
        .catch(() => renderSparkline(box, []));
    });
  }

  // ───────────────────────── Gráfica de velas ─────────────────────────
  const UP = "#0f8a5f";
  const DOWN = "#c8102e";
  const RANGE_TONES = { on: "bg-brand text-white", off: "bg-mist text-ink/80 hover:bg-line" };

  function initChartWorkspace() {
    const root = document.querySelector("[data-chart-workspace]");
    if (!root || !window.LightweightCharts) return;
    const ticker = root.dataset.ticker;
    const status = root.querySelector("[data-chart-status]");
    const LC = window.LightweightCharts;

    const chart = LC.createChart(root.querySelector("[data-chart]"), {
      autoSize: true,
      layout: { background: { type: LC.ColorType.Solid, color: "#ffffff" }, textColor: "#6b6b6b", fontFamily: '"Geist Mono", monospace' },
      grid: { vertLines: { color: "#f3f2ef" }, horzLines: { color: "#f3f2ef" } },
      rightPriceScale: { borderColor: "#e6e4df" },
      timeScale: { borderColor: "#e6e4df", timeVisible: true, secondsVisible: false },
      crosshair: { mode: LC.CrosshairMode.Normal },
    });
    const series = chart.addSeries(LC.CandlestickSeries, { upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN });

    function showStatus(text) {
      status.hidden = !text;
      status.textContent = text || "";
    }

    // Cada carga lleva un número; si llega tarde la respuesta de un rango anterior, se ignora.
    let request = 0;
    function load(btn) {
      const id = ++request;
      showStatus("Cargando datos de Yahoo Finance…");
      getJSON("/api/candles/" + encodeURIComponent(ticker) + "?range=" + btn.dataset.range + "&interval=" + btn.dataset.interval)
        .then((candles) => {
          if (id !== request) return;
          series.setData(candles);
          chart.timeScale().fitContent();
          showStatus(candles.length ? "" : "No hay datos para este rango.");
        })
        .catch(() => id === request && showStatus("No pudimos cargar el gráfico. Inténtalo de nuevo."));
    }

    const buttons = root.querySelectorAll("[data-range]");
    buttons.forEach((btn) =>
      btn.addEventListener("click", () => {
        buttons.forEach((b) => {
          const on = b === btn;
          b.setAttribute("aria-pressed", String(on));
          setTone(b, RANGE_TONES, on ? "on" : "off");
        });
        load(btn);
      }),
    );
    load(root.querySelector('[data-range][aria-pressed="true"]') || buttons[0]);

    // Precio de la cabecera, con su propio sondeo.
    poll(() =>
      getJSON("/api/quote/" + encodeURIComponent(ticker))
        .then((q) => {
          setText(root, '[data-header="price"]', fmtPrice(q.price));
          setText(root, '[data-header="currency"]', q.currency || "");
          const pill = setText(root, '[data-header="change-pill"]', fmtChange(q));
          setTone(pill, PILL_TONES, toneOf(q.change));
        })
        .catch(() => {}),
    );
  }

  initReveal();
  initMobileNav();
  initWatchlistQuotes();
  initSparklines();
  initChartWorkspace();
})();
