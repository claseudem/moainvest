/* MI PERFIL · perfil de comunidad e Interacción.
 *
 * - Perfil: foto (reducida aquí a 192×192 JPEG) o iniciales con color,
 *   nombre visible, profesión, bio/enfoque y visibilidad. Se guarda con
 *   PUT /api/comunidad/perfil; si no hay base de datos, en localStorage.
 * - Resumen de actividad: votos, notas, perfil elegido, siguiendo, conexiones.
 * - Interacción: comparar posturas (consenso y personas que sigues), seguir /
 *   conectar con perfiles públicos y notas rápidas por activo.
 *
 * Usa window.MoaiCommunity (personas/static/community-shared.js). Los textos se
 * escriben siempre con textContent.
 */
(() => {
  const dataEl = document.getElementById("mi-perfil-comunidad");
  if (!dataEl || !window.MoaiCommunity) return;

  const { el, plural, avatar, timeAgo, api, store } = window.MoaiCommunity;
  const config = JSON.parse(dataEl.textContent);
  const missionsKey = (() => {
    try {
      return `moainvest.mi-perfil.v1.${JSON.parse(document.getElementById("mi-perfil-data").textContent).userKey}`;
    } catch {
      return null;
    }
  })();
  const LOCAL_PROFILE = `moainvest:comunidad:perfil:${config.userKey}`;
  const LOCAL_VOTES = `moainvest:comunidad:votos:${config.userKey}`;
  const LOCAL_NOTES = `moainvest:comunidad:notas:${config.userKey}`;
  const profileName = Object.fromEntries(config.profiles.map((p) => [p.slug, p.name]));
  const assetName = Object.fromEntries(config.assets.map((a) => [a.ticker, a.name]));

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const ui = {
    avatar: $("[data-c-avatar]"),
    name: $("[data-c-name]"),
    visibility: $("[data-c-visibility]"),
    profession: $("[data-c-profession]"),
    bio: $("[data-c-bio]"),
    edit: $("[data-c-edit]"),
    stat: Object.fromEntries($$("[data-c-stat]").map((n) => [n.dataset.cStat, n])),
    notice: $("[data-c-notice]"),
    dbNotice: $("[data-c-db-notice]"),
    tabs: $$("[data-c-tab]"),
    panels: $$("[data-c-panel]"),
    agreeSummary: $("[data-c-agree-summary]"),
    compare: $("[data-c-compare]"),
    compareEmpty: $("[data-c-compare-empty]"),
    peers: $("[data-c-peers]"),
    memberSearch: $("[data-c-member-search]"),
    members: $("[data-c-members]"),
    membersEmpty: $("[data-c-members-empty]"),
    noteForm: $("[data-c-note-form]"),
    noteAsset: $("[data-c-note-asset]"),
    noteText: $("[data-c-note-text]"),
    noteTags: $$("[data-c-note-tag]"),
    noteStatus: $("[data-c-note-status]"),
    myNotes: $("[data-c-my-notes]"),
    recentNotes: $("[data-c-recent-notes]"),
    dialog: $("[data-c-dialog]"),
    form: $("[data-c-form]"),
    preview: $("[data-c-preview]"),
    file: $("[data-c-file]"),
    colors: $$("[data-c-color]"),
    photoClear: $("[data-c-photo-clear]"),
    inputs: Object.fromEntries($$("[data-c-input]").map((n) => [n.dataset.cInput, n])),
    bioCount: $("[data-c-bio-count]"),
    formStatus: $("[data-c-form-status]"),
    save: $("[data-c-save]"),
  };

  const state = {
    mode: "server", // "server" | "local"
    profile: null,
    social: { following: 0, followers: 0, connections: 0 },
    votes: { counts: {}, mine: {} },
    notes: [],
    members: [],
    draftAvatar: null,
    noteTag: "",
  };

  const NO_DB_TEXT =
    "Aún no hay una base de datos multiusuario conectada: tu perfil, votos y notas se guardan solo en este navegador y nadie más los ve.";
  const NO_SESSION_TEXT = "Inicia sesión para que tu perfil y tus notas se compartan con la comunidad.";

  function goLocal(error) {
    state.mode = "local";
    const text = error?.status === 401 ? NO_SESSION_TEXT : NO_DB_TEXT;
    for (const notice of [ui.notice, ui.dbNotice]) {
      notice.textContent = text;
      notice.hidden = false;
    }
  }

  const selectedProfile = () => (missionsKey ? store.get(missionsKey, {})?.perfil || null : null);
  const displayName = () => state.profile?.nombre || config.defaultName || "Cuenta sin nombre";

  /* ── Identidad y resumen ──────────────────────────────────── */
  function renderIdentity() {
    const p = state.profile || {};
    ui.avatar.replaceChildren(avatar(p.avatar, displayName(), "lg"));
    ui.name.textContent = displayName();
    ui.profession.textContent = p.profesion || "";
    ui.profession.hidden = !p.profesion;
    ui.bio.textContent = p.bio || "";
    ui.bio.hidden = !p.bio;
    const visible = Boolean(p.visible) && state.mode === "server";
    ui.visibility.textContent = visible ? "Visible en la comunidad" : "Perfil privado";
    ui.visibility.classList.toggle("is-public", visible);
    renderStats();
  }

  function renderStats() {
    const myNotes = state.notes.filter((n) => n.mine);
    ui.stat.votes.textContent = String(Object.keys(state.votes.mine).length);
    ui.stat.notes.textContent = String(myNotes.length);
    const slug = selectedProfile();
    ui.stat.profile.textContent = slug ? profileName[slug] || "—" : "Sin elegir";
    ui.stat.following.textContent = String(state.social.following);
    ui.stat.connections.textContent = String(state.social.connections);
  }

  /* ── Diálogo "Editar perfil" ──────────────────────────────── */
  function renderPreview() {
    ui.preview.replaceChildren(avatar(state.draftAvatar, ui.inputs.nombre.value || displayName(), "xl"));
    ui.colors.forEach((b) => b.setAttribute("aria-checked", String(state.draftAvatar === `iniciales:${b.dataset.cColor}`)));
    ui.photoClear.hidden = !state.draftAvatar;
  }

  function updateBioCount() {
    ui.bioCount.textContent = `${ui.inputs.bio.value.length} / ${config.limits.bio}`;
  }

  function openDialog() {
    const p = state.profile || {};
    ui.inputs.nombre.value = p.nombre || config.defaultName || "";
    ui.inputs.profesion.value = p.profesion || "";
    ui.inputs.bio.value = p.bio || "";
    ui.inputs.visible.checked = Boolean(p.visible);
    ui.inputs.visible.disabled = state.mode === "local";
    state.draftAvatar = p.avatar || null;
    ui.formStatus.textContent = state.mode === "local" ? "Se guardará solo en este navegador." : "";
    updateBioCount();
    renderPreview();
    if (typeof ui.dialog.showModal === "function") ui.dialog.showModal();
    else ui.dialog.setAttribute("open", "");
    ui.inputs.nombre.focus();
  }

  function closeDialog() {
    if (typeof ui.dialog.close === "function") ui.dialog.close();
    else ui.dialog.removeAttribute("open");
  }

  // Recorta al centro y reduce a 192×192 JPEG: la foto cabe en la base de datos.
  function resizePhoto(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 192;
        canvas
          .getContext("2d")
          .drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, 0, 0, 192, 192);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("No se pudo leer la imagen."));
      };
      img.src = url;
    });
  }

  ui.file.addEventListener("change", async () => {
    const file = ui.file.files?.[0];
    ui.file.value = "";
    if (!file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      ui.formStatus.textContent = "Usa una imagen JPG, PNG o WebP.";
      return;
    }
    try {
      state.draftAvatar = await resizePhoto(file);
      ui.formStatus.textContent = "";
      renderPreview();
    } catch (error) {
      ui.formStatus.textContent = error.message;
    }
  });

  ui.colors.forEach((button) =>
    button.addEventListener("click", () => {
      state.draftAvatar = `iniciales:${button.dataset.cColor}`;
      renderPreview();
    }),
  );
  ui.photoClear.addEventListener("click", () => {
    state.draftAvatar = null;
    renderPreview();
  });
  ui.inputs.nombre.addEventListener("input", renderPreview);
  ui.inputs.bio.addEventListener("input", updateBioCount);
  ui.edit.addEventListener("click", openDialog);
  $$("[data-c-cancel]").forEach((b) => b.addEventListener("click", closeDialog));

  function profileBody(overrides = {}) {
    const p = state.profile || {};
    return {
      nombre: p.nombre ?? config.defaultName ?? "",
      profesion: p.profesion || "",
      bio: p.bio || "",
      avatar: p.avatar || null,
      visible: Boolean(p.visible),
      perfil: selectedProfile(),
      ...overrides,
    };
  }

  async function saveProfile(body) {
    if (state.mode === "local") {
      state.profile = { ...body, visible: false };
      store.set(LOCAL_PROFILE, state.profile);
      return;
    }
    try {
      const data = await api(config.urls.profile, { method: "PUT", body });
      applyProfile(data);
    } catch (error) {
      if (!error.local) throw error;
      goLocal(error);
      state.profile = { ...body, visible: false };
      store.set(LOCAL_PROFILE, state.profile);
    }
  }

  ui.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    ui.save.disabled = true;
    ui.formStatus.textContent = "Guardando…";
    try {
      await saveProfile(
        profileBody({
          nombre: ui.inputs.nombre.value.trim(),
          profesion: ui.inputs.profesion.value.trim(),
          bio: ui.inputs.bio.value.trim(),
          avatar: state.draftAvatar,
          visible: ui.inputs.visible.checked,
        }),
      );
      renderIdentity();
      closeDialog();
      loadMembers(); // la visibilidad cambia quién aparece en la comunidad
    } catch (error) {
      ui.formStatus.textContent = error.message || "No se pudo guardar el perfil.";
    } finally {
      ui.save.disabled = false;
    }
  });

  // El perfil elegido en las misiones se refleja en el resumen y en el perfil público.
  document.addEventListener("mp:perfil", () => {
    renderStats();
    if (state.mode === "server" && state.profile) saveProfile(profileBody()).catch(() => {});
  });

  /* ── Pestañas ─────────────────────────────────────────────── */
  function selectTab(name, focus = false) {
    ui.tabs.forEach((tab) => {
      const active = tab.dataset.cTab === name;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });
    ui.panels.forEach((panel) => (panel.hidden = panel.dataset.cPanel !== name));
  }

  ui.tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab.dataset.cTab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      selectTab(ui.tabs[(index + step + ui.tabs.length) % ui.tabs.length].dataset.cTab, true);
    });
  });

  /* ── 1. Comparar posturas ─────────────────────────────────── */
  const VOTE_TEXT = { sube: "▲ Sube", baja: "▼ Baja" };

  // Consenso de los demás: los conteos sin el voto propio.
  function consensusOf(ticker) {
    const c = { ...(state.votes.counts[ticker] || { sube: 0, baja: 0 }) };
    const mine = state.votes.mine[ticker];
    if (mine && c[mine] > 0) c[mine] -= 1;
    const total = c.sube + c.baja;
    const side = c.sube > c.baja ? "sube" : c.baja > c.sube ? "baja" : total ? "dividido" : null;
    return { ...c, total, side };
  }

  function renderCompare() {
    const mine = Object.entries(state.votes.mine);
    ui.compareEmpty.hidden = mine.length > 0;
    let agree = 0;
    let differ = 0;
    const rows = mine.map(([ticker, vote]) => {
      const crowd = consensusOf(ticker);
      const status = !crowd.side ? "sin" : crowd.side === "dividido" ? "dividido" : crowd.side === vote ? "coincide" : "difiere";
      if (status === "coincide") agree += 1;
      if (status === "difiere") differ += 1;
      const li = el("li", "mpc-compare__row");
      const asset = el("div", "mpc-compare__asset");
      asset.append(el("strong", null, assetName[ticker] || ticker), el("span", null, ticker));
      const crowdText = crowd.total ? `Comunidad: ▲ ${crowd.sube} · ▼ ${crowd.baja}` : "Sin votos de otros";
      const badgeText = { coincide: "Coincides", difiere: "Difieres", dividido: "Opiniones divididas", sin: "Sin consenso aún" }[status];
      li.append(
        asset,
        el("span", `mpc-vote mpc-vote--${vote}`, `Tú: ${VOTE_TEXT[vote]}`),
        el("span", "mpc-compare__crowd", crowdText),
        el("span", `mpc-badge mpc-badge--${status}`, badgeText),
      );
      return { li, status };
    });
    // Primero donde difieres: es lo más interesante de revisar.
    const order = { difiere: 0, coincide: 1, dividido: 2, sin: 3 };
    rows.sort((a, b) => order[a.status] - order[b.status]);
    ui.compare.replaceChildren(...rows.map((r) => r.li));

    const compared = agree + differ;
    ui.agreeSummary.replaceChildren();
    if (mine.length) {
      const big = el("span", "mpc-summary__big", compared ? `${Math.round((agree * 100) / compared)}%` : "—");
      const text = el(
        "span",
        "mp-hint",
        compared
          ? `de coincidencia con el consenso: coincides en ${plural(agree, "activo", "activos")} y difieres en ${differ}.`
          : "Aún no hay votos de otros miembros en los activos que votaste.",
      );
      ui.agreeSummary.append(big, text);
    }
    renderPeers();
  }

  function renderPeers() {
    const mine = state.votes.mine;
    const followed = state.members.filter((m) => m.following);
    if (state.mode === "local") {
      ui.peers.replaceChildren(el("li", "mpc-empty", "Disponible cuando haya base de datos multiusuario: podrás comparar tus votos con las personas que sigues."));
      return;
    }
    if (!followed.length) {
      ui.peers.replaceChildren(el("li", "mpc-empty", "Aún no sigues a nadie. En «Seguir y conectar» encontrarás perfiles públicos."));
      return;
    }
    ui.peers.replaceChildren(
      ...followed.map((member) => {
        const common = Object.keys(member.votes).filter((t) => mine[t]);
        const same = common.filter((t) => member.votes[t] === mine[t]).length;
        const li = el("li", "mpc-peer");
        li.append(avatar(member.avatar, member.name, "sm"), el("strong", null, member.name));
        if (common.length) {
          const bar = el("span", "mpc-peer__bar");
          const fill = el("span");
          fill.style.width = `${(same * 100) / common.length}%`;
          bar.append(fill);
          li.append(bar, el("span", "mp-hint", `Coinciden en ${same} de ${plural(common.length, "activo", "activos")}`));
        } else {
          li.append(el("span", "mp-hint", "Sin activos votados en común"));
        }
        return li;
      }),
    );
  }

  /* ── 2. Seguir y conectar ─────────────────────────────────── */
  const CONNECTION = {
    conectados: { label: "Conectados", pressed: true, hint: "Conexión mutua" },
    enviada: { label: "Solicitud enviada", pressed: true, hint: "Esperando que te conecte" },
    recibida: { label: "Aceptar conexión", pressed: false, hint: "Quiere conectar contigo" },
  };

  function memberCard(member) {
    const li = el("li", "mpc-member");
    const head = el("div", "mpc-member__head");
    const who = el("div");
    who.append(el("p", "mpc-member__name", member.name));
    const meta = [member.profession, member.profile ? profileName[member.profile] : null].filter(Boolean).join(" · ");
    if (meta) who.append(el("p", "mpc-member__meta", meta));
    head.append(avatar(member.avatar, member.name, "md"), who);
    li.append(head);
    if (member.bio) li.append(el("p", "mpc-member__bio", member.bio));

    const watched = [...new Set([...member.assets, ...Object.keys(member.votes)])];
    if (watched.length) {
      const label = el("p", "mp-label", "Activos que observa");
      const list = el("div", "mpc-tickers");
      for (const ticker of watched.slice(0, 10)) {
        const vote = member.votes[ticker];
        const chip = el("span", `mpc-ticker${vote ? ` mpc-ticker--${vote}` : ""}`, `${vote === "sube" ? "▲ " : vote === "baja" ? "▼ " : ""}${ticker}`);
        chip.title = assetName[ticker] || ticker;
        list.append(chip);
      }
      li.append(label, list);
    }

    const actions = el("div", "mpc-member__actions");
    const follow = el("button", "btn btn--secondary btn--sm", member.following ? "Siguiendo" : "Seguir");
    follow.type = "button";
    follow.setAttribute("aria-pressed", String(member.following));
    follow.dataset.relation = "seguir";
    follow.dataset.target = member.id;
    const state_ = CONNECTION[member.connection] || { label: "Conectar", pressed: false };
    const connect = el("button", "btn btn--secondary btn--sm", state_.label);
    connect.type = "button";
    connect.setAttribute("aria-pressed", String(state_.pressed));
    connect.dataset.relation = "conectar";
    connect.dataset.target = member.id;
    actions.append(follow, connect);
    const hints = [member.followsYou ? "Te sigue" : null, state_.hint || null].filter(Boolean).join(" · ");
    if (hints) actions.append(el("span", "mpc-member__state", hints));
    li.append(actions);
    return li;
  }

  // Estructura de ejemplo cuando no hay base de datos: muestra cómo se verá, sin acciones.
  function placeholderCard() {
    const li = el("li", "mpc-member");
    const head = el("div", "mpc-member__head");
    const who = el("div");
    who.append(el("p", "mpc-member__name", "Perfil público"), el("p", "mpc-member__meta", "Profesión · perfil de interés"));
    head.append(avatar(null, "?", "md"), who);
    const actions = el("div", "mpc-member__actions");
    for (const text of ["Seguir", "Conectar"]) {
      const b = el("button", "btn btn--secondary btn--sm", text);
      b.type = "button";
      b.disabled = true;
      actions.append(b);
    }
    li.append(head, el("p", "mpc-member__bio", "Aquí aparecerán las personas que hagan visible su perfil, con los activos que observan."), actions);
    return li;
  }

  function renderMembers() {
    if (state.mode === "local") {
      ui.members.replaceChildren(placeholderCard());
      ui.membersEmpty.textContent = "Seguir y Conectar se activan cuando haya una base de datos multiusuario conectada.";
      ui.membersEmpty.hidden = false;
      return;
    }
    const query = ui.memberSearch.value.trim().toLowerCase();
    const shown = state.members.filter((m) =>
      !query
        ? true
        : [m.name, m.profession, m.bio, profileName[m.profile], ...m.assets, ...Object.keys(m.votes)]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(query),
    );
    ui.members.replaceChildren(...shown.map(memberCard));
    ui.membersEmpty.hidden = shown.length > 0;
    ui.membersEmpty.textContent = state.members.length
      ? "Nadie coincide con tu búsqueda."
      : "Todavía no hay otros perfiles públicos. Cuando alguien haga visible su perfil, aparecerá aquí.";
  }

  ui.memberSearch.addEventListener("input", renderMembers);

  ui.members.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-relation]");
    if (!button || button.disabled) return;
    const member = state.members.find((m) => m.id === button.dataset.target);
    if (!member) return;
    const kind = button.dataset.relation;
    const active = kind === "seguir" ? !member.following : !(member.connection === "conectados" || member.connection === "enviada");
    button.disabled = true;
    try {
      const data = await api(config.urls.relations, { method: "POST", body: { target: member.id, kind, active } });
      state.members = data.items || [];
      const profile = await api(config.urls.profile);
      state.social = profile.social || state.social;
    } catch (error) {
      ui.membersEmpty.textContent = error.message || "No se pudo actualizar.";
      ui.membersEmpty.hidden = false;
    } finally {
      renderMembers();
      renderPeers();
      renderStats();
    }
  });

  /* ── 3. Notas y reacciones ────────────────────────────────── */
  function noteItem(note, { showAuthor }) {
    const li = el("li", "mpc-note");
    if (showAuthor) li.append(avatar(note.author.avatar, note.author.name, "sm"));
    const body = el("div", "mpc-note__body");
    const head = el("p", "mpc-note__head");
    if (showAuthor) head.append(el("strong", null, note.author.name));
    const link = el("a", null, note.ticker);
    link.href = `${config.urls.community}#sentimiento`;
    link.title = assetName[note.ticker] || note.ticker;
    head.append(link);
    if (note.vote) head.append(el("span", `mpc-vote mpc-vote--${note.vote}`, VOTE_TEXT[note.vote]));
    head.append(el("span", "mpc-note__time", timeAgo(note.created)));
    body.append(head);
    if (note.tag) body.append(el("span", "mpc-note__tag", note.tag));
    if (note.text) body.append(el("p", "mpc-note__text", note.text));
    if (note.mine && !showAuthor) {
      const remove = el("button", "mpc-link", "Quitar");
      remove.type = "button";
      remove.dataset.removeNote = note.ticker;
      body.append(remove);
    }
    li.append(body);
    return li;
  }

  function renderNotes() {
    const mine = state.notes.filter((n) => n.mine);
    ui.myNotes.replaceChildren(
      ...(mine.length ? mine.map((n) => noteItem(n, { showAuthor: false })) : [el("li", "mpc-empty", "Aún no has dejado notas.")]),
    );
    if (state.mode === "local") {
      ui.recentNotes.replaceChildren(el("li", "mpc-empty", "Las notas de otros miembros aparecerán aquí cuando haya base de datos multiusuario."));
    } else {
      const others = state.notes.filter((n) => !n.mine).slice(0, 8);
      ui.recentNotes.replaceChildren(
        ...(others.length ? others.map((n) => noteItem(n, { showAuthor: true })) : [el("li", "mpc-empty", "Todavía no hay notas de otros miembros.")]),
      );
    }
    renderStats();
  }

  function selectNoteTag(tag) {
    state.noteTag = state.noteTag === tag ? "" : tag;
    ui.noteTags.forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.cNoteTag === state.noteTag)));
  }

  ui.noteTags.forEach((chip) => chip.addEventListener("click", () => selectNoteTag(chip.dataset.cNoteTag)));

  // Al elegir un activo con nota propia, se carga para editarla.
  ui.noteAsset.addEventListener("change", () => {
    const mine = state.notes.find((n) => n.mine && n.ticker === ui.noteAsset.value);
    ui.noteText.value = mine?.text || "";
    state.noteTag = "";
    selectNoteTag(mine?.tag || "");
    if (!mine?.tag) selectNoteTag("");
  });

  function localNotes() {
    return Object.entries(store.get(LOCAL_NOTES, {})).map(([ticker, n]) => ({
      ticker,
      tag: n.tag || null,
      text: n.text || null,
      created: n.created,
      vote: state.votes.mine[ticker] || null,
      mine: true,
      author: { name: "Tú", avatar: null },
    }));
  }

  async function writeNote(ticker, { tag, text, remove = false }) {
    const saveLocal = () => {
      const saved = store.get(LOCAL_NOTES, {});
      if (remove) delete saved[ticker];
      else saved[ticker] = { tag: tag || null, text: text || null, created: new Date().toISOString() };
      store.set(LOCAL_NOTES, saved);
      state.notes = localNotes();
    };
    if (state.mode === "local") return saveLocal();
    try {
      const url = remove ? `${config.urls.notes}/${encodeURIComponent(ticker)}` : config.urls.notes;
      await api(url, remove ? { method: "DELETE" } : { method: "POST", body: { ticker, tag: tag || null, text } });
      state.notes = (await api(config.urls.notes)).items || [];
    } catch (error) {
      if (!error.local) throw error;
      goLocal(error);
      saveLocal();
    }
  }

  ui.noteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = ui.noteText.value.trim();
    if (!state.noteTag && !text) {
      ui.noteStatus.textContent = "Elige una reacción rápida o escribe una nota.";
      return;
    }
    ui.noteStatus.textContent = "Guardando…";
    try {
      await writeNote(ui.noteAsset.value, { tag: state.noteTag, text });
      ui.noteStatus.textContent = "Nota guardada.";
      ui.noteText.value = "";
      selectNoteTag("");
      renderNotes();
    } catch (error) {
      ui.noteStatus.textContent = error.message || "No se pudo guardar la nota.";
    }
  });

  ui.myNotes.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-remove-note]");
    if (!button) return;
    button.disabled = true;
    try {
      await writeNote(button.dataset.removeNote, { remove: true });
    } catch (error) {
      ui.noteStatus.textContent = error.message || "No se pudo quitar la nota.";
    }
    renderNotes();
  });

  /* ── Carga inicial ────────────────────────────────────────── */
  function applyProfile(data) {
    state.profile = data.profile || null;
    state.social = data.social || state.social;
  }

  async function loadMembers() {
    if (state.mode === "local") return renderMembers();
    try {
      state.members = (await api(config.urls.members)).items || [];
    } catch {
      state.members = [];
    }
    renderMembers();
    renderPeers();
  }

  async function load() {
    try {
      applyProfile(await api(config.urls.profile));
    } catch (error) {
      goLocal(error);
      state.profile = store.get(LOCAL_PROFILE, null);
    }

    if (state.mode === "server") {
      const [votes, notes] = await Promise.allSettled([api(config.urls.votes), api(config.urls.notes)]);
      if (votes.status === "fulfilled") state.votes = { counts: votes.value.counts || {}, mine: votes.value.mine || {} };
      state.notes = notes.status === "fulfilled" ? notes.value.items || [] : [];
    } else {
      const mine = store.get(LOCAL_VOTES, {});
      state.votes = { counts: {}, mine };
      for (const [t, v] of Object.entries(mine)) state.votes.counts[t] = { sube: 0, baja: 0, [v]: 1 };
      state.notes = localNotes();
    }

    renderIdentity();
    renderCompare();
    renderNotes();
    loadMembers();
  }

  renderIdentity();
  load();
})();
