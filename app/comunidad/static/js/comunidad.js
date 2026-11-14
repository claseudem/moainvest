/**
 * ¿Qué piensas tú? (/app/que-piensas-tu/):
 * - Cuadrícula con todos los activos (tu lista primero) y su precio.
 * - Búsqueda local por ticker o nombre; si no hay coincidencias, busca en
 *   Yahoo Finance y añade los resultados a la cuadrícula para poder votarlos.
 * - ▲ Sube / ▼ Baja: registra o cambia el voto y muestra el consenso.
 *   Los recuentos se refrescan cada 30 s.
 */
(function () {
  "use strict";

  const page = document.getElementById("vote-page");
  if (!page) return;

  const $ = (id) => document.getElementById(id);
  const grid = $("vote-grid");
  const status = $("vote-status");
  const search = $("vote-q");
  const filters = $("vote-filters");
  const roundEl = $("vote-round");
  const POLL_MS = 30 * 1000;

  const state = { items: new Map(), cards: new Map(), category: "todos", query: "", extra: [], searchSeq: 0, ronda: null, available: true, syncing: false };
  const notice = $("vote-notice");
  const pct = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "always" });
  const price = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(name) {
    const holder = $("vote-icons").content.querySelector(`[data-icon="${name}"]`);
    return holder ? holder.firstElementChild.cloneNode(true) : el("span");
  }

  async function api(path, options) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json" }, credentials: "same-origin", ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `Error ${response.status}`);
      error.status = response.status;
      error.data = data; // p. ej. {codigo: "tabla_pendiente", ronda: "2026-W46"}
      throw error;
    }
    return data;
  }

  // ---------- votos guardados en el navegador ----------
  // Mientras la tabla de votos no exista en InsForge, cada voto se guarda aquí
  // ({ronda, votos: {TICKER: "up"|"down"}}) y se envía solo cuando exista.
  const LOCAL_KEY = "moai-votos-pendientes";

  function readLocalVotes(ronda) {
    try {
      const stored = JSON.parse(localStorage.getItem(LOCAL_KEY) || "null");
      return stored && stored.ronda === ronda ? stored.votos || {} : {};
    } catch (e) {
      return {};
    }
  }

  function writeLocalVotes(ronda, votos) {
    try {
      if (Object.keys(votos).length) localStorage.setItem(LOCAL_KEY, JSON.stringify({ ronda, votos }));
      else localStorage.removeItem(LOCAL_KEY);
      return true;
    } catch (e) {
      return false;
    }
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // ---------- tarjetas ----------
  function voteButton(kind, item) {
    const up = kind === "up";
    const btn = el("button", `btn ${up ? "btn--up" : "btn--down"}`);
    btn.type = "button";
    btn.setAttribute("aria-pressed", String(item.mi_voto === kind));
    btn.setAttribute("aria-label", `${item.ticker}: creo que ${up ? "sube" : "baja"}`);
    btn.appendChild(icon(up ? "up" : "down"));
    btn.append(up ? "▲ Sube" : "▼ Baja");
    btn.addEventListener("click", () => vote(item.ticker, kind));
    return btn;
  }

  function split(item) {
    const wrap = el("div", "vote-split");
    const bar = el("div", "vote-split__bar");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${item.pct_sube} % cree que sube y ${item.pct_baja} % cree que baja`);
    if (item.pct_sube > 0) {
      const upPart = el("span", "vote-split__up");
      upPart.style.width = `${item.pct_sube}%`;
      bar.appendChild(upPart);
    }
    if (item.pct_baja > 0) {
      const downPart = el("span", "vote-split__down");
      downPart.style.width = `${item.pct_baja}%`;
      bar.appendChild(downPart);
    }
    const legend = el("div", "vote-split__legend");
    legend.append(el("span", "is-up", `${item.pct_sube} % Sube`), el("span", "is-down", `${item.pct_baja} % Baja`));
    wrap.append(bar, legend);
    return wrap;
  }

  function card(item) {
    const node = el("article", "vote-card");
    node.dataset.ticker = item.ticker;
    node.setAttribute("aria-label", `${item.ticker}, ${item.nombre}`);
    if (state.extra.includes(item.ticker) && !item.en_lista) node.classList.add("is-searched");

    const head = el("div", "vote-card__head");
    const ticker = el("span", "vote-card__ticker", item.ticker);
    if (item.en_lista) ticker.appendChild(el("span", "vote-tag vote-tag--mine", "Tu lista"));
    else ticker.appendChild(el("span", "vote-tag", item.categoria_nombre));
    head.appendChild(ticker);

    const px = el("div", "vote-card__price");
    if (item.precio !== null && item.precio !== undefined) {
      px.appendChild(el("span", "vote-card__last", `${price.format(item.precio)}${item.moneda ? " " + item.moneda : ""}`));
    }
    if (item.variacion !== null && item.variacion !== undefined) {
      px.appendChild(el("span", `vote-card__change ${item.variacion >= 0 ? "is-up" : "is-down"}`, `${pct.format(item.variacion).replace("-", "−")} %`));
    }
    head.appendChild(px);
    head.appendChild(el("span", "vote-card__name", item.nombre));
    node.appendChild(head);

    const actions = el("div", "vote-card__actions");
    actions.append(voteButton("up", item), voteButton("down", item));
    node.appendChild(actions);

    if (item.mi_voto && item.total && !item.local) node.appendChild(split(item));
    const foot = item.local
      ? "Tu voto está guardado en este navegador. El consenso aparecerá cuando la votación esté conectada."
      : item.mi_voto
        ? `${plural(item.total, "voto")} esta semana · Puedes cambiar tu voto hasta que cierre la ronda.`
        : item.total
          ? `${plural(item.total, "voto")} esta semana. Vota para ver el consenso.`
          : "Nadie ha votado esta semana. Sé el primero.";
    node.appendChild(el("p", "vote-card__foot", foot));

    const msg = el("p", "vote-card__msg");
    msg.setAttribute("role", "status");
    msg.hidden = true;
    node.appendChild(msg);
    return node;
  }

  function upsert(item) {
    state.items.set(item.ticker, item);
    const fresh = card(item);
    const old = state.cards.get(item.ticker);
    if (old) old.replaceWith(fresh); else grid.appendChild(fresh);
    state.cards.set(item.ticker, fresh);
    return fresh;
  }

  // ---------- filtros ----------
  function matches(item) {
    const q = state.query.toLowerCase();
    const inCategory = state.category === "todos"
      || (state.category === "mis-activos" ? item.en_lista : item.categoria === state.category);
    const inQuery = !q || item.ticker.toLowerCase().includes(q) || item.nombre.toLowerCase().includes(q);
    return inCategory && inQuery;
  }

  function applyFilters() {
    let shown = 0;
    state.items.forEach((item, ticker) => {
      const visible = matches(item);
      state.cards.get(ticker).hidden = !visible;
      if (visible) shown += 1;
    });
    status.classList.remove("is-error");
    if (shown) {
      status.textContent = state.query || state.category !== "todos" ? `${plural(shown, "activo")}` : "";
    } else if (state.category === "mis-activos" && !state.query) {
      status.textContent = "Aún no tienes activos en tu lista. Agrégalos en Mis activos o vota cualquiera de «Todos».";
    } else if (state.query.length >= 2) {
      status.textContent = `Buscando «${state.query}» en Yahoo Finance…`;
    } else {
      status.textContent = "Ningún activo coincide con el filtro.";
    }
    return shown;
  }

  async function searchRemote(query) {
    const seq = ++state.searchSeq;
    try {
      const found = await api(`/api/favoritos/buscar?q=${encodeURIComponent(query)}`);
      if (seq !== state.searchSeq) return;
      const fresh = found.items.map((i) => i.ticker).filter((t) => !state.items.has(t)).slice(0, 3);
      if (!fresh.length) {
        if (!applyFilters()) status.textContent = `No encontramos «${query}». Prueba con el ticker o el nombre de la empresa.`;
        return;
      }
      state.extra = [...new Set([...state.extra, ...fresh])].slice(-5);
      await load();
      if (seq === state.searchSeq && !applyFilters()) status.textContent = `No encontramos «${query}».`;
    } catch (err) {
      if (seq === state.searchSeq) status.textContent = `No se pudo buscar en Yahoo Finance: ${err.message}`;
    }
  }

  let searchTimer = null;
  search.addEventListener("input", () => {
    state.query = search.value.trim();
    if (state.category !== "todos" && state.query) setCategory("todos", false);
    clearTimeout(searchTimer);
    const shown = applyFilters();
    if (!shown && state.query.length >= 2) searchTimer = setTimeout(() => searchRemote(state.query), 350);
  });

  function setCategory(category, apply = true) {
    state.category = category;
    filters.querySelectorAll(".vote-chip").forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.cat === category)));
    if (apply) applyFilters();
  }

  filters.addEventListener("click", (event) => {
    const chip = event.target.closest(".vote-chip");
    if (chip) setCategory(chip.dataset.cat);
  });

  // ---------- votar ----------
  async function vote(ticker, kind) {
    const node = state.cards.get(ticker);
    node.classList.add("is-busy");
    try {
      const data = await api("/api/comunidad/votos", { method: "POST", body: JSON.stringify({ ticker, voto: kind }) });
      const fresh = upsert(data.item);
      fresh.hidden = !matches(data.item);
      const msg = fresh.querySelector(".vote-card__msg");
      msg.textContent = { nuevo: "¡Gracias! Tu voto quedó registrado.", cambiado: "Cambiaste tu voto.", igual: "Ese ya era tu voto." }[data.resultado] || "";
      msg.hidden = !msg.textContent;
      fresh.querySelector(`.${kind === "up" ? "btn--up" : "btn--down"}`).focus();
    } catch (err) {
      if (err.data && err.data.codigo === "tabla_pendiente") {
        voteLocally(ticker, kind, err.data.ronda || state.ronda);
        return;
      }
      node.classList.remove("is-busy");
      const msg = node.querySelector(".vote-card__msg");
      msg.textContent = `No se registró el voto: ${err.message}`;
      msg.hidden = false;
    }
  }

  function voteLocally(ticker, kind, ronda) {
    const votos = readLocalVotes(ronda);
    const changed = votos[ticker] && votos[ticker] !== kind;
    const same = votos[ticker] === kind;
    votos[ticker] = kind;
    const stored = writeLocalVotes(ronda, votos);
    const item = { ...state.items.get(ticker), mi_voto: kind, local: true };
    const fresh = upsert(item);
    fresh.hidden = !matches(item);
    const msg = fresh.querySelector(".vote-card__msg");
    msg.textContent = !stored
      ? "No se pudo guardar: este navegador bloquea el almacenamiento local."
      : same ? "Ese ya era tu voto." : changed ? "Cambiaste tu voto (guardado en este navegador)." : "Voto guardado en este navegador.";
    msg.hidden = false;
    fresh.querySelector(`.${kind === "up" ? "btn--up" : "btn--down"}`).focus();
  }

  // Cuando la tabla ya existe, los votos guardados en el navegador se envían una vez.
  async function syncLocalVotes() {
    const votos = readLocalVotes(state.ronda);
    const pending = Object.entries(votos);
    if (!pending.length || state.syncing) return false;
    state.syncing = true;
    for (const [ticker, voto] of pending) {
      try {
        await api("/api/comunidad/votos", { method: "POST", body: JSON.stringify({ ticker, voto }) });
        delete votos[ticker];
      } catch (err) {
        if (err.status && err.status < 500) delete votos[ticker]; // voto inválido: se descarta
      }
    }
    writeLocalVotes(state.ronda, votos);
    state.syncing = false;
    status.textContent = `Se enviaron ${plural(pending.length - Object.keys(votos).length, "voto")} que tenías guardados en este navegador.`;
    return true;
  }

  // ---------- carga y refresco ----------
  function renderRound(data) {
    const closes = new Date(new Date(data.cierra).getTime() - 1);
    const week = Number((data.ronda || "").split("-W")[1]);
    roundEl.textContent = `Semana ${week} · cierra el ${closes.toLocaleDateString("es-ES", { weekday: "long", day: "2-digit", month: "2-digit" })}`;
    roundEl.hidden = false;
  }

  async function load() {
    const extra = state.extra.length ? `?extra=${encodeURIComponent(state.extra.join(","))}` : "";
    const data = await api(`/api/comunidad/activos${extra}`);
    renderRound(data);
    state.ronda = data.ronda;
    state.available = data.votos_disponibles !== false;
    notice.hidden = state.available;
    if (state.available && (await syncLocalVotes())) return load();
    const localVotes = state.available ? {} : readLocalVotes(data.ronda);
    data.items.forEach((original) => {
      // Sin tabla: la lista base con 0 votos y tus votos del navegador.
      const item = localVotes[original.ticker] ? { ...original, mi_voto: localVotes[original.ticker], local: true } : original;
      const old = state.cards.get(item.ticker);
      // No repintar la tarjeta que tiene el foco o un voto en curso.
      if (old && (old.classList.contains("is-busy") || old.contains(document.activeElement))) {
        state.items.set(item.ticker, item);
        return;
      }
      const fresh = upsert(item);
      fresh.hidden = !matches(item);
    });
    grid.setAttribute("aria-busy", "false");
  }

  load()
    .then(applyFilters)
    .catch((err) => {
      status.classList.add("is-error");
      status.textContent = `No se pudieron cargar los activos: ${err.message}`;
      grid.setAttribute("aria-busy", "false");
    });

  setInterval(() => {
    if (document.visibilityState === "visible") load().catch(() => {});
  }, POLL_MS);
})();
