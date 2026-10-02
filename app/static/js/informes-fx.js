/**
 * Fondos animados de la vista "Informes". Cada <canvas data-fx-scene> dibuja
 * una escena decorativa detrás de un contenedor:
 *   - charts: serie de precios en movimiento con velas y área.
 *   - stats:  histograma que se recalcula con su curva normal y puntos.
 *   - sports: pista de atletismo con corredores (la "carrera" del mercado).
 *
 * Si la capa tiene un <video>, el canvas (data-fx-fallback) solo se anima
 * cuando el navegador no puede reproducir ese video (p. ej. sin códec).
 *
 * Solo se anima lo que está en pantalla, se pausa con la pestaña oculta y,
 * con prefers-reduced-motion, los videos quedan en pausa y el canvas dibuja
 * un único fotograma estático.
 */
(function () {
  "use strict";

  const layers = document.querySelectorAll(".fx-layer");
  if (!layers.length) return;

  const COLORS = {
    accent: "200, 16, 46",
    up: "15, 138, 95",
    down: "217, 48, 37",
    grid: "124, 138, 158",
  };
  const rgba = (rgb, a) => `rgba(${rgb}, ${a})`;
  const rand = (min, max) => min + Math.random() * (max - min);

  // Aproximación de una normal estándar (Box-Muller).
  function gaussian() {
    const u = 1 - Math.random();
    const v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function drawGrid(ctx, w, h, stepX, stepY, offsetX) {
    ctx.strokeStyle = rgba(COLORS.grid, 0.12);
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = -(offsetX % stepX); x < w; x += stepX) {
      ctx.moveTo(x + 0.5, 0);
      ctx.lineTo(x + 0.5, h);
    }
    for (let y = stepY; y < h; y += stepY) {
      ctx.moveTo(0, y + 0.5);
      ctx.lineTo(w, y + 0.5);
    }
    ctx.stroke();
  }

  // --- Escena: gráfico de precios ---------------------------------------
  function chartsScene() {
    const STEP = 14; // px entre puntos
    const SPEED = 22; // px por segundo
    let points = [];
    let offset = 0;

    function nextValue(prev) {
      return Math.min(0.9, Math.max(0.1, prev + gaussian() * 0.045));
    }

    function ensure(w) {
      const needed = Math.ceil(w / STEP) + 3;
      if (!points.length) points.push({ v: 0.5, o: 0.5 });
      while (points.length < needed) {
        const prev = points[points.length - 1].v;
        points.push({ o: prev, v: nextValue(prev) });
      }
    }

    return function draw(ctx, w, h, dt) {
      ensure(w);
      offset += SPEED * dt;
      while (offset >= STEP) {
        offset -= STEP;
        points.shift();
        const prev = points[points.length - 1].v;
        points.push({ o: prev, v: nextValue(prev) });
      }

      drawGrid(ctx, w, h, STEP * 6, h / 4, offset);
      const y = (v) => h - v * h;

      // Velas tenues al fondo.
      points.forEach((p, i) => {
        const x = i * STEP - offset;
        const up = p.v >= p.o;
        const top = y(Math.max(p.o, p.v));
        const bodyH = Math.max(2, Math.abs(y(p.o) - y(p.v)));
        ctx.fillStyle = rgba(up ? COLORS.up : COLORS.down, 0.28);
        ctx.fillRect(x - 3, top, 6, bodyH);
        ctx.fillRect(x - 0.5, top - 6, 1, bodyH + 12);
      });

      // Área + línea de la serie.
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = i * STEP - offset;
        if (i === 0) ctx.moveTo(x, y(p.v));
        else ctx.lineTo(x, y(p.v));
      });
      ctx.strokeStyle = rgba(COLORS.accent, 0.95);
      ctx.lineWidth = 2;
      ctx.stroke();

      const lastX = (points.length - 1) * STEP - offset;
      ctx.lineTo(lastX, h);
      ctx.lineTo(-offset, h);
      ctx.closePath();
      const fill = ctx.createLinearGradient(0, 0, 0, h);
      fill.addColorStop(0, rgba(COLORS.accent, 0.35));
      fill.addColorStop(1, rgba(COLORS.accent, 0));
      ctx.fillStyle = fill;
      ctx.fill();
    };
  }

  // --- Escena: estadísticas ---------------------------------------------
  function statsScene() {
    const BINS = 28;
    const RESAMPLE_EVERY = 2.2; // segundos
    let heights = new Array(BINS).fill(0);
    let targets = sample();
    let elapsed = 0;
    let dots = [];

    function sample() {
      const counts = new Array(BINS).fill(0);
      const mean = rand(-0.4, 0.4);
      const sd = rand(0.8, 1.2);
      for (let i = 0; i < 400; i++) {
        const bin = Math.floor(((gaussian() * sd + mean + 3) / 6) * BINS);
        if (bin >= 0 && bin < BINS) counts[bin] += 1;
      }
      const max = Math.max(...counts) || 1;
      return counts.map((c) => c / max);
    }

    return function draw(ctx, w, h, dt) {
      elapsed += dt;
      if (elapsed > RESAMPLE_EVERY) {
        elapsed = 0;
        targets = sample();
      }
      heights = heights.map((v, i) => v + (targets[i] - v) * Math.min(1, dt * 3));

      drawGrid(ctx, w, h, w / 12, h / 3, 0);

      const barW = w / BINS;
      heights.forEach((v, i) => {
        const bh = v * h * 0.85;
        ctx.fillStyle = rgba(i % 7 === 3 ? COLORS.up : COLORS.accent, 0.45);
        ctx.fillRect(i * barW + 2, h - bh, barW - 4, bh);
      });

      // Curva suavizada sobre las barras.
      ctx.beginPath();
      heights.forEach((v, i) => {
        const x = i * barW + barW / 2;
        const yy = h - v * h * 0.85 - 4;
        if (i === 0) ctx.moveTo(x, yy);
        else ctx.lineTo(x, yy);
      });
      ctx.strokeStyle = rgba(COLORS.up, 0.9);
      ctx.lineWidth = 2;
      ctx.stroke();

      // Nube de puntos que asciende (dispersión).
      if (dots.length < 36 && Math.random() < dt * 12) {
        dots.push({ x: rand(0, w), y: h + 4, vy: rand(12, 30), r: rand(1.2, 2.6) });
      }
      dots = dots.filter((d) => (d.y -= d.vy * dt) > -4);
      ctx.fillStyle = rgba(COLORS.grid, 0.55);
      dots.forEach((d) => {
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fill();
      });
    };
  }

  // --- Escena: deportes (pista de atletismo) ----------------------------
  function sportsScene() {
    const LANES = 3;
    const runnerColors = [COLORS.accent, COLORS.up, COLORS.down, COLORS.grid];
    let runners = null;

    function reset(w) {
      runners = Array.from({ length: LANES }, (_, i) => ({
        x: rand(-w * 0.3, 0),
        speed: rand(w * 0.12, w * 0.22),
        color: runnerColors[i % runnerColors.length],
      }));
    }

    return function draw(ctx, w, h, dt) {
      if (!runners) reset(w);
      const laneH = h / LANES;

      // Carriles.
      ctx.strokeStyle = rgba(COLORS.grid, 0.3);
      ctx.lineWidth = 1;
      ctx.setLineDash([10, 8]);
      for (let i = 1; i < LANES; i++) {
        ctx.beginPath();
        ctx.moveTo(0, i * laneH + 0.5);
        ctx.lineTo(w, i * laneH + 0.5);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Meta a cuadros.
      const cell = Math.max(4, laneH / 3);
      const finishX = w - cell * 3;
      for (let yy = 0, row = 0; yy < h; yy += cell, row++) {
        for (let c = 0; c < 2; c++) {
          ctx.fillStyle = rgba("31, 41, 55", (row + c) % 2 ? 0.35 : 0.08);
          ctx.fillRect(finishX + c * cell, yy, cell, cell);
        }
      }

      // Corredores con estela; al cruzar la meta vuelven a la salida.
      runners.forEach((r, i) => {
        r.speed += gaussian() * w * 0.01 * dt;
        r.speed = Math.min(w * 0.3, Math.max(w * 0.08, r.speed));
        r.x += r.speed * dt;
        if (r.x > w + 20) {
          r.x = rand(-w * 0.25, -10);
          r.speed = rand(w * 0.12, w * 0.22);
        }
        const cy = i * laneH + laneH / 2;
        const trail = ctx.createLinearGradient(r.x - 70, 0, r.x, 0);
        trail.addColorStop(0, rgba(r.color, 0));
        trail.addColorStop(1, rgba(r.color, 0.6));
        ctx.fillStyle = trail;
        ctx.fillRect(r.x - 70, cy - 1.5, 70, 3);
        ctx.beginPath();
        ctx.arc(r.x, cy, Math.max(3, laneH * 0.18), 0, Math.PI * 2);
        ctx.fillStyle = rgba(r.color, 0.95);
        ctx.fill();
      });
    };
  }

  const SCENES = { charts: chartsScene, stats: statsScene, sports: sportsScene };
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const VIDEO_TIMEOUT_MS = 8000;

  const items = [];
  let running = false;
  let last = 0;

  function resize(item) {
    const rect = item.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    item.w = rect.width;
    item.h = rect.height;
    item.canvas.width = Math.max(1, Math.round(rect.width * dpr));
    item.canvas.height = Math.max(1, Math.round(rect.height * dpr));
    item.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // Fotograma estático: se avanza la escena unos segundos para que no quede vacía.
  function renderStatic(item) {
    for (let i = 0; i < 90; i++) {
      item.ctx.clearRect(0, 0, item.w, item.h);
      item.draw(item.ctx, item.w, item.h, 1 / 30);
    }
  }

  const resizeObserver = new ResizeObserver((entries) => {
    entries.forEach((entry) => {
      const item = items.find((it) => it.canvas === entry.target);
      if (!item) return;
      resize(item);
      if (reducedMotion) renderStatic(item);
    });
  });

  const visibilityObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      const item = items.find((it) => it.canvas === entry.target);
      if (item) item.visible = entry.isIntersecting;
    });
  });

  function frame(now) {
    // Con la pestaña oculta rAF se detiene; limitar dt evita saltos al volver.
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    items.forEach((item) => {
      if (!item.visible || !item.w || !item.h) return;
      item.ctx.clearRect(0, 0, item.w, item.h);
      item.draw(item.ctx, item.w, item.h, dt);
    });
    requestAnimationFrame(frame);
  }

  function startCanvas(canvas) {
    const factory = SCENES[canvas.dataset.fxScene];
    if (!factory || items.some((it) => it.canvas === canvas)) return;
    items.push({ canvas, ctx: canvas.getContext("2d"), draw: factory(), visible: true, w: 0, h: 0 });
    resizeObserver.observe(canvas);
    if (reducedMotion) return;
    visibilityObserver.observe(canvas);
    if (!running) {
      running = true;
      last = performance.now();
      requestAnimationFrame(frame);
    }
  }

  // Si el video no se puede reproducir, se quita y la capa vuelve al canvas.
  function watchVideo(layer, video, canvas) {
    let settled = false;
    const fallback = () => {
      if (settled) return;
      settled = true;
      video.remove();
      // Sin foto debajo, el canvas usa su overlay más ligero.
      if (!layer.querySelector(".fx-layer__image")) layer.classList.remove("fx-layer--photo");
      startCanvas(canvas);
    };
    const ok = () => {
      settled = true;
    };

    const sources = Array.from(video.querySelectorAll("source"));
    if (!sources.some((s) => video.canPlayType(s.type))) return fallback();

    // Los errores de carga se emiten en cada <source>; el último agota las opciones.
    if (sources.length) sources[sources.length - 1].addEventListener("error", fallback);
    video.addEventListener("error", fallback);
    if (video.readyState >= 2) ok();
    else video.addEventListener("loadeddata", ok, { once: true });
    setTimeout(() => video.readyState < 2 && fallback(), VIDEO_TIMEOUT_MS);

    if (reducedMotion) {
      // Sin movimiento: se deja el primer fotograma como imagen fija.
      video.removeAttribute("autoplay");
      video.pause();
    } else {
      // Algunos navegadores ignoran autoplay aunque el video esté silenciado.
      const played = video.play();
      if (played && played.catch) played.catch(() => {});
    }
  }

  layers.forEach((layer) => {
    const canvas = layer.querySelector("canvas[data-fx-scene]");
    const video = layer.querySelector("video");
    if (video && canvas) watchVideo(layer, video, canvas);
    else if (canvas) startCanvas(canvas);
  });
})();
