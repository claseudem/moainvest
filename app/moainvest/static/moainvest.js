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
      const failed = root.querySelector("[data-quotes-failed]");
      poll(() =>
        getJSON("/api/watchlist/" + encodeURIComponent(slug) + "/quotes")
          .then((quotes) => {
            if (failed) failed.hidden = true;
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

  // ───────────────────────── Utilidades DOM ─────────────────────────
  /** Crea un elemento con clases y texto (el texto nunca se interpreta como HTML). */
  function h(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined && text !== null) el.textContent = text;
    return el;
  }

  function timeAgo(iso) {
    const t = Date.parse(iso || "");
    if (Number.isNaN(t)) return "";
    const rtf = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
    const mins = Math.round((t - Date.now()) / 60000);
    if (Math.abs(mins) < 60) return rtf.format(mins, "minute");
    const hours = Math.round(mins / 60);
    if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
    return rtf.format(Math.round(hours / 24), "day");
  }

  const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ───────────────────────── Sparklines ─────────────────────────
  const SPARK_W = 240;
  const SPARK_H = 80;
  const sparkY = (v, min, span) => SPARK_H - 6 - ((v - min) / span) * (SPARK_H - 14);
  const fmtDay = (t) => new Date(t * 1000).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });

  /** Línea de cierres del último mes como SVG plano (sin librería de gráficos). */
  function renderSparkline(box, candles) {
    candles = candles.filter((c) => c.close !== null && c.close !== undefined);
    const closes = candles.map((c) => c.close);
    if (closes.length < 2) {
      box.innerHTML = '<div class="h-20" aria-hidden="true"></div>';
      return;
    }
    const W = SPARK_W;
    const H = SPARK_H;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const line = closes
      .map((v, i) => (i ? "L" : "M") + ((i / (closes.length - 1)) * W).toFixed(1) + " " + sparkY(v, min, span).toFixed(1))
      .join(" ");
    const color = closes[closes.length - 1] >= closes[0] ? "var(--color-up)" : "var(--color-brand)";
    const gid = "spark-" + box.dataset.sparkline.replace(/[^a-z0-9]/gi, "");
    box.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" class="h-20 w-full overflow-visible" aria-hidden="true">' +
      '<defs><linearGradient id="' + gid + '" x1="0" x2="0" y1="0" y2="1">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity="0.22"/><stop offset="0.7" stop-color="' + color + '" stop-opacity="0.04"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/>' +
      "</linearGradient></defs>" +
      '<line x1="0" x2="' + W + '" y1="' + sparkY(closes[0], min, span).toFixed(1) + '" y2="' + sparkY(closes[0], min, span).toFixed(1) + '" stroke="var(--color-line)" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + line + " L" + W + " " + H + " L0 " + H + ' Z" fill="url(#' + gid + ')"/>' +
      '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>' +
      "</svg>";
    box.style.color = color;
    const lastDot = h("span", "spark-last");
    lastDot.style.left = "100%";
    lastDot.style.top = (sparkY(closes[closes.length - 1], min, span) / H) * 100 + "%";
    box.append(lastDot);
    enableSparkHover(box, candles, min, span);
    renderPeriodRange(box, candles);
  }

  /** Indicador vertical, punto y tooltip del cierre más cercano al cursor. */
  function enableSparkHover(box, candles, min, span) {
    box.classList.add("spark-hover");
    const guide = h("span", "spark-guide");
    const dot = h("span", "spark-dot");
    const tip = h("span", "spark-tip");
    box.append(guide, dot, tip);
    const last = candles.length - 1;
    let shown = -1;

    function show(clientX) {
      const rect = box.getBoundingClientRect();
      const i = Math.round(Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * last);
      box.setAttribute("data-active", "");
      if (i === shown) return;
      shown = i;
      const c = candles[i];
      const x = (i / last) * 100;
      const y = (sparkY(c.close, min, span) / SPARK_H) * 100;
      guide.style.left = x + "%";
      dot.style.left = x + "%";
      dot.style.top = y + "%";
      tip.style.left = Math.min(82, Math.max(18, x)) + "%";
      tip.style.top = y + "%";
      tip.replaceChildren(document.createTextNode(fmtPrice(c.close)), h("small", "", c.time ? fmtDay(c.time) : ""));
    }
    box.addEventListener("pointermove", (e) => show(e.clientX));
    box.addEventListener("pointerdown", (e) => e.pointerType !== "mouse" && show(e.clientX));
    box.addEventListener("pointerleave", () => {
      box.removeAttribute("data-active");
      shown = -1;
    });
  }

  /** Mínimo y máximo del periodo bajo la gráfica, con la posición del último cierre. */
  function renderPeriodRange(box, candles) {
    const card = box.closest("[data-quote]");
    const range = card && card.querySelector("[data-period-range]");
    if (!range) return;
    const lows = candles.map((c) => (c.low ?? c.close));
    const highs = candles.map((c) => (c.high ?? c.close));
    const lo = Math.min(...lows);
    const hi = Math.max(...highs);
    const lastClose = candles[candles.length - 1].close;
    setText(range, "[data-range-min]", fmtPrice(lo));
    setText(range, "[data-range-max]", fmtPrice(hi));
    const marker = range.querySelector("[data-range-marker]");
    if (marker) marker.style.left = (hi > lo ? ((lastClose - lo) / (hi - lo)) * 100 : 50) + "%";
    range.hidden = false;
  }

  function initSparklines() {
    document.querySelectorAll("[data-sparkline]").forEach((box) => {
      getJSON("/api/candles/" + encodeURIComponent(box.dataset.sparkline) + "?range=1mo&interval=1d")
        .then((candles) => renderSparkline(box, candles))
        .catch(() => renderSparkline(box, []));
    });
  }

  // ───────────────────────── Carrusel (noticias y comunidad) ─────────────────────────
  /**
   * Carrusel continuo: se desplaza solo (salvo con «reducir movimiento»), se
   * pausa con el cursor, el foco o el dedo, se arrastra con el ratón y tiene
   * flechas. Para que el bucle no tenga costuras, las diapositivas se clonan
   * (los clones quedan ocultos a lectores de pantalla) y el scroll salta una
   * copia entera, invisible, al pasar del final. La diapositiva más cercana
   * al centro recibe [data-focus].
   */
  const CAROUSEL_SPEED = 0.03; // px por ms

  function createCarousel(root) {
    const viewport = root.querySelector("[data-carousel-viewport]");
    const track = root.querySelector("[data-carousel-track]");
    viewport.style.position = "relative";
    let slides = [];
    let loopW = 0; // ancho de una copia completa
    let pos = 0;
    let hover = false;
    let focusInside = false;
    let touching = false;
    let touchTimer = 0;
    let navigating = 0;
    let onScreen = true;
    let drag = null;
    let suppressClick = false;
    let focused = null;
    let last = 0;

    const paused = () => hover || focusInside || touching || navigating || drag || !onScreen || document.hidden || reducedMotion();

    function wrap(x) {
      if (!loopW) return x;
      while (x >= loopW) x -= loopW;
      while (x < 0) x += loopW;
      return x;
    }

    function updateFocus() {
      const center = viewport.scrollLeft + viewport.clientWidth / 2;
      let best = null;
      let dist = Infinity;
      for (const s of slides) {
        const d = Math.abs(s.offsetLeft + s.offsetWidth / 2 - center);
        if (d < dist) {
          dist = d;
          best = s;
        }
      }
      if (best !== focused) {
        if (focused) focused.removeAttribute("data-focus");
        if (best) best.setAttribute("data-focus", "");
        focused = best;
      }
    }

    function setSlides(nodes) {
      track.replaceChildren(...nodes);
      slides = nodes.slice();
      loopW = 0;
      if (nodes.length < 2) return updateFocus();
      // Copias hasta cubrir una vuelta + el ancho visible + una diapositiva.
      const step = nodes[1].offsetLeft - nodes[0].offsetLeft;
      loopW = step * nodes.length;
      const needed = loopW + viewport.clientWidth + step * 2;
      while (track.scrollWidth < needed) {
        nodes.forEach((n) => {
          const clone = n.cloneNode(true);
          clone.setAttribute("aria-hidden", "true");
          clone.removeAttribute("data-focus");
          clone.querySelectorAll("a, button").forEach((el) => el.setAttribute("tabindex", "-1"));
          if (clone.matches("a")) clone.setAttribute("tabindex", "-1");
          track.append(clone);
          slides.push(clone);
        });
      }
      // Empieza con la primera noticia centrada.
      pos = wrap(nodes[0].offsetLeft + nodes[0].offsetWidth / 2 - viewport.clientWidth / 2);
      viewport.scrollLeft = pos;
      updateFocus();
    }

    function tick(t) {
      const dt = last ? Math.min(64, t - last) : 16;
      last = t;
      if (loopW && !paused()) {
        pos = wrap(pos + CAROUSEL_SPEED * dt);
        viewport.scrollLeft = pos;
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    viewport.addEventListener(
      "scroll",
      () => {
        // Scroll manual (rueda, dedo, flechas): se mantiene en la copia central.
        if (loopW && !drag && !navigating) {
          const sl = viewport.scrollLeft;
          if (sl >= loopW + 1 || sl < 1) viewport.scrollLeft = wrap(sl) || loopW;
        }
        if (paused()) pos = viewport.scrollLeft;
        updateFocus();
      },
      { passive: true },
    );

    viewport.addEventListener("pointerenter", (e) => e.pointerType === "mouse" && (hover = true));
    viewport.addEventListener("pointerleave", (e) => e.pointerType === "mouse" && (hover = false));
    root.addEventListener("focusin", () => (focusInside = true));
    root.addEventListener("focusout", (e) => !root.contains(e.relatedTarget) && (focusInside = false));
    // Con el dedo: pausa mientras toca y 2,5 s después de soltar.
    viewport.addEventListener("touchstart", () => {
      clearTimeout(touchTimer);
      touching = true;
    }, { passive: true });
    viewport.addEventListener("touchend", () => {
      clearTimeout(touchTimer);
      touchTimer = setTimeout(() => (touching = false), 2500);
    }, { passive: true });

    // Arrastrar con el ratón (en táctil ya hay scroll nativo).
    viewport.addEventListener("dragstart", (e) => e.preventDefault());
    viewport.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      drag = { x: e.clientX, start: viewport.scrollLeft, moved: false, id: e.pointerId };
    });
    viewport.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x;
      if (!drag.moved && Math.abs(dx) < 5) return;
      if (!drag.moved) {
        drag.moved = true;
        viewport.setAttribute("data-dragging", "");
        viewport.setPointerCapture(e.pointerId);
      }
      let next = drag.start - dx;
      if (loopW && next >= loopW) { drag.start -= loopW; next -= loopW; }
      if (loopW && next < 0) { drag.start += loopW; next += loopW; }
      viewport.scrollLeft = next;
    });
    function endDrag() {
      if (!drag) return;
      suppressClick = drag.moved;
      drag = null;
      viewport.removeAttribute("data-dragging");
      pos = viewport.scrollLeft;
    }
    viewport.addEventListener("pointerup", endDrag);
    viewport.addEventListener("pointercancel", endDrag);
    viewport.addEventListener(
      "click",
      (e) => {
        if (!suppressClick) return;
        suppressClick = false;
        e.preventDefault();
        e.stopPropagation();
      },
      true,
    );

    function go(dir) {
      if (slides.length < 2) return;
      const step = slides[1].offsetLeft - slides[0].offsetLeft;
      const max = viewport.scrollWidth - viewport.clientWidth;
      // Se salta antes a la copia equivalente para que el desplazamiento suave no choque con un borde.
      if (dir < 0 && viewport.scrollLeft - step < 0) viewport.scrollLeft += loopW;
      if (dir > 0 && viewport.scrollLeft + step > max) viewport.scrollLeft -= loopW;
      clearTimeout(navigating);
      navigating = setTimeout(() => {
        navigating = 0;
        pos = viewport.scrollLeft;
      }, 650);
      viewport.scrollBy({ left: dir * step, behavior: reducedMotion() ? "auto" : "smooth" });
    }
    root.querySelector("[data-carousel-prev]")?.addEventListener("click", () => go(-1));
    root.querySelector("[data-carousel-next]")?.addEventListener("click", () => go(1));

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(([entry]) => (onScreen = entry.isIntersecting)).observe(viewport);
    }
    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => slides.length && setSlides(slides.slice(0, slides.length).filter((s) => !s.hasAttribute("aria-hidden"))), 200);
    });

    return { setSlides };
  }

  // Noticias ──
  const TREND_TAGS = {
    subir: { label: "▲ Subir", cls: "bg-up-soft text-up" },
    bajar: { label: "▼ Bajar", cls: "bg-brand-soft text-brand-deep" },
    medio: { label: "◆ Medio", cls: "bg-white/90 text-muted" },
  };

  function trendTag(trend, extra) {
    const info = TREND_TAGS[trend] || TREND_TAGS.medio;
    return h("span", "inline-flex items-center rounded-full px-2.5 py-1 font-mono text-[0.65rem] tracking-[0.12em] uppercase " + info.cls + (extra ? " " + extra : ""), info.label);
  }

  function newsSlide(item, names) {
    const li = h("li", "carousel-slide");
    const card = h(item.url ? "a" : "article", "spotlight group flex h-full flex-col rounded-2xl border border-line bg-white p-2.5 transition-[border-color,box-shadow] duration-500");
    card.setAttribute("data-spotlight", "");
    if (item.url) {
      card.href = item.url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";
      card.setAttribute("data-cursor-label", "Leer ↗");
    }
    const cover = h("div", "relative h-44 overflow-hidden rounded-xl bg-mist");
    if (item.image) {
      const img = h("img", "absolute inset-0 size-full object-cover transition-transform duration-700 ease-out-soft group-hover:scale-[1.04]");
      img.src = item.image;
      img.alt = "";
      img.loading = "lazy";
      img.draggable = false;
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => {
        img.remove();
        cover.classList.add("news-cover-fallback");
      });
      cover.append(img);
    } else {
      cover.classList.add("news-cover-fallback");
      cover.append(h("span", "absolute right-5 bottom-3 font-serif text-5xl leading-none text-brand/80 italic", names[item.ticker] || item.ticker));
    }
    cover.append(trendTag(item.trend, "absolute top-3 left-3 shadow-sm"));

    const body = h("div", "flex flex-1 flex-col gap-2.5 px-2.5 pt-4 pb-2");
    const chips = h("div", "flex flex-wrap gap-1.5");
    (item.tickers || [item.ticker]).slice(0, 3).forEach((t) => chips.append(h("span", "rounded-md border border-line bg-mist px-1.5 py-0.5 font-mono text-[0.66rem] text-ink/80", t)));
    body.append(chips, h("h3", "line-clamp-3 text-[1.05rem] leading-snug font-semibold tracking-[-0.01em] transition-colors group-hover:text-brand-deep", item.title));
    const meta = [item.source, timeAgo(item.published)].filter(Boolean).join(" · ") + (item.demo ? " · ejemplo" : "");
    body.append(h("p", "mt-auto truncate pt-1 font-mono text-[0.68rem] text-muted", meta));
    card.append(cover, body);
    li.append(card);
    return li;
  }

  // Comentarios ──
  const STANCES = {
    sube: { label: "▲ Sube", cls: "bg-up-soft text-up" },
    baja: { label: "▼ Baja", cls: "bg-brand-soft text-brand-deep" },
  };
  const AVATAR_COLORS = ["#c8102e", "#171717", "#0f8a5f", "#8f1025", "#4a4a4a", "#b25e09"];

  function commentSlide(item, names) {
    const li = h("li", "carousel-slide");
    const card = h("article", "spotlight flex h-full flex-col rounded-2xl border border-line bg-white p-6 transition-[border-color,box-shadow] duration-500");
    card.setAttribute("data-spotlight", "");
    const top = h("div", "flex items-center justify-between gap-3");
    const asset = h("span", "inline-flex min-w-0 items-center gap-2 rounded-full border border-line bg-mist px-2.5 py-1 font-mono text-[0.7rem] text-ink/80");
    asset.append(h("span", "font-semibold text-ink", item.ticker));
    if (names[item.ticker]) asset.append(h("span", "truncate text-muted", names[item.ticker]));
    top.append(asset);
    const stance = STANCES[item.stance];
    if (stance) top.append(h("span", "shrink-0 rounded-full px-2.5 py-1 font-mono text-[0.65rem] tracking-[0.12em] uppercase " + stance.cls, stance.label));

    const quote = h("blockquote", "relative mt-5 flex-1");
    quote.append(
      h("span", "pointer-events-none absolute -top-3 -left-1 font-serif text-5xl leading-none text-brand/25 select-none", "“"),
      h("p", "relative line-clamp-5 pl-5 text-[1.02rem] leading-relaxed text-ink", item.text),
    );
    if (item.tag) quote.append(h("span", "mt-3 ml-5 inline-flex rounded-md bg-mist px-2 py-0.5 text-xs text-muted", item.tag));

    const foot = h("div", "mt-6 flex items-center gap-3 border-t border-line pt-4");
    const avatar = h("span", "grid size-9 shrink-0 place-items-center rounded-full text-xs font-semibold text-white", item.initials || "M");
    let hash = 0;
    for (const ch of item.name || "") hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    avatar.style.background = AVATAR_COLORS[hash % AVATAR_COLORS.length];
    const who = h("div", "min-w-0");
    who.append(
      h("p", "truncate text-sm font-medium", item.name),
      h("p", "font-mono text-[0.68rem] text-muted", [timeAgo(item.created), item.demo ? "ejemplo" : ""].filter(Boolean).join(" · ")),
    );
    foot.append(avatar, who);
    card.append(top, quote, foot);
    li.append(card);
    return li;
  }

  const CAROUSEL_KINDS = { news: newsSlide, comments: commentSlide };
  const CAROUSEL_REFRESH_MS = 5 * 60 * 1000;

  function initCarousels() {
    document.querySelectorAll("[data-carousel]").forEach((root) => {
      const render = CAROUSEL_KINDS[root.dataset.carouselKind];
      if (!render) return;
      const carousel = createCarousel(root);
      const failed = root.querySelector("[data-carousel-failed]");
      const demo = document.querySelector('[data-carousel-demo="' + root.dataset.carouselKind + '"]');
      let names = {};
      try {
        names = JSON.parse(root.dataset.names || "{}");
      } catch (_) {}
      let signature = "";

      function load() {
        getJSON(root.dataset.src)
          .then((data) => {
            const items = (data.items || []).slice(0, 12);
            if (!items.length) throw new Error("vacío");
            const sig = JSON.stringify(items.map((i) => [i.id || i.text, i.created || i.published]));
            if (sig !== signature) {
              signature = sig;
              carousel.setSlides(items.map((item) => render(item, names)));
            }
            if (demo) demo.hidden = !data.demo;
            if (failed) failed.hidden = true;
          })
          .catch(() => {
            if (!signature) carousel.setSlides([]);
            if (failed) failed.hidden = false;
          });
      }
      load();
      setInterval(load, CAROUSEL_REFRESH_MS);
    });
  }

  // ───────────────────────── Barómetro Global de Mercado ─────────────────────────
  // Escala divergente: rojo (pérdida) → gris (≈0 %) → verde (ganancia), saturada en ±2 %.
  const DIVERGING = [
    [-2, [143, 16, 37]],
    [-1, [217, 86, 107]],
    [-0.25, [239, 195, 202]],
    [0, [230, 228, 223]],
    [0.25, [196, 229, 213]],
    [1, [79, 174, 135]],
    [2, [10, 92, 64]],
  ];

  function divergingColor(pct) {
    if (pct === null || pct === undefined) return "rgb(230 228 223)";
    const v = Math.max(-2, Math.min(2, pct));
    for (let i = 1; i < DIVERGING.length; i++) {
      const [x1, c1] = DIVERGING[i];
      if (v <= x1) {
        const [x0, c0] = DIVERGING[i - 1];
        const t = (v - x0) / (x1 - x0 || 1);
        return "rgb(" + c0.map((c, k) => Math.round(c + (c1[k] - c) * t)).join(" ") + ")";
      }
    }
    return "rgb(10 92 64)";
  }

  function initBarometer() {
    const root = document.querySelector("[data-barometer]");
    if (!root) return;
    const svg = root.querySelector("[data-world-map]");
    const stage = root.querySelector("[data-map-stage]");
    const status = root.querySelector("[data-map-status]");
    const tip = document.querySelector("[data-map-tip]");
    const groups = new Map(Array.from(svg.querySelectorAll("[data-region]")).map((g) => [g.dataset.region, g]));
    let data = {};

    // ── Datos (mismo ritmo que los precios: 15 s) ──
    poll(() =>
      getJSON(root.dataset.src)
        .then((res) => {
          data = {};
          res.regions.forEach((r) => {
            data[r.slug] = r;
            const g = groups.get(r.slug);
            if (g) g.style.setProperty("--region-fill", divergingColor(r.change_percent));
            const chip = root.querySelector('[data-region-chip="' + r.slug + '"] [data-region-value]');
            if (chip) {
              chip.textContent = fmtPercent(r.change_percent) + (r.fallback ? "*" : "");
              setTone(chip, TEXT_TONES, toneOf(r.change_percent));
            }
          });
          const estimated = res.regions.some((r) => r.fallback);
          status.textContent = "Actualizado " + new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) + (estimated ? " · * estimado" : "");
        })
        .catch(() => (status.textContent = "No pudimos actualizar los índices.")),
    );

    // ── Tooltip ──
    let hot = null;
    function setHot(slug) {
      const g = slug ? groups.get(slug) : null;
      if (g === hot) return;
      if (hot) hot.removeAttribute("data-hot");
      if (g) g.setAttribute("data-hot", "");
      hot = g;
    }

    function fillTip(r) {
      const head = h("div", "flex items-baseline justify-between gap-4");
      head.append(h("p", "font-semibold tracking-tight", r.name));
      const pct = h("p", "font-mono text-sm font-medium tabular-nums", fmtPercent(r.change_percent));
      setTone(pct, TEXT_TONES, toneOf(r.change_percent));
      head.append(pct);
      const nodes = [head];
      if (r.fallback) nodes.push(h("p", "mt-1 text-[0.7rem] text-muted", "Sin índice directo: promedio global estimado."));
      const list = h("ul", "mt-2 grid gap-1 border-t border-line pt-2");
      r.indices.forEach((i) => {
        const row = h("li", "flex justify-between gap-4 font-mono text-[0.7rem]");
        const v = h("span", "tabular-nums", fmtPercent(i.change_percent));
        setTone(v, TEXT_TONES, toneOf(i.change_percent));
        row.append(h("span", "text-ink/80", i.name), v);
        list.append(row);
      });
      if (r.indices.length) nodes.push(list);
      tip.replaceChildren(...nodes);
    }

    function showTip(slug, x, y) {
      const r = data[slug];
      setHot(slug);
      if (!r) return hideTip(false);
      fillTip(r);
      tip.hidden = false;
      const w = tip.offsetWidth;
      const hgt = tip.offsetHeight;
      const left = x + 18 + w > window.innerWidth - 8 ? x - w - 18 : x + 18;
      const top = Math.min(window.innerHeight - hgt - 8, Math.max(8, y - hgt / 2));
      tip.style.transform = "translate3d(" + Math.max(8, left) + "px," + top + "px,0)";
    }

    function hideTip(clearHot = true) {
      tip.hidden = true;
      if (clearHot) setHot(null);
    }

    svg.addEventListener("pointermove", (e) => {
      if (pan) return;
      const g = e.target.closest("[data-region]");
      g ? showTip(g.dataset.region, e.clientX, e.clientY) : hideTip();
    });
    svg.addEventListener("pointerleave", () => hideTip());
    svg.addEventListener("focusin", (e) => {
      const g = e.target.closest("[data-region]");
      if (!g) return;
      const b = g.getBoundingClientRect();
      showTip(g.dataset.region, b.left + b.width / 2, b.top + b.height / 2);
    });
    svg.addEventListener("focusout", () => hideTip());
    root.querySelectorAll("[data-region-chip]").forEach((chip) => {
      const on = () => {
        const b = chip.getBoundingClientRect();
        showTip(chip.dataset.regionChip, b.right - 10, b.top + b.height / 2);
      };
      chip.addEventListener("pointerenter", on);
      chip.addEventListener("focus", on);
      chip.addEventListener("pointerleave", () => hideTip());
      chip.addEventListener("blur", () => hideTip());
    });
    window.addEventListener("scroll", () => !tip.hidden && hideTip(), { passive: true });

    // ── Zoom (+ / − / reiniciar) y arrastre cuando hay zoom ──
    const [, , baseW, baseH] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
    const view = { k: 1, cx: baseW / 2, cy: baseH / 2 };
    let shown = { ...view };
    let anim = 0;
    let pan = null;

    function clampView(v) {
      const w = baseW / v.k;
      const hh = baseH / v.k;
      v.cx = Math.min(baseW - w / 2, Math.max(w / 2, v.cx));
      v.cy = Math.min(baseH - hh / 2, Math.max(hh / 2, v.cy));
      return v;
    }

    function apply(v) {
      const w = baseW / v.k;
      const hh = baseH / v.k;
      svg.setAttribute("viewBox", [v.cx - w / 2, v.cy - hh / 2, w, hh].map((n) => n.toFixed(2)).join(" "));
      stage.toggleAttribute("data-zoomed", v.k > 1.01);
    }

    function animateTo(target) {
      cancelAnimationFrame(anim);
      const from = { ...shown };
      const t0 = performance.now();
      const dur = reducedMotion() ? 1 : 420;
      const step = (t) => {
        const p = Math.min(1, (t - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        shown = { k: from.k + (target.k - from.k) * e, cx: from.cx + (target.cx - from.cx) * e, cy: from.cy + (target.cy - from.cy) * e };
        apply(shown);
        if (p < 1) anim = requestAnimationFrame(step);
      };
      anim = requestAnimationFrame(step);
    }

    root.querySelectorAll("[data-map-zoom]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const action = btn.dataset.mapZoom;
        if (action === "reset") Object.assign(view, { k: 1, cx: baseW / 2, cy: baseH / 2 });
        else view.k = Math.min(6, Math.max(1, view.k * (action === "in" ? 1.6 : 1 / 1.6)));
        animateTo(clampView(view));
      }),
    );

    stage.addEventListener("pointerdown", (e) => {
      if (view.k <= 1.01 || e.target.closest("button")) return;
      pan = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy, moved: false };
      stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener("pointermove", (e) => {
      if (!pan) return;
      const rect = svg.getBoundingClientRect();
      const scale = baseW / view.k / rect.width;
      if (Math.abs(e.clientX - pan.x) + Math.abs(e.clientY - pan.y) > 3) {
        pan.moved = true;
        stage.setAttribute("data-dragging", "");
        hideTip();
      }
      view.cx = pan.cx - (e.clientX - pan.x) * scale;
      view.cy = pan.cy - (e.clientY - pan.y) * scale;
      clampView(view);
      cancelAnimationFrame(anim);
      shown = { ...view };
      apply(shown);
    });
    const endPan = () => {
      pan = null;
      stage.removeAttribute("data-dragging");
    };
    stage.addEventListener("pointerup", endPan);
    stage.addEventListener("pointercancel", endPan);
  }

  // ───────────────────────── Spotlight y etiqueta del cursor ─────────────────────────
  /** Un solo listener: mueve el brillo de [data-spotlight] y la etiqueta de [data-cursor-label]. */
  function initPointerEffects() {
    const badge = document.querySelector("[data-cursor-badge]");
    if (!document.querySelector("[data-spotlight]") && !badge) return;
    let frame = 0;
    let last = null;

    function update() {
      frame = 0;
      const e = last;
      const card = e.target.closest && e.target.closest("[data-spotlight]");
      if (card) {
        const r = card.getBoundingClientRect();
        card.style.setProperty("--mx", e.clientX - r.left + "px");
        card.style.setProperty("--my", e.clientY - r.top + "px");
      }
      if (!badge) return;
      // Sobre una mini-gráfica manda su propio tooltip: la etiqueta se oculta.
      const target = e.pointerType === "mouse" && e.target.closest && !e.target.closest(".spark-hover") && e.target.closest("[data-cursor-label]");
      if (target) {
        if (badge.textContent !== target.dataset.cursorLabel) badge.textContent = target.dataset.cursorLabel;
        badge.style.transform = "translate3d(" + (e.clientX + 14) + "px," + (e.clientY - 38) + "px,0)";
        badge.setAttribute("data-on", "");
      } else {
        badge.removeAttribute("data-on");
      }
    }

    document.addEventListener(
      "pointermove",
      (e) => {
        last = e;
        if (!frame) frame = requestAnimationFrame(update);
      },
      { passive: true },
    );
    document.addEventListener("pointerleave", () => badge && badge.removeAttribute("data-on"));
    window.addEventListener("scroll", () => badge && badge.removeAttribute("data-on"), { passive: true });
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

  initReveal();
  initMobileNav();
  initWatchlistQuotes();
  initSparklines();
  initCarousels();
  initBarometer();
  initPointerEffects();
  initChartWorkspace();
  initReportBuilder();
})();
