/* COMUNIDAD: noticias de activos, votación "Sube" / "Baja" con ranking y notas.
 *
 * Los activos llegan en #comunidad-data (JSON). Las noticias se piden a
 * /api/comunidad/noticias y se filtran aquí por ticker. Votos y notas viven en
 * InsForge (/api/comunidad/votos y /notas); si el servidor no los puede guardar
 * (sin sesión o sin base de datos) se guardan en localStorage y la página lo
 * indica. Los textos se escriben siempre con textContent (community-shared.js).
 */
(() => {
  const dataEl = document.getElementById("comunidad-data");
  if (!dataEl || !window.MoaiCommunity) return;

  const { el, plural, avatar, timeAgo, api, store } = window.MoaiCommunity;
  const config = JSON.parse(dataEl.textContent);
  const assets = config.assets;
  const assetByTicker = Object.fromEntries(assets.map((a) => [a.ticker, a]));
  const mineTickers = new Set(assets.filter((a) => a.mine).map((a) => a.ticker));

  const $ = (selector) => document.querySelector(selector);
  const ui = {
    newsSection: $("#noticias"),
    newsFilters: $("[data-news-filters]"),
    newsMineChip: $("[data-mine-only]"),
    newsStatus: $("[data-news-status]"),
    newsList: $("[data-news-list]"),
    newsPager: $("[data-news-pager]"),
    newsMore: $("[data-news-more]"),
    newsLess: $("[data-news-less]"),
    newsShown: $("[data-news-shown]"),
    newsDemo: $("[data-news-demo]"),
    ranking: $("[data-ranking]"),
    sort: $("[data-votes-sort]"),
    total: $("[data-votes-total]"),
    votesStatus: $("[data-votes-status]"),
    votesLocal: $("[data-votes-local]"),
    notesTemplate: document.getElementById("cm-notes-template"),
  };

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Noticias ─────────────────────────────────────────────── */
  const PAGE = 9;
  const news = { items: [], filter: "", shown: PAGE };
  const TREND = {
    subir: { label: "Subir", symbol: "▲" },
    bajar: { label: "Bajar", symbol: "▼" },
    medio: { label: "Medio", symbol: "◆" },
  };

  function newsMatches(item) {
    if (!news.filter) return true;
    if (news.filter === "__mine") return item.tickers.some((t) => mineTickers.has(t));
    return item.tickers.includes(news.filter);
  }

  function trendTag(trend) {
    const info = TREND[trend] || TREND.medio;
    const tag = el("span", `cm-trend cm-trend--${trend in TREND ? trend : "medio"}`);
    tag.title = "Tendencia estimada a partir de la noticia";
    tag.append(el("span", "cm-trend__symbol", info.symbol), el("span", null, `Tendencia: ${info.label}`));
    return tag;
  }

  function newsCard(item) {
    const li = el("li");
    const card = el("article", "card cm-news__card");

    const top = el("div", "cm-news__top");
    top.append(el("span", "cm-ticker", item.tickers.join(" · ")), trendTag(item.trend));

    const title = el("h3", "cm-news__title");
    if (item.url) {
      const link = el("a", null, item.title);
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      title.append(link);
    } else {
      title.textContent = item.title;
    }

    card.append(top, title);
    if (item.summary) card.append(el("p", "cm-news__summary", item.summary));
    const meta = [item.source, item.published ? timeAgo(item.published) : null].filter(Boolean).join(" · ");
    card.append(el("p", "cm-news__meta", meta + (item.demo ? " · ejemplo" : "")));
    li.append(card);
    return li;
  }

  function renderNews() {
    const shown = news.items.filter(newsMatches);
    const visible = shown.slice(0, news.shown);
    ui.newsList.replaceChildren(...visible.map(newsCard));
    ui.newsMore.hidden = shown.length <= news.shown;
    ui.newsLess.hidden = news.shown <= PAGE;
    ui.newsPager.hidden = ui.newsMore.hidden && ui.newsLess.hidden;
    ui.newsShown.textContent = shown.length > PAGE ? `${visible.length} de ${shown.length}` : "";
    ui.newsStatus.textContent = shown.length ? "" : "No hay noticias recientes para este activo.";
    ui.newsStatus.hidden = !ui.newsStatus.textContent;
  }

  function renderNewsFilters() {
    const perTicker = new Map();
    for (const item of news.items) for (const t of item.tickers) perTicker.set(t, (perTicker.get(t) || 0) + 1);
    const chips = assets
      .filter((a) => perTicker.has(a.ticker))
      .map((a) => {
        const chip = el("button", "cm-chip", a.ticker);
        chip.type = "button";
        chip.title = a.name;
        chip.dataset.newsFilter = a.ticker;
        chip.setAttribute("aria-pressed", "false");
        chip.append(el("small", null, perTicker.get(a.ticker)));
        return chip;
      });
    ui.newsFilters
      .querySelectorAll("[data-news-filter]:not([data-news-filter=''], [data-news-filter='__mine'])")
      .forEach((c) => c.remove());
    ui.newsFilters.append(...chips);
    ui.newsMineChip.hidden = !news.items.some((i) => i.tickers.some((t) => mineTickers.has(t)));
  }

  ui.newsFilters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-news-filter]");
    if (!chip) return;
    news.filter = chip.dataset.newsFilter;
    news.shown = PAGE;
    ui.newsFilters.querySelectorAll("[data-news-filter]").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    renderNews();
  });

  ui.newsMore.addEventListener("click", () => {
    news.shown += PAGE;
    renderNews();
  });

  // "Ver menos": vuelve a la vista compacta y regresa al inicio del bloque.
  ui.newsLess.addEventListener("click", () => {
    news.shown = PAGE;
    renderNews();
    ui.newsSection.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  });

  async function loadNews() {
    try {
      const data = await api(config.newsUrl);
      news.items = data.items || [];
      ui.newsDemo.hidden = !data.demo;
      renderNewsFilters();
      renderNews();
    } catch {
      ui.newsStatus.textContent = "No se pudieron cargar las noticias. Inténtalo de nuevo más tarde.";
    }
  }

  /* ── Votos ────────────────────────────────────────────────── */
  const LOCAL_VOTES = `moainvest:comunidad:votos:${config.userKey}`;
  const LOCAL_NOTES = `moainvest:comunidad:notas:${config.userKey}`;
  const votes = { counts: {}, mine: {}, mode: "server", busy: new Set() };

  function useLocalVotes(reason) {
    votes.mode = "local";
    votes.mine = store.get(LOCAL_VOTES, {});
    votes.counts = {};
    for (const [ticker, vote] of Object.entries(votes.mine)) {
      if (vote !== "sube" && vote !== "baja") continue;
      votes.counts[ticker] = { sube: 0, baja: 0, [vote]: 1 };
    }
    ui.votesLocal.hidden = false;
    ui.votesLocal.title = reason || "No se pudo guardar en el servidor";
  }

  const countsOf = (ticker) => votes.counts[ticker] || { sube: 0, baja: 0 };

  const SORTERS = {
    total: (c) => c.sube + c.baja,
    sube: (c) => c.sube,
    baja: (c) => c.baja,
    balance: (c) => c.sube - c.baja,
  };

  function sortedAssets() {
    const key = SORTERS[ui.sort.value] || SORTERS.total;
    return assets
      .map((asset, index) => ({ asset, index, c: countsOf(asset.ticker) }))
      .sort((a, b) => key(b.c) - key(a.c) || b.c.sube + b.c.baja - (a.c.sube + a.c.baja) || a.index - b.index)
      .map((entry) => entry.asset);
  }

  function voteButton(ticker, vote, label, symbol) {
    const button = el("button", `cm-vote cm-vote--${vote === "sube" ? "up" : "down"}`);
    button.type = "button";
    button.dataset.vote = vote;
    button.dataset.ticker = ticker;
    button.append(el("span", null, symbol), el("span", null, label));
    return button;
  }

  // Cada fila se crea una vez y se actualiza: así el reordenamiento puede animarse.
  const rows = new Map();

  function buildRow(asset) {
    const li = el("li", "card cm-row");
    li.dataset.ticker = asset.ticker;
    const main = el("div", "cm-row__main");
    const rank = el("span", "cm-rank");

    const info = el("div", "cm-asset");
    info.append(el("p", "cm-asset__name", asset.name));
    const ticker = el("p", "cm-asset__ticker", asset.ticker);
    if (asset.mine) ticker.append(el("span", "cm-asset__mine", "★ Mis activos"));
    info.append(ticker);

    const meter = el("div", "cm-meter");
    const bar = el("div", "cm-bar");
    bar.setAttribute("aria-hidden", "true");
    const up = el("span", "cm-bar__up");
    const down = el("span", "cm-bar__down");
    bar.append(up, down);
    const text = el("p", "cm-meter__text");
    const count = el("span", "cm-meter__count");
    const split = el("span", "cm-mono");
    text.append(count, split);
    meter.append(bar, text);

    const actions = el("div", "cm-actions");
    const buttons = el("div", "cm-votes");
    buttons.setAttribute("role", "group");
    buttons.setAttribute("aria-label", `Tu voto para ${asset.name}`);
    const btnUp = voteButton(asset.ticker, "sube", "Sube", "▲");
    const btnDown = voteButton(asset.ticker, "baja", "Baja", "▼");
    buttons.append(btnUp, btnDown);
    const notesBtn = el("button", "cm-notes-toggle");
    notesBtn.type = "button";
    notesBtn.dataset.notesToggle = asset.ticker;
    notesBtn.setAttribute("aria-expanded", "false");
    actions.append(buttons, notesBtn);

    main.append(rank, info, meter, actions);
    li.append(main);
    return { li, rank, up, down, count, split, btnUp, btnDown, notesBtn, panel: null };
  }

  function updateRow(row, asset, position) {
    const c = countsOf(asset.ticker);
    const total = c.sube + c.baja;
    const mine = votes.mine[asset.ticker];
    row.rank.textContent = String(position);
    row.up.style.width = total ? `${(c.sube * 100) / total}%` : "0%";
    row.down.style.width = total ? `${(c.baja * 100) / total}%` : "0%";
    row.count.textContent = total ? plural(total, "voto", "votos") : "Sin votos";
    row.split.textContent = `▲ ${c.sube} · ▼ ${c.baja}`;
    row.btnUp.setAttribute("aria-pressed", String(mine === "sube"));
    row.btnDown.setAttribute("aria-pressed", String(mine === "baja"));
    const busy = votes.busy.has(asset.ticker);
    row.btnUp.disabled = busy;
    row.btnDown.disabled = busy;
    const n = notesOf(asset.ticker).length;
    row.notesBtn.textContent = n ? `Notas · ${n}` : "Añadir nota";
    row.notesBtn.classList.toggle("has-mine", Boolean(myNote(asset.ticker)));
  }

  function renderRanking() {
    const order = sortedAssets();
    // FLIP: se guarda la posición antes de reordenar y se anima la diferencia.
    const before = new Map();
    if (!reducedMotion) for (const [ticker, row] of rows) before.set(ticker, row.li.getBoundingClientRect().top);

    order.forEach((asset, index) => {
      let row = rows.get(asset.ticker);
      if (!row) {
        row = buildRow(asset);
        rows.set(asset.ticker, row);
      }
      updateRow(row, asset, index + 1);
      ui.ranking.append(row.li); // append mueve el nodo existente a su nuevo lugar
    });

    if (!reducedMotion) {
      for (const [ticker, row] of rows) {
        const prev = before.get(ticker);
        if (prev === undefined) continue;
        const delta = prev - row.li.getBoundingClientRect().top;
        if (Math.abs(delta) < 1) continue;
        row.li.animate([{ transform: `translateY(${delta}px)` }, { transform: "translateY(0)" }], {
          duration: 380,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        });
      }
    }

    const total = Object.values(votes.counts).reduce((sum, c) => sum + c.sube + c.baja, 0);
    const scope = votes.mode === "local" ? " en este navegador" : " de la comunidad";
    ui.total.textContent = `${plural(total, "voto", "votos")}${scope} · ${plural(assets.length, "activo", "activos")}`;
  }

  function applyServer(data) {
    votes.counts = data.counts || {};
    votes.mine = data.mine || {};
    votes.mode = "server";
    ui.votesLocal.hidden = true;
  }

  function castLocal(ticker, vote) {
    const prev = votes.mine[ticker];
    const c = { ...countsOf(ticker) };
    if (prev) c[prev] = Math.max(0, c[prev] - 1);
    if (vote) c[vote] += 1;
    votes.counts[ticker] = c;
    if (vote) votes.mine[ticker] = vote;
    else delete votes.mine[ticker];
  }

  async function vote(ticker, value) {
    const name = assetByTicker[ticker]?.name || ticker;
    ui.votesStatus.textContent = "";

    if (votes.mode === "local") {
      castLocal(ticker, value);
      store.set(LOCAL_VOTES, votes.mine);
      return;
    }
    // Optimista: el contador cambia al instante y se confirma con el servidor.
    const snapshot = { counts: structuredClone(votes.counts), mine: { ...votes.mine } };
    castLocal(ticker, value);
    votes.busy.add(ticker);
    renderRanking();
    try {
      applyServer(await api(config.votesUrl, { method: "POST", body: { ticker, voto: value } }));
    } catch (error) {
      if (error.local) {
        useLocalVotes(error.message);
        castLocal(ticker, value);
        store.set(LOCAL_VOTES, votes.mine);
      } else {
        votes.counts = snapshot.counts;
        votes.mine = snapshot.mine;
        ui.votesStatus.textContent = `No se pudo registrar tu voto para ${name}. Inténtalo de nuevo.`;
      }
    } finally {
      votes.busy.delete(ticker);
    }
  }

  async function loadVotes() {
    try {
      const data = await api(config.votesUrl);
      applyServer(data);
      if (!data.canVote) useLocalVotes("Inicia sesión para que tu voto cuente en la comunidad");
    } catch (error) {
      useLocalVotes(error.message);
    }
  }

  /* ── Notas (tesis por activo) ─────────────────────────────── */
  const NOTES_PREVIEW = 3;
  const notes = { items: [], mode: "server", expanded: new Set() };

  const notesOf = (ticker) => notes.items.filter((n) => n.ticker === ticker);
  const myNote = (ticker) => notes.items.find((n) => n.ticker === ticker && n.mine);

  function localNoteItems() {
    return Object.entries(store.get(LOCAL_NOTES, {})).map(([ticker, n]) => ({
      ticker,
      tag: n.tag || null,
      text: n.text || null,
      created: n.created,
      vote: votes.mine[ticker] || null,
      mine: true,
      author: { name: "Tú", avatar: null },
    }));
  }

  function useLocalNotes() {
    notes.mode = "local";
    notes.items = localNoteItems();
  }

  async function loadNotes() {
    try {
      const data = await api(config.notesUrl);
      notes.items = data.items || [];
      notes.mode = "server";
    } catch {
      useLocalNotes();
    }
  }

  function noteItem(note) {
    const li = el("li", `cm-note${note.mine ? " is-mine" : ""}`);
    li.append(avatar(note.author.avatar, note.author.name, "sm"));
    const body = el("div", "cm-note__body");
    const head = el("p", "cm-note__head");
    head.append(el("strong", null, note.author.name));
    if (note.vote) head.append(el("span", `cm-note__vote cm-note__vote--${note.vote}`, note.vote === "sube" ? "▲ Sube" : "▼ Baja"));
    head.append(el("span", "cm-note__time", timeAgo(note.created)));
    body.append(head);
    if (note.tag) body.append(el("span", "cm-quick__tag", note.tag));
    if (note.text) body.append(el("p", "cm-note__text", note.text));
    li.append(body);
    return li;
  }

  function buildPanel(ticker) {
    const panel = ui.notesTemplate.content.firstElementChild.cloneNode(true);
    panel.id = `notas-${ticker.replace(/[^A-Za-z0-9]/g, "_")}`;
    panel.querySelector("[data-note-asset]").textContent = assetByTicker[ticker]?.name || ticker;
    const tags = panel.querySelector("[data-note-tags]");
    for (const tag of config.quickTags) {
      const chip = el("button", "cm-quick__chip", tag);
      chip.type = "button";
      chip.dataset.noteTag = tag;
      chip.setAttribute("aria-pressed", "false");
      tags.append(chip);
    }
    panel.dataset.ticker = ticker;
    return panel;
  }

  function fillPanel(row, ticker) {
    const panel = row.panel;
    const mine = myNote(ticker);
    const selected = panel.dataset.selectedTag ?? mine?.tag ?? "";
    panel.querySelectorAll("[data-note-tag]").forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.noteTag === selected)));
    const input = panel.querySelector("[data-note-text]");
    if (!panel.dataset.dirty) input.value = mine?.text || "";
    panel.querySelector("[data-note-save]").textContent = mine ? "Actualizar nota" : "Guardar nota";
    panel.querySelector("[data-note-delete]").hidden = !mine;

    const all = notesOf(ticker);
    const expanded = notes.expanded.has(ticker);
    const list = panel.querySelector("[data-note-list]");
    list.replaceChildren(
      ...(all.length
        ? (expanded ? all : all.slice(0, NOTES_PREVIEW)).map(noteItem)
        : [el("li", "cm-note cm-note--empty", "Aún no hay notas sobre este activo. ¡Deja la primera!")]),
    );
    list.classList.toggle("is-expanded", expanded);
    const more = panel.querySelector("[data-note-all]");
    more.hidden = all.length <= NOTES_PREVIEW;
    more.textContent = expanded ? "Ver menos notas" : `Ver las ${all.length} notas`;
    if (notes.mode === "local") panel.querySelector("[data-note-status]").textContent ||= "Las notas se guardan solo en este navegador.";
  }

  function toggleNotes(ticker, open) {
    const row = rows.get(ticker);
    if (!row) return;
    const willOpen = open ?? !row.panel;
    if (!willOpen) {
      row.panel?.remove();
      row.panel = null;
      row.notesBtn.setAttribute("aria-expanded", "false");
      return;
    }
    if (!row.panel) {
      row.panel = buildPanel(ticker);
      row.li.append(row.panel);
      row.notesBtn.setAttribute("aria-controls", row.panel.id);
    }
    row.notesBtn.setAttribute("aria-expanded", "true");
    fillPanel(row, ticker);
  }

  function refreshOpenPanels() {
    for (const [ticker, row] of rows) if (row.panel) fillPanel(row, ticker);
  }

  async function saveNote(ticker, panel, remove = false) {
    const status = panel.querySelector("[data-note-status]");
    const tag = panel.dataset.selectedTag ?? myNote(ticker)?.tag ?? "";
    const text = panel.querySelector("[data-note-text]").value.trim();
    if (!remove && !tag && !text) {
      status.textContent = "Elige una reacción rápida o escribe una nota.";
      return;
    }
    const saveLocal = () => {
      const saved = store.get(LOCAL_NOTES, {});
      if (remove) delete saved[ticker];
      else saved[ticker] = { tag: tag || null, text: text || null, created: new Date().toISOString() };
      store.set(LOCAL_NOTES, saved);
      useLocalNotes();
    };
    panel.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      if (notes.mode === "local") saveLocal();
      else {
        const url = remove ? `${config.notesUrl}/${encodeURIComponent(ticker)}` : config.notesUrl;
        const data = await api(url, remove ? { method: "DELETE" } : { method: "POST", body: { ticker, tag: tag || null, text } });
        notes.items = notes.items.filter((n) => n.ticker !== ticker).concat(data.items || []);
        notes.items.sort((a, b) => String(b.created).localeCompare(String(a.created)));
      }
      delete panel.dataset.selectedTag;
      delete panel.dataset.dirty;
      status.textContent = remove ? "Nota quitada." : "Nota guardada.";
    } catch (error) {
      if (error.local) {
        saveLocal();
        delete panel.dataset.selectedTag;
        delete panel.dataset.dirty;
        status.textContent = "Nota guardada solo en este navegador.";
      } else {
        status.textContent = error.message || "No se pudo guardar la nota.";
      }
    } finally {
      panel.querySelectorAll("button").forEach((b) => (b.disabled = false));
      renderRanking();
      refreshOpenPanels();
    }
  }

  /* ── Eventos del ranking ──────────────────────────────────── */
  ui.ranking.addEventListener("click", async (event) => {
    const voteBtn = event.target.closest("[data-vote]");
    if (voteBtn) {
      const { ticker } = voteBtn.dataset;
      if (votes.busy.has(ticker)) return;
      // Mismo botón otra vez = retirar el voto.
      const value = votes.mine[ticker] === voteBtn.dataset.vote ? null : voteBtn.dataset.vote;
      await vote(ticker, value);
      // Tras votar, se invita a dejar la tesis si aún no hay nota propia.
      if (value && !myNote(ticker)) toggleNotes(ticker, true);
      // El voto propio aparece junto a la nota del usuario.
      notes.items.forEach((n) => n.mine && n.ticker === ticker && (n.vote = votes.mine[ticker] || null));
      renderRanking();
      refreshOpenPanels();
      return;
    }

    const toggle = event.target.closest("[data-notes-toggle]");
    if (toggle) {
      toggleNotes(toggle.dataset.notesToggle);
      return;
    }

    const panel = event.target.closest(".cm-notes");
    if (!panel) return;
    const { ticker } = panel.dataset;
    const chip = event.target.closest("[data-note-tag]");
    if (chip) {
      const current = panel.dataset.selectedTag ?? myNote(ticker)?.tag ?? "";
      panel.dataset.selectedTag = current === chip.dataset.noteTag ? "" : chip.dataset.noteTag;
      fillPanel(rows.get(ticker), ticker);
      return;
    }
    if (event.target.closest("[data-note-delete]")) {
      await saveNote(ticker, panel, true);
      return;
    }
    if (event.target.closest("[data-note-all]")) {
      if (notes.expanded.has(ticker)) notes.expanded.delete(ticker);
      else notes.expanded.add(ticker);
      fillPanel(rows.get(ticker), ticker);
    }
  });

  ui.ranking.addEventListener("input", (event) => {
    const panel = event.target.closest(".cm-notes");
    if (panel && event.target.matches("[data-note-text]")) panel.dataset.dirty = "1";
  });

  ui.ranking.addEventListener("submit", (event) => {
    const panel = event.target.closest(".cm-notes");
    if (!panel) return;
    event.preventDefault();
    saveNote(panel.dataset.ticker, panel);
  });

  ui.sort.addEventListener("change", renderRanking);

  renderRanking();
  Promise.all([loadVotes(), loadNotes()]).then(() => {
    renderRanking();
    refreshOpenPanels();
  });
  loadNews();
})();
