/*
 * MOAINVEST: comportamiento de las páginas de moainvest/templates/moainvest/ y
 * cuentas/templates/cuentas/ (precios en vivo, sparklines, gráficas, guilloché,
 * cinta, carrusel, formularios, informe y menú móvil), sin framework.
 * Cada bloque se activa solo si su página contiene el elemento
 * correspondiente (data-*).
 *
 * Las clases de Tailwind que se ponen o quitan aquí deben escribirse enteras:
 * Tailwind lee este fichero al compilar moainvest/static/moainvest.css.
 */
(function () {
  "use strict";

  const QUOTE_POLL_MS = 15000;
  const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const EASE = (t) => 1 - Math.pow(1 - t, 3); // ease-out, cercano a cubic-bezier(.22,1,.36,1)

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

  /** Llama a fn(el) la primera vez que el elemento entra en pantalla. */
  function onVisible(els, fn, options) {
    els = Array.from(els);
    if (!("IntersectionObserver" in window)) {
      els.forEach(fn);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            io.unobserve(entry.target);
            fn(entry.target);
          }
        }
      },
      options || { rootMargin: "0px 0px -10% 0px", threshold: 0.15 },
    );
    els.forEach((el) => io.observe(el));
  }

  /** Anima un número de `from` a `to` y lo escribe con `format`. */
  function countTo(el, from, to, format, duration) {
    if (REDUCED_MOTION || from === to) {
      el.textContent = format(to);
      return;
    }
    const start = performance.now();
    const dur = duration || 600;
    function frame(now) {
      const t = Math.min(1, (now - start) / dur);
      el.textContent = format(from + (to - from) * EASE(t));
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // ───────────────────────── Animación al hacer scroll ─────────────────────────
  function initReveal() {
    onVisible(document.querySelectorAll("[data-reveal]:not([data-visible])"), (el) => el.setAttribute("data-visible", ""), {
      rootMargin: "0px 0px -12% 0px",
      threshold: 0.12,
    });
  }

  // ───────────────────────── Navbar ─────────────────────────
  /** Se encoge y gana sombra al bajar (CSS: .site-nav[data-scrolled]). */
  function initNavbar() {
    const nav = document.querySelector("[data-site-nav]");
    if (!nav) return;
    let ticking = false;
    function update() {
      nav.toggleAttribute("data-scrolled", window.scrollY > 12);
      ticking = false;
    }
    window.addEventListener(
      "scroll",
      () => {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(update);
        }
      },
      { passive: true },
    );
    update();
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

  // ───────────────────────── Guilloché ─────────────────────────
  /*
   * Patrón tipo billete generado en SVG: una roseta de anillos ondulados
   * entrelazados (dos familias con fase opuesta) que gira muy lento, y bandas
   * de ondas que se desplazan. Cada capa es un <div> que se anima con
   * transform (lo compone la GPU, sin repintar el SVG).
   */
  const SVG_NS = "http://www.w3.org/2000/svg";

  function rosettePaths(rings, base, step, amp, petals, phaseStep) {
    const paths = [];
    const SAMPLES = 360;
    for (let i = 0; i < rings; i++) {
      const r0 = base + i * step;
      const phase = i * phaseStep;
      let d = "";
      for (let k = 0; k <= SAMPLES; k++) {
        const t = (k / SAMPLES) * Math.PI * 2;
        const r = r0 + amp * Math.sin(petals * t + phase);
        d += (k ? "L" : "M") + (500 + r * Math.cos(t)).toFixed(1) + " " + (500 + r * Math.sin(t)).toFixed(1);
      }
      paths.push(d + "Z");
    }
    return paths;
  }

  function wavePaths(lines, width, gap, amp, length, phaseStep) {
    const paths = [];
    for (let j = 0; j < lines; j++) {
      const y0 = 40 + j * gap;
      let d = "";
      for (let x = 0; x <= width; x += 8) {
        const envelope = 0.55 + 0.45 * Math.sin((x / width) * Math.PI);
        const y = y0 + amp * envelope * Math.sin(x / length + j * phaseStep);
        d += (x ? "L" : "M") + x + " " + y.toFixed(1);
      }
      paths.push(d);
    }
    return paths;
  }

  function svgFrom(viewBox, groups, aspect) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", viewBox);
    svg.setAttribute("preserveAspectRatio", aspect || "xMidYMid meet");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    groups.forEach(({ paths, width }) => {
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("stroke-width", width);
      g.innerHTML = paths.map((d) => '<path d="' + d + '"/>').join("");
      svg.appendChild(g);
    });
    return svg;
  }

  // Posición de la roseta y de las ondas por variante.
  const GUILLOCHE_LAYOUT = {
    hero: { size: "min(1150px, 125vw)", x: "right: -22%", y: "50%", waves: "bottom: 0; height: 48%" },
    panel: { size: "max(720px, 120%)", x: "right: -45%", y: "45%", waves: "bottom: 0; height: 55%" },
    band: { size: "min(1100px, 160%)", x: "left: calc(50% - min(1100px, 160%) / 2)", y: "50%", waves: "top: 0; height: 100%" },
  };

  function initGuilloche() {
    document.querySelectorAll("[data-guilloche]").forEach((box) => {
      const layout = GUILLOCHE_LAYOUT[box.dataset.guilloche] || GUILLOCHE_LAYOUT.hero;

      const spin = document.createElement("div");
      spin.className = "guilloche__spin absolute aspect-square";
      spin.style.cssText = "width:" + layout.size + ";" + layout.x + ";top:calc(" + layout.y + " - " + layout.size + " / 2)";
      spin.appendChild(
        svgFrom("0 0 1000 1000", [
          { paths: rosettePaths(26, 150, 12, 16, 18, 0.32), width: 0.9 },
          { paths: rosettePaths(26, 156, 12, 16, 18, Math.PI + 0.32 * 0.5), width: 0.6 },
          { paths: rosettePaths(8, 60, 10, 9, 12, 0.5), width: 0.7 },
        ]),
      );

      const spinRev = document.createElement("div");
      spinRev.className = "guilloche__spin guilloche__spin--rev absolute aspect-square";
      spinRev.style.cssText = spin.style.cssText;
      spinRev.appendChild(svgFrom("0 0 1000 1000", [{ paths: rosettePaths(6, 470, 7, 10, 40, 0.8), width: 0.7 }]));

      const waves = document.createElement("div");
      waves.className = "guilloche__wave absolute inset-x-[-6%]";
      waves.style.cssText += layout.waves;
      waves.appendChild(
        svgFrom(
          "0 0 1600 260",
          [
            { paths: wavePaths(22, 1600, 9, 34, 120, 0.22), width: 0.8 },
            { paths: wavePaths(22, 1600, 9, 34, 120, Math.PI + 0.22), width: 0.5 },
          ],
          "none",
        ),
      );

      box.replaceChildren(waves, spinRev, spin);
    });
  }

  // ───────────────────────── Precios en vivo ─────────────────────────
  /**
   * Rellena cada [data-quote="TICKER"] de los bloques [data-watchlist-quotes]
   * ("slug" o "slug1 slug2 ...") con su precio; se refresca cada 15 s. Aunque
   * varios bloques compartan watchlist, cada slug se pide una sola vez.
   */
  function updatePrice(el, price) {
    if (price === null || price === undefined) {
      el.textContent = "—";
      return;
    }
    const prev = el.dataset.value === undefined ? null : Number(el.dataset.value);
    el.dataset.value = String(price);
    if (prev === null || !el.hasAttribute("data-animate-price")) {
      el.textContent = fmtPrice(price);
      return;
    }
    if (prev === price) return;
    countTo(el, prev, price, fmtPrice, 650);
    if (!REDUCED_MOTION) {
      el.classList.remove("flash-up", "flash-down");
      void el.offsetWidth; // reinicia la animación del destello
      el.classList.add(price > prev ? "flash-up" : "flash-down");
    }
  }

  function paintQuote(card, q) {
    card.querySelectorAll('[data-field="price"]').forEach((el) => updatePrice(el, q.price));
    setText(card, '[data-field="currency"]', q.currency || "");
    const pill = setText(card, '[data-field="change-pill"]', fmtPercent(q.change_percent));
    if (pill) setTone(pill, PILL_TONES, toneOf(q.change_percent));
    const tone = setText(card, '[data-field="change-tone"]', fmtPercent(q.change_percent));
    if (tone) setTone(tone, TEXT_TONES, toneOf(q.change_percent));
  }

  function initWatchlistQuotes() {
    const roots = Array.from(document.querySelectorAll("[data-watchlist-quotes]"));
    if (!roots.length) return;
    const slugsOf = (root) => root.dataset.watchlistQuotes.split(/\s+/).filter(Boolean);
    const slugs = Array.from(new Set(roots.flatMap(slugsOf)));

    poll(() => {
      const requests = slugs.map((slug) =>
        getJSON("/api/watchlist/" + encodeURIComponent(slug) + "/quotes").then(
          (quotes) => [slug, quotes],
          () => [slug, null],
        ),
      );
      Promise.all(requests).then((results) => {
        const bySlug = Object.fromEntries(results);
        roots.forEach((root) => {
          const failed = root.querySelector("[data-quotes-failed]");
          const lists = slugsOf(root).map((s) => bySlug[s]);
          if (failed) failed.hidden = lists.every(Boolean);
          // Si falla, se mantienen en pantalla los últimos valores.
          const quotes = Object.assign({}, ...lists.filter(Boolean));
          root.querySelectorAll("[data-quote]").forEach((card) => {
            const q = quotes[card.dataset.quote];
            if (q) paintQuote(card, q);
          });
        });
      });
    });
  }

  // ───────────────────────── Sparklines y gráfica del hero ─────────────────────────
  /** Trazado SVG (línea y área) de una serie de cierres en un lienzo W×H. */
  function seriesPath(closes, W, H, pad) {
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const pts = closes.map((v, i) => [(i / (closes.length - 1)) * W, H - pad - ((v - min) / span) * (H - pad * 2)]);
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    return { line: line, area: line + " L" + W + " " + H + " L0 " + H + " Z", last: pts[pts.length - 1] };
  }

  let gradientId = 0;
  function areaSVG(closes, W, H, heightClass, withDot) {
    const color = closes[closes.length - 1] >= closes[0] ? "var(--up)" : "var(--brand)";
    const gid = "area-" + ++gradientId;
    const p = seriesPath(closes, W, H, withDot ? 10 : 6);
    return (
      '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" class="' + heightClass + ' w-full overflow-visible" aria-hidden="true">' +
      '<defs><linearGradient id="' + gid + '" x1="0" x2="0" y1="0" y2="1">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity="0.24"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/>' +
      "</linearGradient></defs>" +
      '<path class="draw-fill" d="' + p.area + '" fill="url(#' + gid + ')"/>' +
      '<path class="draw-line" pathLength="1" d="' + p.line + '" fill="none" stroke="' + color + '" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>' +
      "</svg>"
    );
  }

  /** Marca el bloque como dibujado en el siguiente frame (arranca la transición). */
  function markDrawn(box) {
    requestAnimationFrame(() => requestAnimationFrame(() => box.setAttribute("data-drawn", "")));
  }

  /** Línea de cierres del último mes; se dibuja al entrar en pantalla. */
  function initSparklines() {
    const boxes = document.querySelectorAll("[data-sparkline]");
    boxes.forEach((box) => {
      getJSON("/api/candles/" + encodeURIComponent(box.dataset.sparkline) + "?range=1mo&interval=1d")
        .then((candles) => {
          const closes = candles.map((c) => c.close);
          box.innerHTML = closes.length < 2 ? '<div class="h-24" aria-hidden="true"></div>' : areaSVG(closes, 240, 96, "h-24", false);
          if (box.dataset.visible !== undefined) markDrawn(box);
        })
        .catch(() => (box.innerHTML = '<div class="h-24" aria-hidden="true"></div>'));
    });
    onVisible(boxes, (box) => {
      box.dataset.visible = "";
      if (box.querySelector("svg")) markDrawn(box);
    });
  }

  /** Gráfica de área grande (hero) con máximo, mínimo y variación del periodo. */
  function initAreaCharts() {
    document.querySelectorAll("[data-area-chart]").forEach((box) => {
      const card = box.closest("[data-quote]") || box.parentElement;
      getJSON("/api/candles/" + encodeURIComponent(box.dataset.areaChart) + "?range=" + (box.dataset.range || "6mo") + "&interval=1d")
        .then((candles) => {
          const closes = candles.map((c) => c.close).filter((v) => v !== null && v !== undefined);
          if (closes.length < 2) throw new Error("sin datos");
          box.innerHTML = areaSVG(closes, 600, 220, "h-full", true);
          markDrawn(box);
          const change = (closes[closes.length - 1] / closes[0] - 1) * 100;
          setText(card, '[data-chart-stat="max"]', fmtPrice(Math.max(...closes)));
          setText(card, '[data-chart-stat="min"]', fmtPrice(Math.min(...closes)));
          const stat = setText(card, '[data-chart-stat="change"]', fmtPercent(change));
          if (stat) setTone(stat, TEXT_TONES, toneOf(change));
        })
        .catch(() => {
          box.innerHTML = '<p class="grid h-full place-items-center rounded-xl bg-mist text-sm text-muted">No pudimos cargar la gráfica.</p>';
        });
    });
  }

  // ───────────────────────── Cinta de cotizaciones ─────────────────────────
  function initMarquee() {
    const toggle = document.querySelector("[data-marquee-toggle]");
    const marquee = document.querySelector("[data-marquee]");
    if (!toggle || !marquee) return;
    toggle.addEventListener("click", () => {
      const paused = !marquee.hasAttribute("data-paused");
      marquee.toggleAttribute("data-paused", paused);
      toggle.setAttribute("aria-pressed", String(paused));
      toggle.setAttribute("aria-label", paused ? "Reanudar la cinta de cotizaciones" : "Pausar la cinta de cotizaciones");
      toggle.querySelector('[data-marquee-icon="pause"]').hidden = paused;
      toggle.querySelector('[data-marquee-icon="play"]').hidden = !paused;
    });
  }

  // ───────────────────────── Contadores de métricas ─────────────────────────
  function initCounters() {
    const els = document.querySelectorAll("[data-count-to]");
    if (REDUCED_MOTION) return; // el servidor ya pinta la cifra final
    els.forEach((el) => (el.textContent = "0"));
    onVisible(els, (el) => countTo(el, 0, Number(el.dataset.countTo), (v) => String(Math.round(v)), 1200));
  }

  // ───────────────────────── Carrusel ─────────────────────────
  function initCarousels() {
    document.querySelectorAll("[data-carousel]").forEach((root) => {
      const track = root.querySelector("[data-carousel-track]");
      const prev = root.querySelector("[data-carousel-prev]");
      const next = root.querySelector("[data-carousel-next]");
      if (!track || !prev || !next) return;

      function step() {
        const item = track.firstElementChild;
        const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
        return item ? item.getBoundingClientRect().width + gap : track.clientWidth;
      }
      function update() {
        const max = track.scrollWidth - track.clientWidth - 2;
        prev.disabled = track.scrollLeft <= 2;
        next.disabled = track.scrollLeft >= max;
      }
      const behavior = REDUCED_MOTION ? "auto" : "smooth";
      prev.addEventListener("click", () => track.scrollBy({ left: -step(), behavior: behavior }));
      next.addEventListener("click", () => track.scrollBy({ left: step(), behavior: behavior }));
      track.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight") track.scrollBy({ left: step(), behavior: behavior });
        else if (e.key === "ArrowLeft") track.scrollBy({ left: -step(), behavior: behavior });
        else return;
        e.preventDefault();
      });
      track.addEventListener("scroll", update, { passive: true });
      window.addEventListener("resize", update);
      update();
    });
  }

  // ───────────────────────── Formularios de cuenta ─────────────────────────
  /** Botón para mostrar u ocultar la contraseña. */
  function initPasswordToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
      const input = document.getElementById(btn.getAttribute("aria-controls"));
      if (!input) return;
      btn.hidden = false;
      btn.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.setAttribute("aria-pressed", String(show));
        btn.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
        btn.querySelector('[data-eye="show"]').hidden = show;
        btn.querySelector('[data-eye="hide"]').hidden = !show;
      });
    });
  }

  /** Mensaje de error de un campo (null si es válido). */
  function fieldError(input, form) {
    const value = input.value.trim();
    if (input.required && !value) {
      return input.type === "email" ? "Escribe tu correo." : input.type === "password" ? "Escribe tu contraseña." : "Este campo es obligatorio.";
    }
    if (!value) return null;
    if (input.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return "Escribe un correo válido, por ejemplo nombre@correo.com.";
    if (input.minLength > 0 && input.value.length < input.minLength) return "Usa al menos " + input.minLength + " caracteres.";
    if (input.pattern && !new RegExp("^(?:" + input.pattern + ")$").test(value)) return "El código tiene 6 dígitos.";
    const match = input.dataset.matches && form.querySelector("#" + input.dataset.matches);
    if (match && input.value !== match.value) return "Las contraseñas no coinciden.";
    return null;
  }

  function showFieldError(input, message) {
    const box = document.getElementById(input.id + "-error");
    input.setAttribute("aria-invalid", message ? "true" : "false");
    if (!box) return;
    box.hidden = !message;
    box.querySelector("[data-error-text]").textContent = message || "";
  }

  function setLoading(btn, on) {
    const label = btn.querySelector("[data-label]");
    btn.toggleAttribute("data-loading", on);
    btn.setAttribute("aria-busy", String(on));
    if (label) {
      if (on && !btn.dataset.idleLabel) btn.dataset.idleLabel = label.textContent;
      label.textContent = on ? btn.dataset.loadingLabel || "Enviando…" : btn.dataset.idleLabel || label.textContent;
    }
    const spinner = btn.querySelector(".spinner");
    if (on && !spinner) btn.insertAdjacentHTML("afterbegin", '<span class="spinner" aria-hidden="true"></span>');
    if (!on && spinner) spinner.remove();
  }

  /** Validación inline en español y estado de carga del botón al enviar. */
  function initAuthForms() {
    document.querySelectorAll("[data-auth-form]").forEach((form) => {
      const inputs = Array.from(form.querySelectorAll("input.field-input"));
      inputs.forEach((input) =>
        input.addEventListener("input", () => {
          if (input.getAttribute("aria-invalid") === "true") showFieldError(input, fieldError(input, form));
        }),
      );
      inputs.forEach((input) =>
        input.addEventListener("blur", () => {
          if (input.value) showFieldError(input, fieldError(input, form));
        }),
      );

      form.addEventListener("submit", (e) => {
        const submitter = e.submitter || form.querySelector('button[type="submit"]');
        if (form.dataset.submitting) {
          e.preventDefault();
          return;
        }
        // "Reenviar código" (formnovalidate) no necesita validar los campos.
        if (!(submitter && submitter.formNoValidate)) {
          let firstInvalid = null;
          inputs.forEach((input) => {
            const message = fieldError(input, form);
            showFieldError(input, message);
            if (message && !firstInvalid) firstInvalid = input;
          });
          if (firstInvalid) {
            e.preventDefault();
            firstInvalid.focus();
            return;
          }
        }
        // No se deshabilita el botón: así el navegador envía su name/value.
        form.dataset.submitting = "1";
        if (submitter) setLoading(submitter, true);
      });
    });

    // Al volver con "atrás" (bfcache) los botones no deben quedarse cargando.
    window.addEventListener("pageshow", (e) => {
      if (!e.persisted) return;
      document.querySelectorAll("[data-auth-form]").forEach((form) => {
        delete form.dataset.submitting;
        form.querySelectorAll("[data-loading]").forEach((btn) => setLoading(btn, false));
      });
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
      layout: { background: { type: LC.ColorType.Solid, color: "#ffffff" }, textColor: "#6b6b6b", fontFamily: '"JetBrains Mono", monospace' },
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

  initReveal();
  initNavbar();
  initMobileNav();
  initGuilloche();
  initWatchlistQuotes();
  initSparklines();
  initAreaCharts();
  initMarquee();
  initCounters();
  initCarousels();
  initPasswordToggles();
  initAuthForms();
  initChartWorkspace();
  initReportBuilder();
})();
