/**
 * Noticias (/app/noticias/):
 * - Suscripción a alertas: se guarda sola en cada cambio (PUT /api/noticias/suscripcion).
 * - Feed con filtros rápidos (Todos, Mis activos, Tecnología, Cripto...).
 * Los titulares se insertan siempre con textContent, nunca como HTML.
 */
(function () {
  "use strict";

  const page = document.getElementById("news-page");
  if (!page) return;

  const $ = (id) => document.getElementById(id);
  const SENTIMENT = { alcista: "Alcista", bajista: "Bajista", neutral: "Neutral" };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  async function api(path, options) {
    const response = await fetch(`/api/noticias${path}`, { headers: { "Content-Type": "application/json" }, credentials: "same-origin", ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `Error ${response.status}`);
      error.status = response.status;
      error.data = data; // p. ej. {codigo: "tabla_pendiente", suscripcion: {...}}
      throw error;
    }
    return data;
  }

  // Mientras la tabla de suscripciones no exista en InsForge, la suscripción
  // vive en este navegador; en cuanto exista, se sube sola (ver loadSubscription).
  const LOCAL_KEY = "moai-suscripcion-noticias";

  function readLocal() {
    try {
      return JSON.parse(localStorage.getItem(LOCAL_KEY) || "null");
    } catch (e) {
      return null;
    }
  }

  function writeLocal(sub) {
    try {
      if (sub) localStorage.setItem(LOCAL_KEY, JSON.stringify(sub));
      else localStorage.removeItem(LOCAL_KEY);
      return true;
    } catch (e) {
      return false;
    }
  }

  function ago(epochSeconds) {
    const minutes = Math.round((Date.now() / 1000 - epochSeconds) / 60);
    if (minutes < 1) return "ahora";
    if (minutes < 60) return `hace ${minutes} min`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `hace ${hours} h`;
    const days = Math.round(hours / 24);
    return days === 1 ? "ayer" : `hace ${days} días`;
  }

  // =====================================================================
  // Suscripción
  // =====================================================================
  const form = $("news-sub-form");
  const toggle = $("sub-activa");
  const body = $("news-sub-body");
  const viaApp = $("sub-via-app");
  const viaEmail = $("sub-via-email");
  const emailRow = $("sub-email-row");
  const email = $("sub-email");
  const emailHint = $("sub-email-hint");
  const state = $("news-sub-state");
  const status = $("news-sub-status");
  const notice = $("news-sub-notice");
  let accountEmail = email.value;
  let localMode = false;
  let saved = null;
  let saveTimer = null;

  function describe(sub) {
    if (!sub.activa) return "Desactivadas. Actívalas para enterarte de lo que mueve tus activos.";
    const ways = [sub.via_app && "la campana", sub.via_email && `el correo (${sub.email})`].filter(Boolean).join(" y ");
    return `Activas en ${ways} · ${sub.alcance === "todos" ? "todos los activos" : "solo tus favoritos"}.`;
  }

  function setLocalMode(on) {
    localMode = on;
    notice.hidden = !on;
  }

  function fill(sub) {
    saved = sub;
    toggle.checked = sub.activa;
    viaApp.checked = sub.via_app;
    viaEmail.checked = sub.via_email;
    email.value = sub.email || accountEmail || "";
    form.querySelector(`input[name="alcance"][value="${sub.alcance}"]`).checked = true;
    syncUi();
  }

  function syncUi() {
    body.disabled = !toggle.checked;
    emailRow.hidden = !viaEmail.checked;
    emailHint.textContent = email.value && email.value === accountEmail
      ? "Es el correo de tu cuenta; puedes cambiarlo. Te enviamos un resumen con los titulares nuevos."
      : "Te enviamos un resumen con los titulares nuevos.";
    state.textContent = saved
      ? describe(saved) + (localMode && saved.activa ? " Empezarán a llegar cuando la base de datos esté lista." : "")
      : "";
    state.classList.toggle("is-on", Boolean(saved && saved.activa));
  }

  function payload() {
    return {
      activa: toggle.checked,
      via_app: viaApp.checked,
      via_email: viaEmail.checked,
      email: email.value.trim(),
      alcance: form.querySelector('input[name="alcance"]:checked').value,
    };
  }

  async function save() {
    status.classList.remove("is-error");
    status.textContent = "Guardando…";
    try {
      // El servidor valida siempre, aunque la tabla aún no exista.
      const sub = await api("/suscripcion", { method: "PUT", body: JSON.stringify(payload()) });
      writeLocal(null);
      setLocalMode(false);
      fill(sub);
      status.textContent = "Cambios guardados.";
    } catch (err) {
      if (err.data && err.data.codigo === "tabla_pendiente" && err.data.suscripcion) {
        const sub = err.data.suscripcion;
        setLocalMode(true);
        fill(sub);
        status.textContent = writeLocal(sub)
          ? "Guardado en este navegador."
          : "No se pudo guardar: este navegador bloquea el almacenamiento local.";
        return;
      }
      status.classList.add("is-error");
      status.textContent = err.message;
    }
  }

  function scheduleSave(delay) {
    // Activar sin vías marcadas: se propone la campana en vez de mostrar un error.
    if (toggle.checked && !viaApp.checked && !viaEmail.checked) viaApp.checked = true;
    syncUi();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, delay);
  }

  form.addEventListener("change", (event) => scheduleSave(event.target === email ? 0 : 150));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    scheduleSave(0);
  });

  async function loadSubscription() {
    try {
      const sub = await api("/suscripcion");
      accountEmail = sub.email_cuenta || accountEmail;
      toggle.disabled = false;
      const local = readLocal();
      if (sub.almacenamiento === "local") {
        // Tabla pendiente: lo guardado en este navegador o los valores por defecto.
        setLocalMode(true);
        fill(local ? { ...sub, ...local } : sub);
        return;
      }
      setLocalMode(false);
      fill(sub);
      if (local && !sub.guardada) {
        // La tabla ya existe y no hay nada en el servidor: se sube lo del navegador.
        status.textContent = "Sincronizando tu suscripción…";
        const synced = await api("/suscripcion", { method: "PUT", body: JSON.stringify(local) });
        writeLocal(null);
        fill(synced);
        status.textContent = "Tu suscripción se guardó en tu cuenta.";
      } else if (local) {
        writeLocal(null); // el servidor manda
      }
    } catch (err) {
      state.textContent = `No se pudo cargar tu suscripción: ${err.message}`;
    }
  }

  loadSubscription();

  // =====================================================================
  // Feed
  // =====================================================================
  const feedCard = $("news-feed");
  const list = $("news-list");
  const empty = $("news-empty");
  const filters = $("news-filters");
  let current = "todos";
  let seq = 0;

  function placeholder(item) {
    // Marcador limpio cuando la noticia no trae portada o no carga.
    const ph = el("span", "news-item__ph");
    const holder = $("news-icons").content.querySelector('[data-icon="news"]');
    if (holder) ph.appendChild(holder.firstElementChild.cloneNode(true));
    const first = (item.activos || [])[0];
    if (first) ph.appendChild(el("span", "news-item__ph-ticker", first.ticker));
    return ph;
  }

  function media(item, href) {
    const box = el(href ? "a" : "span", "news-item__media");
    if (href) {
      box.href = href;
      box.target = "_blank";
      box.rel = "noopener noreferrer";
      box.tabIndex = -1; // el titular ya es el enlace accesible
    }
    box.setAttribute("aria-hidden", "true");
    if (item.imagen && item.imagen.src) {
      const img = el("img", "news-item__img");
      img.src = item.imagen.src;
      img.srcset = item.imagen.srcset;
      img.sizes = "(max-width: 640px) calc(100vw - 4rem), 11rem";
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.width = 360;
      img.height = 240;
      img.addEventListener("error", () => img.replaceWith(placeholder(item)), { once: true });
      box.appendChild(img);
    } else {
      box.appendChild(placeholder(item));
    }
    return box;
  }

  function row(item) {
    const href = item.url && /^https?:\/\//.test(item.url) ? item.url : null;
    const li = el("li", "news-item");
    li.appendChild(media(item, href));

    const body = el("div", "news-item__body");
    const top = el("div", "news-item__top");
    const tickers = el("div", "news-item__tickers");
    (item.activos || []).slice(0, 4).forEach((a) => {
      const badge = el("span", "news-ticker", a.ticker);
      badge.title = a.nombre;
      tickers.appendChild(badge);
    });
    top.appendChild(tickers);
    top.appendChild(el("span", `news-sentiment news-sentiment--${item.sentimiento}`, SENTIMENT[item.sentimiento] || "Neutral"));
    body.appendChild(top);

    const title = el("p", "news-item__title");
    if (href) {
      const link = el("a", null, item.title);
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      title.appendChild(link);
    } else {
      title.textContent = item.title;
    }
    body.appendChild(title);

    const when = new Date(item.published_at * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    body.appendChild(el("p", "news-item__meta", [item.publisher, `${ago(item.published_at)} · ${when}`].filter(Boolean).join(" · ")));
    li.appendChild(body);
    return li;
  }

  function showEmpty(text, withLink) {
    empty.hidden = false;
    empty.replaceChildren(text);
    if (withLink) {
      const link = el("a", null, "Agrega activos en Mis activos");
      link.href = "/app/favoritos/";
      empty.append(" ", link, ".");
    }
  }

  async function load(filter) {
    current = filter;
    const mine = ++seq;
    filters.querySelectorAll(".news-chip").forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.filter === filter)));
    feedCard.setAttribute("aria-busy", "true");
    list.replaceChildren();
    showEmpty("Cargando titulares…");
    try {
      const data = await api(`?filtro=${encodeURIComponent(filter)}`);
      if (mine !== seq) return;
      list.replaceChildren(...data.items.map(row));
      if (data.items.length) {
        empty.hidden = true;
      } else if (filter === "mis-activos" && !data.mis_activos.length) {
        showEmpty("Aún no tienes activos guardados.", true);
      } else {
        showEmpty("No hay titulares recientes para este filtro.");
      }
    } catch (err) {
      if (mine === seq) showEmpty(`No se pudieron cargar las noticias: ${err.message}`);
    } finally {
      if (mine === seq) feedCard.setAttribute("aria-busy", "false");
    }
  }

  filters.addEventListener("click", (event) => {
    const chip = event.target.closest(".news-chip");
    if (chip && chip.dataset.filter !== current) load(chip.dataset.filter);
  });

  load("todos");
})();
