/* Utilidades compartidas por COMUNIDAD y MI PERFIL (window.MoaiCommunity).
 *
 * - el(): crea nodos y escribe texto con textContent (nunca innerHTML).
 * - avatar(): pinta la foto (data URL) o las iniciales con su color.
 * - timeAgo(), plural(): textos legibles.
 * - api(): fetch JSON que marca con .local los fallos que piden modo local
 *   (sin sesión o sin base de datos: respuesta con mode: "local").
 * - store: localStorage tolerante a fallos (modo privado, cuota llena...).
 */
(() => {
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  function initials(name) {
    const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
  }

  /** Avatar circular: foto, iniciales con color o iniciales en gris. */
  function avatar(value, name, size = "md") {
    const node = el("span", `mc-avatar mc-avatar--${size}`);
    node.setAttribute("aria-hidden", "true");
    if (typeof value === "string" && value.startsWith("data:image/")) {
      const img = el("img");
      img.src = value;
      img.alt = "";
      node.append(img);
      return node;
    }
    const color = typeof value === "string" && value.startsWith("iniciales:") ? value.slice(10) : null;
    if (color) {
      node.style.background = color;
      node.style.color = "#fff";
    }
    node.textContent = initials(name);
    return node;
  }

  const dateFmt = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  function timeAgo(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const minutes = Math.round((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return "ahora";
    if (minutes < 60) return `hace ${minutes} min`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `hace ${plural(hours, "hora", "horas")}`;
    return dateFmt.format(date);
  }

  async function api(url, { method = "GET", body } = {}) {
    const response = await fetch(url, {
      method,
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `Error ${response.status}`);
      error.local = data.mode === "local";
      error.status = response.status;
      throw error;
    }
    return data;
  }

  const store = {
    get(key, fallback) {
      try {
        const value = JSON.parse(localStorage.getItem(key) || "null");
        return value ?? fallback;
      } catch {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch {
        /* sin almacenamiento: dura lo que la pestaña */
      }
    },
  };

  window.MoaiCommunity = { el, plural, initials, avatar, timeAgo, api, store };
})();
