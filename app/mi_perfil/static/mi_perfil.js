/* MI PERFIL: perfil elegido, nivel, misiones y trayectoria.
 *
 * Los perfiles, niveles y misiones llegan en #mi-perfil-data (JSON). Lo que la
 * persona hace se guarda en su navegador (localStorage), con una clave por
 * usuario y dentro de ella un bloque por perfil: cambiar de perfil no borra ni
 * mezcla el progreso de otro, y otra cuenta en el mismo navegador empieza limpia.
 *
 * Las misiones son secuenciales: solo la siguiente está disponible. Los textos
 * se escriben con textContent, nunca con innerHTML.
 */
(() => {
  const dataEl = document.getElementById("mi-perfil-data");
  if (!dataEl) return;

  const { profiles, xpPerLevel, userKey } = JSON.parse(dataEl.textContent);
  const STORAGE_KEY = `moainvest.mi-perfil.v1.${userKey}`;
  const bySlug = Object.fromEntries(profiles.map((p) => [p.slug, p]));

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => document.querySelectorAll(selector);
  const ui = {
    cards: $$("[data-profile]"),
    chosenLine: $("[data-chosen-line]"),
    route: $("[data-route]"),
    levelTitle: $("[data-level-title]"),
    xpText: $("[data-xp-text]"),
    xpBar: $("[data-xp-bar]"),
    nextLevel: $("[data-next-level]"),
    path: $("[data-path]"),
    stats: {
      completadas: $("[data-stat='completadas']"),
      disponibles: $("[data-stat='disponibles']"),
      bloqueadas: $("[data-stat='bloqueadas']"),
    },
    next: {
      card: $("[data-next-card]"),
      icon: $("[data-next-icon]"),
      name: $("[data-next-name]"),
      desc: $("[data-next-desc]"),
      status: $("[data-next-status]"),
      xp: $("[data-next-xp]"),
      difficulty: $("[data-next-difficulty]"),
      action: $("[data-next-action]"),
      empty: $("[data-next-empty]"),
    },
    panel: $("[data-panel]"),
    panelLabel: $("[data-panel-label]"),
    panelName: $("[data-panel-name]"),
    panelObjective: $("[data-panel-objective]"),
    panelSteps: $("[data-panel-steps]"),
    complete: $("[data-action='completar']"),
    message: $("[data-message]"),
    others: $("[data-others]"),
    history: $("[data-history]"),
    historyCount: $("[data-history-count]"),
    historyList: $("[data-history-list]"),
    editar: $("[data-action='editar']"),
    section: $("#mp-perfil"),
  };

  const STATUS_LABEL = {
    completada: "Completada",
    progreso: "En progreso",
    disponible: "Disponible",
    bloqueada: "Bloqueada",
  };

  // ── Estado (por usuario, con un bloque por perfil) ──────────────
  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (saved && typeof saved === "object") return { perfil: saved.perfil || null, progreso: saved.progreso || {} };
    } catch {
      /* Sin localStorage el progreso dura solo esta visita. */
    }
    return { perfil: null, progreso: {} };
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* Sin almacenamiento disponible la sección sigue funcionando. */
    }
  }

  const state = load();
  if (state.perfil && !bySlug[state.perfil]) state.perfil = null;
  let panelOpen = false;

  function progressOf(slug) {
    if (!state.progreso[slug]) state.progreso[slug] = { hechas: [], iniciada: null };
    return state.progreso[slug];
  }

  // Primer nivel sin completar: la siguiente misión. ``null`` si la ruta está completa.
  function currentIndex(profile, progress) {
    const index = profile.stages.findIndex((_, i) => !progress.hechas.includes(i));
    return index === -1 ? null : index;
  }

  function statusOf(index, progress, current) {
    if (progress.hechas.includes(index)) return "completada";
    if (index === current) return progress.iniciada === index ? "progreso" : "disponible";
    return "bloqueada";
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Calcula el nivel y el XP de la ruta a partir de las misiones completadas.
  function levelOf(profile, progress) {
    const xp = progress.hechas.reduce((sum, i) => sum + profile.stages[i].xp, 0);
    const total = profile.stages.length;
    const level = Math.min(total, Math.floor(xp / xpPerLevel) + 1);
    const next = level >= total ? null : level * xpPerLevel;
    return { xp, level, next, total };
  }

  // ── Perfil elegido ──────────────────────────────────────────────
  function renderCards() {
    ui.cards.forEach((card) => {
      const selected = state.perfil === card.dataset.profile;
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-pressed", String(selected));
      card.querySelector("[data-selected-badge]").hidden = !selected;
    });
    ui.chosenLine.textContent = state.perfil
      ? `Perfil elegido: ${bySlug[state.perfil].name}.`
      : "Aún no has elegido un perfil.";
  }

  function render() {
    if (!state.perfil) {
      ui.route.hidden = true;
      return;
    }
    const profile = bySlug[state.perfil];
    const progress = progressOf(profile.slug);
    const current = currentIndex(profile, progress);
    const level = levelOf(profile, progress);

    ui.route.hidden = false;
    renderLevel(profile, progress, current, level);
    renderPath(profile, progress, current);
    renderNext(profile, progress, current);
    renderOthers(profile, progress, current);
    renderHistory(profile, progress);
    renderPanel(profile, progress, current);
  }

  function renderLevel(profile, progress, current, level) {
    const stage = profile.stages[level.level - 1];
    ui.levelTitle.textContent = `Nivel ${level.level} — ${stage.name}`;
    if (level.next === null) {
      ui.xpText.textContent = `${level.xp} XP · nivel máximo de la ruta`;
      ui.nextLevel.textContent = "Ya alcanzaste el último nivel de este perfil.";
      ui.xpBar.setAttribute("aria-valuenow", "100");
      ui.xpBar.firstElementChild.style.width = "100%";
      return;
    }
    const next = profile.stages[level.level];
    ui.xpText.textContent = `${level.xp} / ${level.next} XP`;
    const percent = Math.round((level.xp * 100) / level.next);
    ui.xpBar.setAttribute("aria-valuenow", String(percent));
    ui.xpBar.firstElementChild.style.width = `${percent}%`;
    ui.nextLevel.textContent = `Próximo nivel: ${next.name}.`;
  }

  function renderPath(profile, progress, current) {
    ui.path.replaceChildren(
      ...profile.stages.map((stage, index) => {
        const status = statusOf(index, progress, current);
        const cls = status === "completada" ? "is-done" : index === current ? "is-current" : "is-locked";
        const li = el("li", `mp-node ${cls}`);
        li.setAttribute("aria-label", `Nivel ${index + 1}: ${stage.name}, ${STATUS_LABEL[status].toLowerCase()}`);
        li.append(el("span", "mp-node__num", String(index + 1)), el("span", "mp-node__name", stage.name));
        return li;
      }),
    );
  }

  function renderNext(profile, progress, current) {
    const n = ui.next;
    if (current === null) {
      n.card.hidden = true;
      n.empty.hidden = false;
      return;
    }
    const stage = profile.stages[current];
    const status = statusOf(current, progress, current);
    n.empty.hidden = true;
    n.card.hidden = false;
    n.icon.replaceChildren(...iconNodes());
    n.name.textContent = stage.mission;
    n.desc.textContent = stage.description;
    n.status.textContent = STATUS_LABEL[status];
    n.status.className = `mp-badge ${status === "progreso" ? "is-progreso" : "is-next"}`;
    n.xp.textContent = `+${stage.xp} XP`;
    n.difficulty.textContent = stage.difficulty;
    n.action.textContent = status === "progreso" ? "Continuar misión" : "Iniciar misión";
    n.action.dataset.action = "iniciar";
  }

  // Copia el icono SVG del perfil elegido para usarlo en la tarjeta de la misión.
  function iconNodes() {
    const card = [...ui.cards].find((c) => c.dataset.profile === state.perfil);
    const svg = card && card.querySelector("svg");
    return svg ? [svg.cloneNode(true)] : [];
  }

  function renderOthers(profile, progress, current) {
    const rest = profile.stages
      .map((stage, index) => ({ stage, index, status: statusOf(index, progress, current) }))
      .filter((item) => item.status === "bloqueada");

    const available = current === null ? 0 : 1;
    ui.stats.completadas.textContent = String(progress.hechas.length);
    ui.stats.disponibles.textContent = String(available);
    ui.stats.bloqueadas.textContent = String(rest.length);

    ui.others.replaceChildren(
      ...(rest.length
        ? rest.map(({ stage, index }) => {
            const li = el("li", "mp-row is-locked");
            const head = el("div", "mp-row__main");
            head.append(el("span", "mp-row__name", stage.mission), el("span", "mp-row__xp", `+${stage.xp} XP`));
            const lock = el("p", "mp-row__req");
            lock.textContent = `Requisito: completa «${profile.stages[index - 1].mission}».`;
            li.append(head, lock);
            return li;
          })
        : [el("li", "mp-empty", "No quedan misiones bloqueadas.")]),
    );
  }

  function renderHistory(profile, progress) {
    const done = progress.hechas.slice().sort((a, b) => a - b);
    ui.historyCount.textContent = String(done.length);
    ui.historyList.replaceChildren(
      ...(done.length
        ? done.map((index) => {
            const stage = profile.stages[index];
            const li = el("li", "mp-row is-done");
            const head = el("div", "mp-row__main");
            head.append(el("span", "mp-row__name", stage.mission), el("span", "mp-row__xp", `+${stage.xp} XP`));
            li.append(head);
            return li;
          })
        : [el("li", "mp-empty", "Todavía no has completado misiones.")]),
    );
    ui.history.open = ui.history.open && done.length > 0;
  }

  function renderPanel(profile, progress, current) {
    const open = panelOpen && current !== null;
    ui.panel.hidden = !open;
    if (!open) return;

    const stage = profile.stages[current];
    const started = progress.iniciada === current;
    ui.panelLabel.textContent = `Nivel ${current + 1} · ${stage.name} · ${stage.difficulty} · +${stage.xp} XP`;
    ui.panelName.textContent = stage.mission;
    ui.panelObjective.textContent = stage.objective;
    ui.panelSteps.replaceChildren(...stage.steps.map((text) => el("li", "", text)));
    ui.complete.disabled = !started;
    if (!started) say("Pulsa «Iniciar misión» en la tarjeta para comenzar.");
  }

  function say(text) {
    ui.message.textContent = text;
  }

  // ── Acciones ────────────────────────────────────────────────────
  function selectProfile(slug) {
    state.perfil = slug;
    progressOf(slug);
    panelOpen = false;
    save();
    renderCards();
    render();
    say("");
  }

  function startCurrent() {
    const profile = bySlug[state.perfil];
    const progress = progressOf(profile.slug);
    const current = currentIndex(profile, progress);
    if (current === null) return;
    progress.iniciada = current;
    panelOpen = true;
    save();
    render();
    say("Misión iniciada. Sigue los pasos y márcala como completada cuando termines.");
    ui.panel.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function completeCurrent() {
    const profile = bySlug[state.perfil];
    const progress = progressOf(profile.slug);
    const current = currentIndex(profile, progress);
    if (current === null || progress.iniciada !== current) return;

    const earned = profile.stages[current].xp;
    progress.hechas.push(current);
    progress.iniciada = null;
    const next = currentIndex(profile, progress);
    panelOpen = false;
    save();
    render();
    if (next === null) {
      say(`¡Ruta completada! +${earned} XP en esta misión.`);
    } else {
      say(`¡Misión completada! +${earned} XP. Desbloqueaste: ${profile.stages[next].mission}.`);
    }
  }

  function closePanel() {
    panelOpen = false;
    render();
  }

  // ── Eventos ─────────────────────────────────────────────────────
  ui.cards.forEach((card) => card.addEventListener("click", () => selectProfile(card.dataset.profile)));

  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action) return;
    if (action === "iniciar" && state.perfil) startCurrent();
    if (action === "completar" && state.perfil) completeCurrent();
    if (action === "cerrar") closePanel();
    if (action === "editar") {
      ui.section.focus();
      ui.section.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  });

  renderCards();
  render();
})();
