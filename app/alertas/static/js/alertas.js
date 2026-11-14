/**
 * Campana de notificaciones (core/base.html) y botones de alertas por
 * watchlist (si una página los incluye con ``data-alert-watchlist``).
 *
 * - Pide /api/alertas al cargar y cada POLL_MS mientras la pestaña está
 *   visible; el servidor evalúa los movimientos y guarda las alertas nuevas.
 * - "Noticias" depende de la suscripción de /app/noticias/ (vía «campana»);
 *   los titulares nuevos desde la última visita suman al contador.
 * - Los textos externos (titulares, fuentes) se insertan siempre con
 *   textContent: nunca como HTML.
 */
(function () {
  "use strict";

  const root = document.getElementById("notif");
  if (!root) return; // sin sesión no hay campana

  const POLL_MS = 3 * 60 * 1000;
  const API = "/api/alertas";

  const $ = (id) => document.getElementById(id);
  const bell = $("notif-btn");
  const badge = $("notif-badge");
  const panel = $("notif-panel");
  const tabs = [$("notif-tab-mov"), $("notif-tab-news")];
  const panes = { "notif-tab-mov": $("notif-pane-mov"), "notif-tab-news": $("notif-pane-news") };
  const listMov = $("notif-list-mov");
  const emptyMov = $("notif-empty-mov");
  const listNews = $("notif-list-news");
  const emptyNews = $("notif-empty-news");
  const tabCount = $("notif-count");
  const summary = $("notif-summary");
  const dialog = $("notif-settings");
  const form = $("notif-settings-form");
  const formError = $("notif-settings-error");
  const saveBtn = $("notif-settings-save");
  const iconTpl = $("notif-icons");

  const state = { items: [], prefs: null, news: [], newsSubscribed: null, newsSeen: readSeen(), newsLoading: false };
  const newsCount = $("notif-news-count");

  const pct = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "always" });
  const num = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

  // ---------- utilidades ----------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(name) {
    const holder = iconTpl.content.querySelector(`[data-icon="${name}"]`);
    return holder ? holder.firstElementChild.cloneNode(true) : el("span");
  }

  function formatPct(value) {
    return `${pct.format(value).replace("-", "−")} %`;
  }

  function ago(dateLike) {
    const then = new Date(dateLike).getTime();
    if (Number.isNaN(then)) return "";
    const minutes = Math.round((Date.now() - then) / 60000);
    if (minutes < 1) return "ahora";
    if (minutes < 60) return `hace ${minutes} min`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `hace ${hours} h`;
    const days = Math.round(hours / 24);
    return days === 1 ? "ayer" : `hace ${days} días`;
  }

  function isToday(dateLike) {
    const d = new Date(dateLike);
    const now = new Date();
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  }

  function watchlistNames(slugs) {
    const all = (state.prefs && state.prefs.watchlists) || [];
    return (slugs || []).map((slug) => (all.find((w) => w.slug === slug) || { nombre: slug }).nombre);
  }

  async function api(path, options) {
    const response = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Error ${response.status}`);
    return data;
  }

  // ---------- campana y contador ----------
  // Titulares "nuevos" = publicados después de la última vez que se abrió la
  // pestaña Noticias (se recuerda en este navegador).
  function readSeen() {
    try {
      return Number(localStorage.getItem("moai-news-seen")) || Date.now() / 1000 - 6 * 3600;
    } catch (e) {
      return Date.now() / 1000 - 6 * 3600;
    }
  }

  function newsUnread() {
    return state.news.filter((item) => item.published_at > state.newsSeen).length;
  }

  function markNewsSeen() {
    if (!state.news.length) return;
    state.newsSeen = Math.max(state.newsSeen, ...state.news.map((item) => item.published_at));
    try {
      localStorage.setItem("moai-news-seen", String(state.newsSeen));
    } catch (e) {
      /* sin almacenamiento: se vuelve a contar en la próxima visita */
    }
    renderBadge();
  }

  function unreadCount() {
    return state.items.filter((item) => !item.leida).length;
  }

  function renderBadge() {
    const alerts = unreadCount();
    const fresh = newsUnread();
    const count = alerts + fresh;
    const previous = Number(badge.dataset.count || 0);
    badge.hidden = count === 0;
    badge.textContent = count > 9 ? "9+" : String(count);
    badge.dataset.count = String(count);
    tabCount.hidden = alerts === 0;
    tabCount.textContent = String(alerts);
    newsCount.hidden = fresh === 0;
    newsCount.textContent = String(fresh);
    bell.setAttribute("aria-label", count ? `Notificaciones: ${count} sin leer` : "Notificaciones");
    if (count > previous) {
      bell.classList.remove("has-unread");
      void bell.offsetWidth; // reinicia la animación
      bell.classList.add("has-unread");
    }
  }

  function renderSummary() {
    if (!state.prefs) return;
    const muted = state.prefs.silenciadas.length;
    summary.textContent = `Umbral ±${state.prefs.umbral} %` + (muted ? ` · ${muted} watchlist${muted > 1 ? "s" : ""} silenciada${muted > 1 ? "s" : ""}` : "");
  }

  // ---------- pestaña Movimientos ----------
  function alertItem(item) {
    const dir = item.direccion === "up" ? "up" : "down";
    const li = el("li", `alert-item alert-item--${dir}${item.leida ? "" : " is-unread"}`);
    li.dataset.id = item.id;

    const badgeIcon = el("span", "alert-item__icon");
    badgeIcon.appendChild(icon(dir));
    li.appendChild(badgeIcon);

    const body = el("div", "alert-item__body");
    const title = el("p", "alert-item__title");
    title.appendChild(el("strong", null, item.nombre || item.ticker));
    title.append(` ${dir === "up" ? "subió" : "cayó"} `);
    title.appendChild(el("span", "alert-item__pct", formatPct(Number(item.variacion))));
    title.append(isToday(item.created_at) ? " hoy" : ` el ${new Date(item.created_at).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit" })}`);
    body.appendChild(title);

    const ctx = el("p", item.noticia_titulo ? "alert-item__ctx" : "alert-item__ctx alert-item__ctx--none");
    ctx.appendChild(el("span", "alert-item__label", "Contexto"));
    if (item.noticia_titulo) {
      if (item.noticia_url && /^https?:\/\//.test(item.noticia_url)) {
        const link = el("a", null, item.noticia_titulo);
        link.href = item.noticia_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        ctx.appendChild(link);
      } else {
        ctx.append(item.noticia_titulo);
      }
      const source = [item.noticia_fuente, item.noticia_fecha ? ago(item.noticia_fecha) : null].filter(Boolean).join(" · ");
      if (source) ctx.append(` · ${source}`);
    } else {
      ctx.append("Sin titulares relevantes en las últimas 48 h.");
    }
    body.appendChild(ctx);

    const meta = el("p", "alert-item__meta");
    meta.appendChild(el("span", `alert-tag alert-tag--${dir}`, `${dir === "up" ? "Alza" : "Baja"} ≥ ${item.nivel * item.umbral} %`));
    if (item.nivel > 1) meta.appendChild(el("span", "alert-tag alert-tag--level", `Se intensifica · ${item.nivel}× umbral`));
    meta.appendChild(el("span", "alert-item__ticker", item.ticker));
    const extra = [];
    if (item.precio !== null && item.precio !== undefined) extra.push(`${num.format(item.precio)}${item.moneda ? " " + item.moneda : ""}`);
    const lists = watchlistNames(item.watchlists);
    if (lists.length) extra.push(lists.join(", "));
    extra.push(ago(item.created_at));
    meta.append(extra.filter(Boolean).join(" · "));
    body.appendChild(meta);

    li.appendChild(body);
    return li;
  }

  function renderMovements(errorText) {
    listMov.replaceChildren(...state.items.map(alertItem));
    emptyMov.hidden = state.items.length > 0;
    if (!state.items.length) {
      emptyMov.textContent = errorText
        ? `No se pudieron cargar las alertas: ${errorText}`
        : `Sin movimientos de ±${state.prefs ? state.prefs.umbral : 5} % o más en tus watchlists. Te avisaremos aquí.`;
    }
    renderBadge();
  }

  async function markRead(ids) {
    const targets = state.items.filter((item) => !item.leida && (!ids || ids.includes(item.id)));
    if (!targets.length) return;
    targets.forEach((item) => { item.leida = true; });
    renderMovements();
    try {
      await api("/leidas", { method: "POST", body: JSON.stringify(ids ? { ids } : {}) });
    } catch (err) {
      targets.forEach((item) => { item.leida = false; });
      renderMovements();
    }
  }

  listMov.addEventListener("click", (event) => {
    const li = event.target.closest(".alert-item");
    if (li && li.classList.contains("is-unread")) markRead([li.dataset.id]);
  });
  $("notif-read-all").addEventListener("click", () => markRead(null));

  // ---------- pestaña Noticias ----------
  function newsItem(item) {
    const li = el("li", "news-item");
    const ic = el("span", "alert-item__icon");
    ic.appendChild(icon("news"));
    li.appendChild(ic);

    const body = el("div", "alert-item__body");
    const title = el("p", "news-item__title");
    if (item.url && /^https?:\/\//.test(item.url)) {
      const link = el("a", null, item.title);
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      title.appendChild(link);
    } else {
      title.textContent = item.title;
    }
    body.appendChild(title);

    const meta = el("p", "alert-item__meta");
    (item.activos || []).slice(0, 3).forEach((asset) => {
      const change = asset.variacion;
      const dir = change === null || change === undefined ? null : change >= 0 ? "up" : "down";
      const tag = el("span", dir ? `alert-tag alert-tag--${dir}` : "alert-tag", dir ? `${asset.nombre} ${formatPct(change)}` : asset.nombre);
      meta.appendChild(tag);
    });
    meta.append([item.publisher, ago(item.published_at * 1000)].filter(Boolean).join(" · "));
    body.appendChild(meta);
    li.appendChild(body);
    return li;
  }

  function renderNewsList() {
    listNews.replaceChildren(...state.news.map(newsItem));
    emptyNews.hidden = state.news.length > 0 && state.newsSubscribed;
    if (state.newsSubscribed === false) {
      listNews.replaceChildren();
      emptyNews.hidden = false;
      emptyNews.replaceChildren("Activa las alertas de noticias para verlas aquí. ");
      const link = el("a", "notif-link", "Ir a Noticias");
      link.href = "/app/noticias/";
      emptyNews.appendChild(link);
    } else if (!state.news.length) {
      emptyNews.textContent = "No hay titulares recientes de tus activos.";
    }
  }

  // ``quiet``: refresco en segundo plano (no pisa el mensaje de carga).
  async function loadNews(quiet) {
    if (state.newsLoading) return;
    state.newsLoading = true;
    if (!quiet && !state.news.length) {
      emptyNews.hidden = false;
      emptyNews.textContent = "Cargando titulares…";
    }
    try {
      const data = await api("/noticias");
      state.newsSubscribed = data.suscrito !== false;
      state.news = data.items || [];
      renderNewsList();
      renderBadge();
      if (tabs[1].getAttribute("aria-selected") === "true" && !panel.hidden) markNewsSeen();
    } catch (err) {
      if (!quiet) emptyNews.textContent = `No se pudieron cargar las noticias: ${err.message}`;
    } finally {
      state.newsLoading = false;
    }
  }

  // ---------- pestañas (patrón ARIA tabs) ----------
  function selectTab(tab, focus) {
    tabs.forEach((t) => {
      const selected = t === tab;
      t.setAttribute("aria-selected", String(selected));
      t.tabIndex = selected ? 0 : -1;
      panes[t.id].hidden = !selected;
    });
    if (focus) tab.focus();
    if (tab.id === "notif-tab-news") {
      if (state.newsSubscribed === null) loadNews(); else markNewsSeen();
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      selectTab(tabs[(index + step + tabs.length) % tabs.length], true);
    });
  });

  // ---------- abrir / cerrar el panel ----------
  function setOpen(open) {
    panel.hidden = !open;
    bell.setAttribute("aria-expanded", String(open));
    if (open) {
      bell.classList.remove("has-unread");
      const selected = tabs.find((t) => t.getAttribute("aria-selected") === "true");
      selected.focus();
      if (selected === tabs[1]) markNewsSeen();
    }
  }

  bell.addEventListener("click", () => setOpen(panel.hidden));
  document.addEventListener("click", (event) => {
    if (!panel.hidden && !root.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden && !dialog.open) {
      setOpen(false);
      bell.focus();
    }
  });

  // ---------- preferencias: diálogo y botones del paso 01 ----------
  function applyPrefs(prefs) {
    state.prefs = prefs;
    renderSummary();
    document.querySelectorAll("[data-alert-watchlist]").forEach((btn) => {
      const on = !prefs.silenciadas.includes(btn.dataset.alertWatchlist);
      const name = btn.getAttribute("aria-label").replace(/^Alertas de /, "");
      btn.setAttribute("aria-pressed", String(on));
      btn.title = `Alertas de ${name}: ${on ? "activadas" : "silenciadas"}`;
    });
  }

  async function savePrefs(changes) {
    const prefs = await api("/preferencias", { method: "PUT", body: JSON.stringify(changes) });
    applyPrefs(prefs);
    return prefs;
  }

  function openSettings() {
    if (!state.prefs) return;
    formError.hidden = true;
    form.querySelectorAll('input[name="umbral"]').forEach((input) => {
      input.checked = Number(input.value) === state.prefs.umbral;
    });
    form.querySelectorAll('input[name="activas"]').forEach((input) => {
      input.checked = !state.prefs.silenciadas.includes(input.value);
    });
    setOpen(false);
    dialog.showModal();
  }

  root.querySelectorAll("#notif-open-settings, [data-open-settings]").forEach((btn) => btn.addEventListener("click", openSettings));
  $("notif-settings-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => bell.focus());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const umbral = Number(form.querySelector('input[name="umbral"]:checked').value);
    const silenciadas = Array.from(form.querySelectorAll('input[name="activas"]'))
      .filter((input) => !input.checked)
      .map((input) => input.value);
    saveBtn.disabled = true;
    saveBtn.textContent = "Guardando…";
    try {
      await savePrefs({ umbral, silenciadas });
      dialog.close();
      refresh();
    } catch (err) {
      formError.textContent = `No se guardaron los cambios: ${err.message}`;
      formError.hidden = false;
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = "Guardar";
    }
  });

  document.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-alert-watchlist]");
    if (!btn || !state.prefs) return;
    const slug = btn.dataset.alertWatchlist;
    const muted = new Set(state.prefs.silenciadas);
    if (muted.has(slug)) muted.delete(slug); else muted.add(slug);
    btn.classList.add("is-saving");
    try {
      await savePrefs({ silenciadas: Array.from(muted) });
      refresh();
    } catch (err) {
      btn.title = `No se pudo cambiar: ${err.message}`;
    } finally {
      btn.classList.remove("is-saving");
    }
  });

  // ---------- carga y sondeo ----------
  let timer = null;

  async function refresh() {
    try {
      const data = await api("");
      state.items = data.items || [];
      applyPrefs(data.preferencias);
      renderMovements();
    } catch (err) {
      if (!state.items.length) renderMovements(err.message);
    }
    loadNews(true); // titulares nuevos también suman al contador de la campana
  }

  function schedule() {
    clearInterval(timer);
    timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, POLL_MS);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });

  refresh();
  schedule();
})();
