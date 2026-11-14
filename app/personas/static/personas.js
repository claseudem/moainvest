/* PERSONAS (comunidad): directorio con buscador, filtros y perfil público.
 *
 * Los integrantes llegan en #personas-data (JSON), ya filtrados por el servidor
 * a perfiles públicos (ver community.members). Aquí solo se buscan y filtran
 * esos datos, y se muestra el perfil público. Nada de esta sección lee ni
 * escribe progreso personal.
 *
 * Los filtros se combinan: dentro de un grupo basta con una opción (O), y entre
 * grupos deben cumplirse todos (Y). Los textos se escriben con textContent.
 */
(() => {
  const dataEl = document.getElementById("personas-data");
  if (!dataEl) return;

  const { members, profiles } = JSON.parse(dataEl.textContent);
  const profileName = Object.fromEntries(profiles.map((p) => [p.slug, p.name]));

  const $ = (selector) => document.querySelector(selector);
  const ui = {
    search: $("[data-search]"),
    profileChips: document.querySelectorAll("[data-filter-profile]"),
    levelChips: document.querySelectorAll("[data-filter-level]"),
    count: $("[data-results-count]"),
    directory: $("[data-directory]"),
    empty: $("[data-directory-empty]"),
    panel: $("[data-public]"),
    panelAvatar: $("[data-public-avatar]"),
    panelName: $("[data-public-name]"),
    panelProfile: $("[data-public-profile]"),
    panelLevel: $("[data-public-level]"),
    panelBio: $("[data-public-bio]"),
    panelInterests: $("[data-public-interests]"),
    panelAchievements: $("[data-public-achievements]"),
    panelClose: $("[data-public-close]"),
  };

  const EMPTY_TEXT = "Aún no hay integrantes que mostrar. Cuando haya perfiles públicos, aparecerán aquí.";
  const filters = { text: "", profiles: new Set(), levels: new Set() };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function matches(member) {
    const text = filters.text.trim().toLowerCase();
    if (text) {
      const haystack = [member.name, ...(member.interests || [])].join(" ").toLowerCase();
      if (!haystack.includes(text)) return false;
    }
    if (filters.profiles.size && !filters.profiles.has(member.profile)) return false;
    if (filters.levels.size && !filters.levels.has(String(member.level))) return false;
    return true;
  }

  function renderDirectory() {
    const shown = members.filter(matches);
    ui.directory.replaceChildren(...shown.map(card));

    if (members.length === 0) {
      ui.count.textContent = "";
      ui.empty.textContent = EMPTY_TEXT;
      ui.empty.hidden = false;
      return;
    }
    ui.count.textContent = `${shown.length} de ${members.length} ${members.length === 1 ? "persona" : "personas"}`;
    ui.empty.textContent = "Ninguna persona coincide con la búsqueda o los filtros.";
    ui.empty.hidden = shown.length > 0;
  }

  function card(member) {
    const li = el("li", "card pe-member");
    const head = el("div", "pe-member__head");
    head.append(el("span", "pe-avatar", member.initial || "?"), el("p", "pe-member__name", member.name));
    const profile = el("p", "pe-member__profile", profileName[member.profile] || "");
    const level = el("p", "pe-hint", `Nivel ${member.level}: ${member.level_name}`);
    const bio = el("p", "pe-hint", member.bio || "");
    const button = el("button", "btn btn--secondary btn--sm", "Ver perfil");
    button.type = "button";
    button.addEventListener("click", () => showPublic(member));
    li.append(head, profile, level, bio, button);
    return li;
  }

  function showPublic(member) {
    ui.panelAvatar.textContent = member.initial || "?";
    ui.panelName.textContent = member.name;
    ui.panelProfile.textContent = `Perfil: ${profileName[member.profile] || ""}`;
    ui.panelLevel.textContent = `Nivel ${member.level}: ${member.level_name}`;
    ui.panelBio.textContent = member.bio || "";
    ui.panelInterests.replaceChildren(...(member.interests || []).map((i) => el("li", "pe-tag-item", i)));
    ui.panelAchievements.replaceChildren(
      ...((member.achievements || []).length
        ? member.achievements.map((a) => el("li", "", a))
        : [el("li", "pe-hint", "Esta persona no ha compartido logros todavía.")]),
    );
    ui.panel.hidden = false;
    ui.panel.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function toggleChip(button, set) {
    const value = button.dataset.filterProfile ?? button.dataset.filterLevel;
    const on = !set.has(value);
    if (on) set.add(value);
    else set.delete(value);
    button.setAttribute("aria-pressed", String(on));
    renderDirectory();
  }

  ui.search.addEventListener("input", () => {
    filters.text = ui.search.value;
    renderDirectory();
  });
  ui.profileChips.forEach((b) => b.addEventListener("click", () => toggleChip(b, filters.profiles)));
  ui.levelChips.forEach((b) => b.addEventListener("click", () => toggleChip(b, filters.levels)));
  ui.panelClose.addEventListener("click", () => {
    ui.panel.hidden = true;
  });

  renderDirectory();

  // ── Invitar personas: copia el enlace de registro existente ─────
  const inviteButton = document.querySelector("[data-copy-invite]");
  const inviteInput = document.getElementById("invite-link");
  const inviteStatus = document.querySelector("[data-copy-status]");
  if (inviteButton && inviteInput) {
    inviteButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(inviteInput.value);
        inviteStatus.textContent = "Enlace copiado. Compártelo para invitar a más personas.";
      } catch {
        inviteInput.focus();
        inviteInput.select();
        inviteStatus.textContent = "Selecciona el enlace y cópialo con Ctrl+C.";
      }
    });
  }
})();
