/**
 * Mis activos (/app/favoritos/): autocompletado del campo "Agregar un activo"
 *    (combobox ARIA): populares
 *    al enfocar, filtro local instantáneo y búsqueda en Yahoo con debounce.
 *    Elegir una opción la agrega directamente a la lista.
 *
 * Las noticias y la votación viven en sus propias apps (/app/noticias/ y
 * /app/que-piensas-tu/). Los nombres que llegan de Yahoo se insertan con
 * textContent, nunca como HTML.
 */
(function () {
  "use strict";

  const page = document.getElementById("fav-page");
  if (!page) return;

  const API = "/api/favoritos";
  const $ = (id) => document.getElementById(id);
  const myTickers = new Set((page.dataset.tickers || "").split(",").filter(Boolean));

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  async function api(path, options) {
    const response = await fetch(API + path, { headers: { "Content-Type": "application/json" }, credentials: "same-origin", ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Error ${response.status}`);
    return { status: response.status, data };
  }

  const form = $("fav-add-form");
  const input = $("fav-ticker");
  const nameField = $("fav-nombre");
  const panel = $("fav-suggest-panel");
  const list = $("fav-suggest");
  const head = $("fav-suggest-head");
  const status = $("fav-suggest-status");

  const combo = { options: [], active: -1, popular: null, timer: null, seq: 0 };

  function highlight(text, query) {
    const frag = document.createDocumentFragment();
    const i = query ? text.toLowerCase().indexOf(query.toLowerCase()) : -1;
    if (i < 0) {
      frag.append(text);
      return frag;
    }
    frag.append(text.slice(0, i));
    frag.appendChild(el("mark", null, text.slice(i, i + query.length)));
    frag.append(text.slice(i + query.length));
    return frag;
  }

  function setOpen(open) {
    panel.hidden = !open;
    input.setAttribute("aria-expanded", String(open));
    if (!open) setActive(-1);
  }

  function setActive(index) {
    combo.active = index;
    list.querySelectorAll(".fav-option").forEach((li, i) => li.setAttribute("aria-selected", String(i === index)));
    const current = list.children[index];
    if (current && current.classList.contains("fav-option")) {
      input.setAttribute("aria-activedescendant", current.id);
      current.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function render(options, query, { title, loading, preselect } = {}) {
    combo.options = options.map((o) => ({ ...o, en_lista: o.en_lista || myTickers.has(o.ticker) }));
    head.textContent = title || (query ? `Resultados para «${query}»` : "Activos populares");
    list.replaceChildren();
    combo.options.forEach((option, i) => {
      const li = el("li", "fav-option");
      li.id = `fav-opt-${i}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      if (option.en_lista) li.setAttribute("aria-disabled", "true");
      const ticker = el("span", "fav-option__ticker");
      ticker.appendChild(highlight(option.ticker, query));
      const name = el("span", "fav-option__name");
      name.appendChild(highlight(option.nombre, query));
      const meta = el("span", "fav-option__meta");
      meta.appendChild(el("span", "fav-type", option.en_lista ? "En tu lista" : option.tipo));
      if (option.bolsa && !option.en_lista) meta.append(option.bolsa);
      li.append(ticker, name, meta);
      li.addEventListener("mousedown", (event) => event.preventDefault()); // conserva el foco
      li.addEventListener("click", () => choose(i));
      list.appendChild(li);
    });
    if (!combo.options.length) {
      list.appendChild(el("li", "fav-suggest__state", loading ? "Buscando en Yahoo Finance…" : `Sin resultados para «${query}». Prueba con el nombre de la empresa.`));
    } else if (loading) {
      list.appendChild(el("li", "fav-suggest__state", "Buscando más en Yahoo Finance…"));
    }
    const first = combo.options.findIndex((o) => !o.en_lista);
    setActive(preselect && first >= 0 ? first : -1);
    status.textContent = loading ? "" : `${combo.options.length} sugerencias disponibles.`;
    setOpen(true);
  }

  function localMatches(query) {
    const q = query.toLowerCase();
    return (combo.popular || []).filter((o) => o.ticker.toLowerCase().includes(q) || o.nombre.toLowerCase().includes(q));
  }

  async function loadPopular() {
    if (combo.popular) return combo.popular;
    try {
      combo.popular = (await api("/buscar?q=")).data.items;
    } catch (err) {
      combo.popular = [];
    }
    return combo.popular;
  }

  function choose(index) {
    const option = combo.options[index];
    if (!option || option.en_lista) return;
    input.value = option.ticker;
    nameField.value = option.nombre;
    setOpen(false);
    status.textContent = `Agregando ${option.ticker}, ${option.nombre}.`;
    form.requestSubmit ? form.requestSubmit() : form.submit();
  }

  input.addEventListener("focus", async () => {
    if (input.value.trim()) return;
    render(await loadPopular(), "", { title: "Activos populares" });
  });

  input.addEventListener("input", () => {
    nameField.value = ""; // el nombre solo vale si se eligió de la lista
    const query = input.value.trim();
    clearTimeout(combo.timer);
    if (!query) {
      render(combo.popular || [], "");
      return;
    }
    // Primero lo local (instantáneo); luego Yahoo, que busca también por nombre y corrige erratas.
    render(localMatches(query), query, { loading: true, preselect: true });
    const seq = ++combo.seq;
    combo.timer = setTimeout(async () => {
      try {
        const { data } = await api(`/buscar?q=${encodeURIComponent(query)}`);
        if (seq === combo.seq) render(data.items, query, { preselect: true });
      } catch (err) {
        if (seq === combo.seq) render(localMatches(query), query, { title: "Sin conexión con Yahoo Finance · sugerencias locales", preselect: true });
      }
    }, 250);
  });

  input.addEventListener("keydown", (event) => {
    const open = !panel.hidden;
    const enabled = combo.options.map((o, i) => (o.en_lista ? -1 : i)).filter((i) => i >= 0);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        input.dispatchEvent(new Event(input.value.trim() ? "input" : "focus"));
        return;
      }
      if (!enabled.length) return;
      const pos = enabled.indexOf(combo.active);
      const next = event.key === "ArrowDown" ? enabled[(pos + 1) % enabled.length] : enabled[(pos - 1 + enabled.length) % enabled.length];
      setActive(next);
    } else if (event.key === "Enter" && open && combo.active >= 0) {
      event.preventDefault();
      choose(combo.active);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  });

  input.addEventListener("blur", () => setTimeout(() => setOpen(false), 120));
  loadPopular(); // precarga: el primer foco ya muestra la lista
})();
