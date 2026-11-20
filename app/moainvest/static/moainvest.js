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
  /** Rellena cada [data-quote="TICKER"] con su precio; se refresca cada 15 s. */
  function initWatchlistQuotes() {
    document.querySelectorAll("[data-watchlist-quotes]").forEach((root) => {
      const slug = root.dataset.watchlistQuotes;
      const url = root.dataset.quotesUrl || "/api/watchlist/" + encodeURIComponent(slug) + "/quotes";
      const failed = root.querySelector("[data-quotes-failed]");
      poll(() =>
        getJSON(url)
          .then((quotes) => {
            if (failed) failed.hidden = true;
            // Otros bloques (panorama de /mercados) escuchan los precios sin pedirlos otra vez.
            document.dispatchEvent(new CustomEvent("moainvest:quotes", { detail: { slug: slug, root: root, quotes: quotes } }));
            const counter = root.querySelector("[data-market-count]");
            if (counter) {
              const moves = Object.values(quotes).map((q) => q.change_percent).filter((v) => v !== null && v !== undefined);
              const up = moves.filter((v) => v >= 0).length;
              counter.textContent = "Hoy: " + up + " suben · " + (moves.length - up) + " bajan";
            }
            root.querySelectorAll("[data-quote]").forEach((card) => {
              const q = quotes[card.dataset.quote];
              if (!q) return;
              setText(card, '[data-field="price"]', fmtPrice(q.price));
              setText(card, '[data-field="currency"]', q.currency || "");
              const pill = setText(card, '[data-field="change-pill"]', fmtPercent(q.change_percent));
              if (pill) setTone(pill, PILL_TONES, toneOf(q.change_percent));
              const tone = setText(card, '[data-field="change-tone"]', fmtPercent(q.change_percent));
              if (tone) setTone(tone, TEXT_TONES, toneOf(q.change_percent));
            });
          })
          // Se mantienen en pantalla los últimos valores.
          .catch(() => failed && (failed.hidden = false)),
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

  function loadSparkline(box) {
    getJSON("/api/candles/" + encodeURIComponent(box.dataset.sparkline) + "?range=1mo&interval=1d")
      .then((candles) => renderSparkline(box, candles.map((c) => c.close)))
      .catch(() => renderSparkline(box, []));
  }

  /** Las marcadas con data-sparkline-lazy se piden al acercarse a la pantalla (páginas con muchos activos). */
  function initSparklines() {
    const lazy = "IntersectionObserver" in window ? new IntersectionObserver(
      (entries) => entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        lazy.unobserve(entry.target);
        loadSparkline(entry.target);
      }),
      { rootMargin: "300px 0px" },
    ) : null;
    document.querySelectorAll("[data-sparkline]").forEach((box) => {
      if (lazy && box.hasAttribute("data-sparkline-lazy")) lazy.observe(box);
      else loadSparkline(box);
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

  // ───────────────────────── Radar de noticias ─────────────────────────
  const RADAR_POLL_MS = 5 * 60 * 1000;
  const RADAR_PAGE = 6;
  const SENTIMENT_UI = {
    alcista: { label: "Alcista", badge: "bg-up-soft text-up", mark: "bg-up-soft text-up" },
    bajista: { label: "Bajista", badge: "bg-brand-soft text-brand-deep", mark: "bg-brand-soft text-brand-deep" },
    neutral: { label: "Neutral", badge: "bg-mist text-muted", mark: "" },
  };
  const SIGNAL_UI = {
    confirma: { label: "Confirma", badge: "bg-up-soft text-up" },
    divergencia: { label: "Divergencia", badge: "bg-brand text-white" },
    neutral: { label: "Mixto", badge: "bg-mist text-ink/80" },
    "sin-noticias": { label: "Sin noticias", badge: "bg-mist text-muted" },
    "sin-precio": { label: "Sin precio", badge: "bg-mist text-muted" },
  };
  const FILTER_TONES = { on: "bg-ink text-white", off: "bg-mist text-ink/80 hover:bg-line" };

  function esc(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function timeAgo(iso) {
    const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    if (minutes < 60) return "hace " + minutes + " min";
    const hours = Math.round(minutes / 60);
    if (hours < 24) return "hace " + hours + " h";
    const days = Math.round(hours / 24);
    return "hace " + days + (days === 1 ? " día" : " días");
  }

  /** Resalta en el titular las palabras que deciden su sentimiento. */
  function highlight(title, senales) {
    const words = [
      ...senales.alcistas.map((w) => [w, SENTIMENT_UI.alcista.mark]),
      ...senales.bajistas.map((w) => [w, SENTIMENT_UI.bajista.mark]),
    ];
    let html = esc(title);
    words.forEach(([word, cls]) => {
      const re = new RegExp("(^|[^\\p{L}\\p{N}-])(" + esc(word).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")(?![\\p{L}\\p{N}-])", "iu");
      html = html.replace(re, '$1<mark class="rounded px-0.5 ' + cls + '">$2</mark>');
    });
    return html;
  }

  function renderPulse(root, pulso) {
    const value = pulso.valor;
    setText(root, "[data-pulse-value]", value == null ? "—" : String(value));
    setText(root, "[data-pulse-label]", pulso.etiqueta);
    setText(root, "[data-pulse-description]", pulso.descripcion);
    const needle = root.querySelector("[data-pulse-needle]");
    // 0 → -90° (miedo), 50 → 0°, 100 → 90° (euforia).
    if (needle) needle.style.transform = "rotate(" + ((value == null ? 50 : value) * 1.8 - 90) + "deg)";
    const gauge = root.querySelector("[data-pulse-gauge]");
    if (gauge) gauge.setAttribute("aria-label", "Termómetro del mercado: " + (value == null ? "sin datos" : value + " de 100, " + pulso.etiqueta));
    const total = pulso.total || 1;
    Object.entries(pulso.conteo).forEach(([key, n]) => {
      const bar = root.querySelector('[data-pulse-bar="' + key + '"]');
      if (bar) bar.style.width = (pulso.total ? (n / total) * 100 : 0) + "%";
    });
    setText(root, "[data-pulse-counts]", "");
    const counts = root.querySelector("[data-pulse-counts]");
    if (counts) {
      counts.innerHTML =
        '<span class="text-up">' + pulso.conteo.alcista + " alcistas</span>" +
        "<span>" + pulso.conteo.neutral + " neutrales</span>" +
        '<span class="text-brand">' + pulso.conteo.bajista + " bajistas</span>";
    }
  }

  function renderAssets(root, slug, activos) {
    const list = root.querySelector("[data-radar-assets]");
    list.innerHTML = activos
      .map((a) => {
        const ui = SIGNAL_UI[a.estado] || SIGNAL_UI.neutral;
        // Barra de tono: de -1 (izquierda, rojo) a 1 (derecha, verde).
        const tone = a.tono == null ? null : a.tono;
        const pos = tone == null ? 50 : 50 + tone * 50;
        const toneColor = tone == null ? "bg-line" : tone >= 0.2 ? "bg-up" : tone <= -0.2 ? "bg-brand" : "bg-muted";
        const change = a.variacion == null ? "—" : fmtPercent(a.variacion);
        const changeTone = a.variacion == null ? "text-muted" : a.variacion >= 0 ? "text-up" : "text-brand";
        return (
          '<li class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 py-3 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_5rem_7rem]">' +
          '<a class="min-w-0 hover:text-brand" href="/graficas/' + encodeURIComponent(slug) + "/" + encodeURIComponent(a.ticker) + '">' +
          '<span class="block truncate font-semibold tracking-tight">' + esc(a.nombre) + "</span>" +
          '<span class="font-mono text-xs text-muted">' + esc(a.ticker) + " · " + a.noticias + (a.noticias === 1 ? " titular" : " titulares") + "</span></a>" +
          '<span class="order-last col-span-2 sm:order-none sm:col-span-1" title="Tono de sus noticias">' +
          '<span class="relative block h-1.5 rounded-full bg-mist"><span class="absolute left-1/2 top-0 h-1.5 w-px bg-line"></span>' +
          '<span class="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white ' + toneColor + '" style="left:' + pos.toFixed(1) + '%"></span></span>' +
          '<span class="mt-1 block text-xs text-muted">' + esc(a.texto) + "</span></span>" +
          '<span class="hidden text-right font-mono text-sm tabular-nums sm:block ' + changeTone + '">' + change + "</span>" +
          '<span class="justify-self-end rounded-full px-2.5 py-1 font-mono text-xs ' + ui.badge + '">' + ui.label + "</span>" +
          "</li>"
        );
      })
      .join("");
  }

  function renderNewsItem(slug, n) {
    const ui = SENTIMENT_UI[n.sentimiento] || SENTIMENT_UI.neutral;
    const words = [...n.senales.alcistas, ...n.senales.bajistas];
    const why = words.length
      ? "Palabras clave: " + words.map((w) => "«" + esc(w) + "»").join(", ")
      : "Sin palabras clave de subida o bajada: tono neutral.";
    const title = n.url
      ? '<a href="' + esc(n.url) + '" target="_blank" rel="noopener noreferrer" class="hover:text-brand">' + highlight(n.titulo, n.senales) + "</a>"
      : highlight(n.titulo, n.senales);
    const chips = n.activos
      .map(
        (a) =>
          '<a href="/graficas/' + encodeURIComponent(slug) + "/" + encodeURIComponent(a.ticker) + '" class="rounded-full border border-line px-2 py-0.5 font-mono text-xs text-muted hover:border-brand/40 hover:text-brand">' +
          esc(a.ticker) + "</a>",
      )
      .join("");
    return (
      '<li class="flex h-full flex-col rounded-2xl border border-line bg-white p-5" data-sentiment="' + n.sentimiento + '">' +
      '<div class="flex items-center justify-between gap-3">' +
      '<span class="rounded-full px-2.5 py-0.5 font-mono text-xs ' + ui.badge + '">' + ui.label + "</span>" +
      '<span class="truncate font-mono text-xs text-muted">' + esc(n.fuente || "Yahoo Finance") + " · " + timeAgo(n.publicado) + "</span></div>" +
      '<p class="mt-3 text-pretty font-semibold leading-snug tracking-tight">' + title + "</p>" +
      '<p class="mt-2 text-xs text-muted">' + why + "</p>" +
      '<div class="mt-auto flex flex-wrap gap-1.5 pt-4">' + chips + "</div>" +
      "</li>"
    );
  }

  function initNewsRadar() {
    const root = document.querySelector("[data-news-radar]");
    if (!root) return;
    const slug = root.dataset.newsRadar;
    const list = root.querySelector("[data-radar-news]");
    const more = root.querySelector("[data-radar-more]");
    const failed = root.querySelector("[data-radar-failed]");
    const filters = root.querySelectorAll("[data-radar-filter]");
    let items = [];
    let filter = "todos";
    let shown = RADAR_PAGE;

    function renderNews() {
      const visible = items.filter((n) => filter === "todos" || n.sentimiento === filter);
      list.innerHTML = visible.length
        ? visible.slice(0, shown).map((n) => renderNewsItem(slug, n)).join("")
        : '<li class="rounded-2xl border border-dashed border-line p-6 text-sm text-muted md:col-span-2">No hay titulares de este tipo en las últimas 72 horas.</li>';
      more.hidden = visible.length <= shown;
      filters.forEach((btn) => {
        const key = btn.dataset.radarFilter;
        const count = key === "todos" ? items.length : items.filter((n) => n.sentimiento === key).length;
        btn.querySelector("[data-radar-filter-count]").textContent = String(count);
      });
    }

    filters.forEach((btn) =>
      btn.addEventListener("click", () => {
        filter = btn.dataset.radarFilter;
        shown = RADAR_PAGE;
        filters.forEach((b) => {
          const on = b === btn;
          b.setAttribute("aria-pressed", String(on));
          setTone(b, FILTER_TONES, on ? "on" : "off");
        });
        renderNews();
      }),
    );
    more.addEventListener("click", () => {
      shown += RADAR_PAGE;
      renderNews();
    });

    function load() {
      getJSON("/api/radar?watchlist=" + encodeURIComponent(slug))
        .then((data) => {
          failed.hidden = true;
          items = data.noticias;
          renderPulse(root, data.pulso);
          renderAssets(root, slug, data.activos);
          renderNews();
          setText(root, "[data-radar-updated]", "Actualizado " + new Date(data.actualizado).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" }));
        })
        .catch(() => {
          failed.hidden = false;
          if (!items.length) list.innerHTML = "";
          setText(root, "[data-radar-updated]", "");
        });
    }
    load();
    setInterval(load, RADAR_POLL_MS);
  }

  // ───────────────────────── Mercados ─────────────────────────
  const MARKET_LINK_TONES = { on: "bg-ink text-white", off: "bg-mist text-ink/80 hover:bg-line" };

  /** Marca en la barra de categorías la sección que se está leyendo. */
  function initMarketNav() {
    const nav = document.querySelector("[data-market-nav]");
    if (!nav || !("IntersectionObserver" in window)) return;
    const links = nav.querySelectorAll("[data-market-link]");
    function activate(slug) {
      links.forEach((a) => {
        const on = a.dataset.marketLink === slug;
        setTone(a, MARKET_LINK_TONES, on ? "on" : "off");
        if (on) {
          a.setAttribute("aria-current", "true");
          a.scrollIntoView({ block: "nearest", inline: "nearest" });
        } else a.removeAttribute("aria-current");
      });
    }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && activate(e.target.dataset.market)),
      { rootMargin: "-40% 0px -55% 0px" },
    );
    document.querySelectorAll("[data-market]").forEach((section) => io.observe(section));
  }

  /** Panorama: cuántos activos suben y los extremos del día, con los precios que ya llegan a la página. */
  function initMarketBreadth() {
    const root = document.querySelector("[data-market-breadth]");
    if (!root) return;
    const all = {};
    document.addEventListener("moainvest:quotes", (e) => {
      const { root: section, quotes, slug } = e.detail;
      // Los bonos públicos son rendimientos, no precios: no cuentan como "subir" o "bajar".
      if (section.querySelector("[data-yield-curve]")) return;
      Object.entries(quotes).forEach(([ticker, q]) => {
        if (q.change_percent === null || q.change_percent === undefined) return;
        const card = section.querySelector('[data-quote="' + CSS.escape(ticker) + '"]');
        const nameEl = card && card.querySelector(".font-semibold");
        all[slug + ":" + ticker] = { ticker: ticker, name: nameEl ? nameEl.textContent.trim() : ticker, change: q.change_percent };
      });
      const items = Object.values(all);
      const up = items.filter((i) => i.change >= 0).length;
      setText(root, "[data-breadth-up]", String(up));
      setText(root, "[data-breadth-total]", String(items.length));
      root.querySelector('[data-breadth-bar="up"]').style.width = (items.length ? (up / items.length) * 100 : 0) + "%";
      root.querySelector('[data-breadth-bar="down"]').style.width = (items.length ? ((items.length - up) / items.length) * 100 : 0) + "%";
      const sorted = items.slice().sort((a, b) => b.change - a.change);
      const row = (i) =>
        '<li class="flex items-center justify-between gap-3"><span class="min-w-0 truncate">' + esc(i.name) +
        ' <span class="font-mono text-xs text-muted">' + esc(i.ticker) + "</span></span>" +
        '<span class="font-mono tabular-nums ' + (i.change >= 0 ? "text-up" : "text-brand") + '">' + fmtPercent(i.change) + "</span></li>";
      root.querySelector('[data-breadth-list="up"]').innerHTML = sorted.filter((i) => i.change > 0).slice(0, 3).map(row).join("") || '<li class="text-muted">Nada sube por ahora.</li>';
      root.querySelector('[data-breadth-list="down"]').innerHTML = sorted.filter((i) => i.change < 0).reverse().slice(0, 3).map(row).join("") || '<li class="text-muted">Nada baja por ahora.</li>';
    });
  }

  function initBondFilters() {
    document.querySelectorAll("[data-bond-filters]").forEach((group) => {
      const section = group.closest("[data-market]");
      const buttons = group.querySelectorAll("[data-bond-filter]");
      buttons.forEach((btn) =>
        btn.addEventListener("click", () => {
          const value = btn.dataset.bondFilter;
          buttons.forEach((b) => {
            const on = b === btn;
            b.setAttribute("aria-pressed", String(on));
            setTone(b, FILTER_TONES, on ? "on" : "off");
          });
          section.querySelectorAll("[data-bond-group]").forEach((row) => {
            row.hidden = value !== "Todos" && row.dataset.bondGroup !== value;
          });
        }),
      );
    });
  }

  const CURVE_TONES = { normal: "bg-up-soft text-up", plana: "bg-mist text-ink", invertida: "bg-brand-soft text-brand-deep", "sin-datos": "bg-mist text-muted" };

  /** Curva de rendimiento: eje X en raíz cuadrada de los años para que 3 meses y 30 años quepan. */
  function renderCurve(box, points) {
    const pts = points.filter((p) => p.rendimiento !== null && p.rendimiento !== undefined);
    if (pts.length < 2) {
      box.innerHTML = '<p class="py-16 text-center text-sm text-muted">Sin datos suficientes para dibujar la curva.</p>';
      return;
    }
    const W = 560, H = 220, L = 40, R = 24, T = 32, B = 32;
    const maxX = Math.sqrt(Math.max(...points.map((p) => p.anios)));
    const ys = pts.map((p) => p.rendimiento);
    const lo = Math.floor(Math.min(...ys) - 0.25), hi = Math.ceil(Math.max(...ys) + 0.25);
    const x = (years) => L + (Math.sqrt(years) / maxX) * (W - L - R);
    const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
    let grid = "";
    for (let v = lo; v <= hi; v += (hi - lo) > 3 ? 1 : 0.5) {
      grid += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--color-line)"/>' +
        '<text x="' + (L - 8) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="11" fill="var(--color-muted)">' + v.toFixed(1) + "%</text>";
    }
    const line = pts.map((p, i) => (i ? "L" : "M") + x(p.anios).toFixed(1) + " " + y(p.rendimiento).toFixed(1)).join(" ");
    const dots = pts.map((p) =>
      '<circle cx="' + x(p.anios) + '" cy="' + y(p.rendimiento) + '" r="5" fill="var(--color-brand)" stroke="#fff" stroke-width="2"/>' +
      '<text x="' + x(p.anios) + '" y="' + (y(p.rendimiento) - 12) + '" text-anchor="middle" font-size="12" font-weight="600" fill="var(--color-ink)">' + p.rendimiento.toFixed(2) + "%</text>" +
      '<text x="' + x(p.anios) + '" y="' + (H - 10) + '" text-anchor="middle" font-size="11" fill="var(--color-muted)">' + (p.anios < 1 ? Math.round(p.anios * 12) + " m" : p.anios + " a") + "</text>",
    ).join("");
    box.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" class="w-full" role="img" aria-label="Curva de rendimiento del Tesoro de EE. UU.">' +
      grid + '<path d="' + line + '" fill="none" stroke="var(--color-brand)" stroke-width="2.5" stroke-linejoin="round"/>' + dots + "</svg>";
  }

  function initYieldCurve() {
    document.querySelectorAll("[data-yield-curve]").forEach((root) => {
      const text = root.querySelector("[data-curve-text]");
      const load = () =>
        getJSON(root.dataset.curveUrl)
          .then((data) => {
            renderCurve(root.querySelector("[data-curve-chart]"), data.puntos);
            text.textContent = data.texto;
            setTone(text, CURVE_TONES, data.estado in CURVE_TONES ? data.estado : "sin-datos");
          })
          .catch(() => (text.textContent = "No pudimos cargar la curva ahora."));
      load();
      setInterval(load, 60000);
    });
  }

  initReveal();
  initMobileNav();
  initWatchlistQuotes();
  initSparklines();
  initChartWorkspace();
  initNewsRadar();
  initMarketNav();
  initMarketBreadth();
  initBondFilters();
  initYieldCurve();
})();
