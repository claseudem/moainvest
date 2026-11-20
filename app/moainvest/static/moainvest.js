/*
 * MOAINVEST: comportamiento de las páginas de moainvest/templates/moainvest/ (precios en
 * vivo, sparklines, gráfico de velas, informe y menú móvil), sin framework.
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
    return (value >= 0 ? "+" : "") + value.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
  }

  function fmtChange(q) {
    if (q.change === null || q.change_percent === null) return "—";
    const sign = q.change >= 0 ? "+" : "";
    return sign + fmtPrice(q.change) + " (" + fmtPercent(q.change_percent) + ")";
  }

  function fmtSigned(value) {
    if (value === null || value === undefined) return "—";
    return (value >= 0 ? "+" : "") + fmtPrice(value);
  }

  function fmtTime(date) {
    return date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function fmtDay(unixSeconds) {
    return new Date(unixSeconds * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
  }

  function escapeAttr(text) {
    return String(text).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
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

  /** Destello breve de un precio que cambia entre dos sondeos (CSS [data-flash]). */
  function flash(el, direction) {
    el.removeAttribute("data-flash");
    void el.offsetWidth; // reinicia la animación aunque se repita la dirección
    el.setAttribute("data-flash", direction);
  }

  function getJSON(url) {
    return fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
  }

  function poll(load) {
    load();
    // Con la pestaña oculta no se pide nada; al volver a ella se actualiza al momento.
    document.addEventListener("visibilitychange", () => !document.hidden && load());
    return setInterval(() => !document.hidden && load(), QUOTE_POLL_MS);
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
  // Estado de la conexión del Resumen: punto de color y texto de [data-quotes-status].
  const DOT_TONES = { loading: "bg-line", ok: "bg-up", error: "bg-brand" };
  const STATUS_TEXT = {
    loading: "Conectando con Yahoo Finance…",
    ok: "Precios actualizados",
    error: "Sin conexión · últimos valores",
  };

  /**
   * Rellena cada [data-quote="TICKER"] con su precio; se refresca cada 15 s.
   * Campos opcionales de cada tarjeta: price, currency, change-pill, change-tone
   * y change (variación absoluta frente al cierre anterior).
   */
  function initWatchlistQuotes() {
    document.querySelectorAll("[data-watchlist-quotes]").forEach((root) => {
      const slug = root.dataset.watchlistQuotes;
      const failed = root.querySelector("[data-quotes-failed]");
      const statusEl = root.querySelector("[data-quotes-status]");
      const dots = root.querySelectorAll("[data-quotes-dot]");
      const updated = root.querySelector("[data-quotes-updated]");
      let state = "loading";

      function setState(next) {
        dots.forEach((dot) => setTone(dot, DOT_TONES, next));
        // El CSS atenúa la cinta mientras no hay conexión ([data-quotes-state="error"]).
        root.setAttribute("data-quotes-state", next);
        // El texto es una región role="status": solo cambia con el estado, no en cada sondeo.
        if (statusEl && next !== state) statusEl.textContent = STATUS_TEXT[next];
        state = next;
        root.querySelectorAll("[data-quotes-list]").forEach((list) => list.setAttribute("aria-busy", "false"));
      }

      function fillCard(card, q) {
        const hasPrice = q.price !== null && q.price !== undefined;
        const previous = card.dataset.price;
        card.setAttribute("data-loaded", "");
        card.setAttribute("data-price", hasPrice ? String(q.price) : "");
        const price = setText(card, '[data-field="price"]', fmtPrice(q.price));
        // Destello breve del precio cuando cambia entre dos sondeos (no en la primera carga).
        if (price && hasPrice && previous && Number(previous) !== q.price) flash(price, q.price > Number(previous) ? "up" : "down");
        setText(card, '[data-field="currency"]', hasPrice ? q.currency || "" : "");
        const pill = setText(card, '[data-field="change-pill"]', fmtPercent(q.change_percent));
        if (pill) setTone(pill, PILL_TONES, toneOf(q.change_percent));
        const tone = setText(card, '[data-field="change-tone"]', fmtPercent(q.change_percent));
        if (tone) setTone(tone, TEXT_TONES, toneOf(q.change_percent));
        let change = "Variación no disponible";
        if (!hasPrice) change = "Sin datos en Yahoo Finance";
        else if (q.change !== null && q.change !== undefined) change = fmtSigned(q.change) + " vs. cierre anterior";
        setText(card, '[data-field="change"]', change);
      }

      /** Tarjetas que nunca recibieron precio: se quita el esqueleto de carga. */
      function markUnavailable() {
        root.querySelectorAll("[data-quote]:not([data-loaded])").forEach((card) => {
          setText(card, '[data-field="price"]', "—");
          setText(card, '[data-field="change"]', "Precio no disponible");
        });
      }

      poll(() =>
        getJSON("/api/watchlist/" + encodeURIComponent(slug) + "/quotes")
          .then((quotes) => {
            if (failed) failed.hidden = true;
            root.querySelectorAll("[data-quote]").forEach((card) => {
              const q = quotes[card.dataset.quote];
              if (q) fillCard(card, q);
            });
            markUnavailable();
            const at = new Date();
            if (updated) updated.textContent = "· " + fmtTime(at);
            setState("ok");
            root.dispatchEvent(new CustomEvent("moai:quotes", { detail: { quotes: quotes, at: at } }));
          })
          // Se mantienen en pantalla los últimos valores.
          .catch(() => {
            if (failed) failed.hidden = false;
            markUnavailable();
            setState("error");
            root.dispatchEvent(new CustomEvent("moai:quotes-error"));
          }),
      );
    });
  }

  // ───────────────────────── Sparklines ─────────────────────────
  // Una sola petición por ticker aunque aparezca en varias sparklines (hero y tarjeta).
  const monthCandles = {};
  function getMonthCandles(ticker) {
    if (!monthCandles[ticker]) {
      monthCandles[ticker] = getJSON("/api/candles/" + encodeURIComponent(ticker) + "?range=1mo&interval=1d").catch((err) => {
        delete monthCandles[ticker];
        throw err;
      });
    }
    return monthCandles[ticker];
  }

  let sparkSeq = 0;

  /** Mínimo, máximo, variación y fechas del mes en el [data-spark-scope] que contiene la sparkline. */
  function fillSparkStats(scope, points) {
    if (!scope) return;
    const closes = points.map((c) => c.close);
    const has = closes.length >= 2;
    const first = closes[0];
    const last = closes[closes.length - 1];
    const pct = has && first ? ((last - first) / first) * 100 : null;
    setText(scope, '[data-spark-stat="min"]', has ? fmtPrice(Math.min(...closes)) : "—");
    setText(scope, '[data-spark-stat="max"]', has ? fmtPrice(Math.max(...closes)) : "—");
    const change = setText(scope, '[data-spark-stat="change"]', fmtPercent(pct));
    if (change) setTone(change, TEXT_TONES, toneOf(pct));
    setText(scope, '[data-spark-stat="start"]', has ? fmtDay(points[0].time) : "");
    setText(scope, '[data-spark-stat="end"]', has ? fmtDay(points[points.length - 1].time) : "");
  }

  /**
   * Línea de cierres del último mes como SVG plano (sin librería de gráficos),
   * con la línea discontinua del primer cierre como referencia. El alto sale de
   * data-sparkline-height (64 px por defecto) y, con data-sparkline-label, el
   * SVG lleva una descripción accesible en vez de ser decorativo.
   */
  function renderSparkline(box, candles) {
    const points = candles.filter((c) => typeof c.close === "number" && isFinite(c.close));
    const height = Number(box.dataset.sparklineHeight) || 64;
    fillSparkStats(box.closest("[data-spark-scope]"), points);
    if (points.length < 2) {
      box.innerHTML =
        '<div class="grid place-items-center rounded-lg border border-dashed border-line text-xs text-muted" style="height:' +
        height + 'px">Sin histórico disponible</div>';
      return;
    }
    const closes = points.map((c) => c.close);
    const W = 240;
    const H = 64;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const y = (v) => (H - 4 - ((v - min) / span) * (H - 8)).toFixed(1);
    const line = closes.map((v, i) => (i ? "L" : "M") + ((i / (closes.length - 1)) * W).toFixed(1) + " " + y(v)).join(" ");
    const first = closes[0];
    const last = closes[closes.length - 1];
    const color = last >= first ? "var(--color-up)" : "var(--color-brand)";
    const gid = "spark-" + ++sparkSeq;
    const label = box.dataset.sparklineLabel;
    const a11y = label
      ? 'role="img" aria-label="' + escapeAttr(label + ": cierres diarios del último mes, de " + fmtPrice(first) + " a " + fmtPrice(last)) + '"'
      : 'aria-hidden="true"';
    // La línea y su relleno se descubren de izquierda a derecha (.spark-reveal, en el
    // CSS) con un recorte: los datos y la forma no cambian, solo cómo aparecen.
    box.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" class="block w-full" style="height:' + height + 'px" ' + a11y + ">" +
      '<defs><linearGradient id="' + gid + '" x1="0" x2="0" y1="0" y2="1">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity="0.18"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/>' +
      "</linearGradient>" +
      '<clipPath id="' + gid + '-clip"><rect class="spark-reveal" width="' + W + '" height="' + H + '"/></clipPath></defs>' +
      '<line x1="0" x2="' + W + '" y1="' + y(first) + '" y2="' + y(first) + '" stroke="var(--color-muted)" stroke-opacity="0.45" stroke-width="1" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>' +
      '<g clip-path="url(#' + gid + '-clip)">' +
      '<path d="' + line + " L" + W + " " + H + " L0 " + H + ' Z" fill="url(#' + gid + ')"/>' +
      '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="1.75" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>' +
      "</g></svg>";
  }

  function initSparklines() {
    document.querySelectorAll("[data-sparkline]").forEach((box) => {
      getMonthCandles(box.dataset.sparkline)
        .then((candles) => renderSparkline(box, Array.isArray(candles) ? candles : []))
        .catch(() => renderSparkline(box, []));
    });
  }

  // ───────────────────────── Cinta de cotizaciones ─────────────────────────
  /** Botón de pausa de la cinta (WCAG 2.2.2): aria-pressed indica si está pausada. */
  function initTape() {
    document.querySelectorAll("[data-tape]").forEach((tape) => {
      const toggle = tape.querySelector("[data-tape-toggle]");
      if (!toggle) return;
      toggle.addEventListener("click", () => {
        const paused = toggle.getAttribute("aria-pressed") !== "true";
        toggle.setAttribute("aria-pressed", String(paused));
        tape.toggleAttribute("data-paused", paused);
        toggle.querySelector('[data-tape-icon="pause"]').hidden = paused;
        toggle.querySelector('[data-tape-icon="play"]').hidden = !paused;
      });
    });
  }

  // ───────────────────────── Mapa de calor ─────────────────────────
  // Todos los bloques miden lo mismo; el color codifica el signo y tres niveles
  // de |variación| (< 0,5 %, < 2 %, ≥ 2 %), como explica la leyenda.
  const HEAT_TONES = {
    none: "bg-mist text-ink border-line",
    up1: "bg-up-soft text-ink border-up/25",
    up2: "bg-up/25 text-ink border-up/30",
    up3: "bg-up text-white border-up",
    down1: "bg-brand-soft text-ink border-brand/25",
    down2: "bg-brand/25 text-ink border-brand/30",
    down3: "bg-brand text-white border-brand",
  };

  function heatLevel(pct) {
    if (pct === null || pct === undefined || !isFinite(pct)) return "none";
    const size = Math.abs(pct);
    return (pct >= 0 ? "up" : "down") + (size < 0.5 ? 1 : size < 2 ? 2 : 3);
  }

  function paintHeatmap(root, quotes) {
    root.querySelectorAll("[data-heat]").forEach((tile) => {
      const q = quotes[tile.dataset.heat];
      const pct = q && q.price !== null && q.price !== undefined ? q.change_percent : null;
      setText(tile, "[data-heat-value]", pct === null || pct === undefined ? "Sin datos" : fmtPercent(pct));
      const level = heatLevel(pct);
      // Solo se cambia el color si cambia el nivel: nada de parpadeos en cada sondeo.
      if (tile.dataset.level !== level) {
        setTone(tile, HEAT_TONES, level);
        tile.dataset.level = level;
      }
    });
  }

  // ───────────────────────── Ventana de mercado + constelación ─────────────────────────
  /**
   * Un único activo seleccionado, compartido por la constelación (radiogroup),
   * el mapa de calor, las tarjetas y la ventana. Precio y variación salen del
   * sondeo común (evento moai:quotes); el gráfico, de /api/candles con la
   * misma caché que las sparklines. Cada carga lleva un número: si el usuario
   * cambia de activo antes de que llegue la respuesta, la antigua se descarta.
   */
  function initMarketWindow() {
    const win = document.querySelector("[data-market-window]");
    const root = win && win.closest("[data-watchlist-quotes]");
    if (!win || !root) return;
    const radios = Array.from(win.querySelectorAll("[data-select]"));
    if (!radios.length) return;
    const tiles = Array.from(root.querySelectorAll("[data-heat]"));
    const cards = Array.from(root.querySelectorAll("[data-card]"));
    const chartBox = win.querySelector("[data-window-chart]");
    const selLink = root.querySelector("[data-selected-link]");
    const selName = root.querySelector("[data-selected-name]");
    const field = (key) => win.querySelector('[data-window="' + key + '"]');
    const meta = (ticker) => radios.find((r) => r.dataset.select === ticker);

    let selected = (radios.find((r) => r.getAttribute("aria-checked") === "true") || radios[0]).dataset.select;
    let quotes = null;
    let lastAt = null;
    let failed = false;
    let seq = 0;

    function paintQuote(flashChange) {
      const ageEl = field("age");
      if (ageEl) ageEl.textContent = lastAt ? (failed ? "Datos de las " : "Actualizado ") + fmtTime(lastAt) : failed ? "Sin conexión" : "";
      if (!quotes) {
        if (failed) {
          setText(win, '[data-window="price"]', "—");
          setText(win, '[data-window="change"]', "No pudimos cargar el precio. Se reintentará en unos segundos.");
        }
        return;
      }
      const q = quotes[selected];
      const hasPrice = !!q && q.price !== null && q.price !== undefined;
      const priceEl = setText(win, '[data-window="price"]', hasPrice ? fmtPrice(q.price) : "—");
      if (flashChange && priceEl && hasPrice && flashChange !== q.price) flash(priceEl, q.price > flashChange ? "up" : "down");
      setText(win, '[data-window="currency"]', hasPrice ? q.currency || "" : "");
      const pct = hasPrice ? q.change_percent : null;
      const pill = setText(win, '[data-window="pill"]', fmtPercent(pct));
      if (pill) setTone(pill, PILL_TONES, toneOf(pct));
      let change = "Sin datos en Yahoo Finance";
      if (hasPrice) change = q.change === null || q.change === undefined ? "Variación no disponible" : fmtSigned(q.change) + " vs. cierre anterior";
      setText(win, '[data-window="change"]', change);
    }

    function loadChart() {
      const id = ++seq;
      chartBox.setAttribute("data-loading", "");
      getMonthCandles(selected)
        .then((candles) => id === seq && renderSparkline(chartBox, Array.isArray(candles) ? candles : []))
        .catch(() => id === seq && renderSparkline(chartBox, []))
        .finally(() => id === seq && chartBox.removeAttribute("data-loading"));
    }

    function select(ticker, announce) {
      const m = meta(ticker);
      if (!m) return;
      const changed = ticker !== selected;
      selected = ticker;
      radios.forEach((r) => {
        const on = r === m;
        r.setAttribute("aria-checked", String(on));
        r.tabIndex = on ? 0 : -1;
      });
      tiles.forEach((t) => t.setAttribute("aria-pressed", String(t.dataset.heat === ticker)));
      cards.forEach((c) => c.toggleAttribute("data-selected", c.dataset.quote === ticker));
      setText(win, '[data-window="name"]', m.dataset.name);
      setText(win, '[data-window="kind"]', m.dataset.kind);
      setText(win, '[data-window="ticker"]', ticker);
      field("link").href = m.dataset.href;
      if (selLink) selLink.href = m.dataset.href;
      if (selName) selName.textContent = m.dataset.name;
      chartBox.dataset.sparklineLabel = m.dataset.name;
      paintQuote();
      if (changed || !chartBox.querySelector("svg")) loadChart();
      if (announce) {
        const q = quotes && quotes[ticker];
        const price = q && q.price !== null && q.price !== undefined ? ": " + fmtPrice(q.price) + " " + (q.currency || "") + ", " + fmtPercent(q.change_percent) : "";
        setText(win, '[data-window="announce"]', m.dataset.name + " en la ventana de mercado" + price);
      }
    }

    radios.forEach((r, i) => {
      r.addEventListener("click", () => select(r.dataset.select, true));
      // Patrón de radiogroup: las flechas mueven foco y selección; Inicio/Fin van a los extremos.
      r.addEventListener("keydown", (e) => {
        const moves = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
        let next = null;
        if (e.key in moves) next = (i + moves[e.key] + radios.length) % radios.length;
        else if (e.key === "Home") next = 0;
        else if (e.key === "End") next = radios.length - 1;
        if (next === null) return;
        e.preventDefault();
        radios[next].focus();
        select(radios[next].dataset.select, true);
      });
    });
    tiles.forEach((t) => t.addEventListener("click", () => select(t.dataset.heat, true)));

    root.addEventListener("moai:quotes", (e) => {
      const before = quotes && quotes[selected] ? quotes[selected].price : null;
      quotes = e.detail.quotes;
      lastAt = e.detail.at;
      failed = false;
      paintQuote(before);
      paintHeatmap(root, quotes);
    });
    root.addEventListener("moai:quotes-error", () => {
      failed = true;
      paintQuote();
    });

    select(selected, false);
  }

  // ───────────────────────── MOAI SIGNAL (apertura) ─────────────────────────
  /**
   * La apertura la decide el script del <head> (html.intro-play) y la anima el
   * CSS, que también la cierra solo. Aquí solo se permite omitirla (botón,
   * Escape, cualquier tecla, clic, rueda o toque) y se limpia al terminar.
   */
  function initIntro() {
    const html = document.documentElement;
    const intro = document.querySelector("[data-intro]");
    if (!intro || !html.classList.contains("intro-play")) return;
    let done = false;
    const events = ["keydown", "wheel", "touchstart"];

    function finish() {
      html.classList.remove("intro-play", "intro-skip");
      if (intro.contains(document.activeElement)) document.activeElement.blur();
    }
    function skip() {
      if (done) return;
      done = true;
      events.forEach((type) => window.removeEventListener(type, skip));
      html.classList.add("intro-skip");
      setTimeout(finish, 320);
    }

    intro.querySelector("[data-intro-skip]").addEventListener("click", skip);
    intro.addEventListener("pointerdown", skip);
    events.forEach((type) => window.addEventListener(type, skip, { passive: true }));
    intro.addEventListener("animationend", (e) => {
      if (e.target !== intro || done) return;
      done = true;
      events.forEach((type) => window.removeEventListener(type, skip));
      finish();
    });
  }

  // ───────────────────────── Profundidad (parallax sutil) ─────────────────────────
  /** Capas [data-depth] del hero que siguen al cursor unos píxeles. Solo con ratón,
   *  en escritorio, sin movimiento reducido ni ahorro de datos. */
  function initDepth() {
    const hero = document.querySelector("[data-depth-root]");
    if (!hero || !window.matchMedia) return;
    const capable =
      window.matchMedia("(pointer: fine) and (min-width: 1024px)").matches &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches &&
      !(navigator.connection && navigator.connection.saveData) &&
      (navigator.hardwareConcurrency || 4) > 2;
    if (!capable) return;
    const layers = Array.from(hero.querySelectorAll("[data-depth]"));
    let x = 0;
    let y = 0;
    let frame = 0;
    function apply() {
      frame = 0;
      layers.forEach((layer) => {
        const depth = Number(layer.dataset.depth) || 0;
        layer.style.translate = (x * depth).toFixed(1) + "px " + (y * depth).toFixed(1) + "px";
      });
    }
    function queue() {
      if (!frame) frame = requestAnimationFrame(apply);
    }
    hero.addEventListener("pointermove", (e) => {
      const box = hero.getBoundingClientRect();
      x = (e.clientX - box.left) / box.width - 0.5;
      y = (e.clientY - box.top) / box.height - 0.5;
      queue();
    });
    hero.addEventListener("pointerleave", () => {
      x = 0;
      y = 0;
      queue();
    });
  }

  /** Con la pestaña oculta se pausan las animaciones infinitas (CSS html.tab-hidden). */
  function initTabVisibility() {
    document.addEventListener("visibilitychange", () => document.documentElement.classList.toggle("tab-hidden", document.hidden));
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

  // ───────────────────────── Informe ─────────────────────────
  const OPTION_TONES = { on: "border-ink/30 bg-mist", off: "border-line hover:border-ink/30" };
  const STATUS_TONES = { ok: "bg-mist text-ink", error: "bg-brand-soft text-brand-deep" };

  function initReportBuilder() {
    const root = document.querySelector("[data-report-builder]");
    if (!root) return;
    const checkboxes = Array.from(root.querySelectorAll('input[name="watchlists"]'));
    const statusEl = root.querySelector("[data-status]");
    const frame = root.querySelector("[data-preview-frame]");
    const empty = root.querySelector("[data-preview-empty]");
    const previewBtn = root.querySelector("[data-preview]");
    const form = root.querySelector("[data-send-form]");
    const sendBtn = form.querySelector('button[type="submit"]');
    const email = form.querySelector('input[type="email"]');

    const selected = () => checkboxes.filter((c) => c.checked).map((c) => c.value);

    checkboxes.forEach((c) =>
      c.addEventListener("change", () => setTone(c.closest("[data-watchlist-option]"), OPTION_TONES, c.checked ? "on" : "off")),
    );

    function setStatus(text, error) {
      statusEl.hidden = !text;
      statusEl.textContent = text || "";
      statusEl.setAttribute("role", error ? "alert" : "status");
      if (text) setTone(statusEl, STATUS_TONES, error ? "error" : "ok");
    }

    function setBusy(btn, busy, label) {
      btn.disabled = busy;
      btn.querySelector("[data-label]").textContent = label;
    }

    function requireSelection() {
      if (selected().length) return true;
      setStatus("Selecciona al menos una watchlist.", true);
      return false;
    }

    previewBtn.addEventListener("click", () => {
      if (!requireSelection()) return;
      setStatus("");
      setBusy(previewBtn, true, "Generando informe…");
      frame.hidden = false;
      empty.hidden = true;
      frame.src = root.dataset.previewUrl + "?watchlists=" + encodeURIComponent(selected().join(",")) + "&t=" + Date.now();
    });
    frame.addEventListener("load", () => frame.src && setBusy(previewBtn, false, "Ver informe"));

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!requireSelection()) return;
      const to = email.value.trim();
      setBusy(sendBtn, true, "Enviando…");
      setStatus("Enviando informe a " + to + "…");
      fetch(root.dataset.sendUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to: to, watchlists: selected() }),
      })
        .then((res) =>
          res
            .json()
            .catch(() => ({}))
            .then((data) => {
              if (!res.ok) throw new Error(data.error || "Error " + res.status);
              setStatus("Informe enviado a " + to + ".");
            }),
        )
        .catch((err) => setStatus("No se pudo enviar el informe: " + err.message, true))
        .finally(() => setBusy(sendBtn, false, "Enviar por correo"));
    });
  }

  initIntro();
  initTabVisibility();
  initReveal();
  initMobileNav();
  initTape();
  // La ventana se suscribe antes de que el sondeo emita su primer evento.
  initMarketWindow();
  initWatchlistQuotes();
  initDepth();
  initSparklines();
  initChartWorkspace();
  initReportBuilder();
})();
