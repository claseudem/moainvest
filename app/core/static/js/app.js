/**
 * Comportamiento común de las páginas del área App (core/base.html):
 * - en escritorio, colapsar y expandir el sidebar, recordando la preferencia
 *   en localStorage;
 * - en móvil, abrir y cerrar el sidebar como cajón desde el botón de menú de
 *   la barra superior (se cierra con el fondo, con Escape o al navegar);
 * - cerrar los avisos flash (botón ✕, o solos a los 6 s si no son errores).
 */
(function () {
  "use strict";

  const MOBILE = window.matchMedia("(max-width: 760px)");

  function readCollapsed() {
    try {
      return localStorage.getItem("sidebar-collapsed") === "1";
    } catch (e) {
      return false;
    }
  }

  function saveCollapsed(value) {
    try {
      localStorage.setItem("sidebar-collapsed", value ? "1" : "0");
    } catch (e) {
      /* sin almacenamiento: la preferencia dura lo que la página */
    }
  }

  function initSidebar() {
    const layout = document.querySelector(".layout");
    const toggleBtn = document.getElementById("sidebar-toggle");
    if (!layout || !toggleBtn) return;
    const openBtn = document.getElementById("sidebar-open");
    const backdrop = document.querySelector("[data-sidebar-close]");

    function setCollapsed(collapsed) {
      layout.classList.toggle("is-sidebar-collapsed", collapsed);
      toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      toggleBtn.setAttribute("aria-label", collapsed ? "Expandir sidebar" : "Colapsar sidebar");
    }

    function setDrawer(open) {
      layout.classList.toggle("is-sidebar-open", open);
      if (backdrop) backdrop.hidden = !open;
      if (openBtn) {
        openBtn.setAttribute("aria-expanded", open ? "true" : "false");
        openBtn.setAttribute("aria-label", open ? "Cerrar menú de la app" : "Abrir menú de la app");
      }
    }

    setCollapsed(readCollapsed());

    toggleBtn.addEventListener("click", () => {
      const collapsed = !layout.classList.contains("is-sidebar-collapsed");
      setCollapsed(collapsed);
      saveCollapsed(collapsed);
    });

    if (openBtn) {
      openBtn.addEventListener("click", () => setDrawer(!layout.classList.contains("is-sidebar-open")));
    }
    if (backdrop) backdrop.addEventListener("click", () => setDrawer(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && layout.classList.contains("is-sidebar-open")) {
        setDrawer(false);
        if (openBtn) openBtn.focus();
      }
    });
    // Al pasar a escritorio el cajón deja de tener sentido.
    MOBILE.addEventListener("change", (event) => {
      if (!event.matches) setDrawer(false);
    });
  }

  function initFlashes() {
    const box = document.querySelector("[data-app-flashes]");
    if (!box) return;
    const dismiss = (flash) => {
      flash.remove();
      if (!box.children.length) box.remove();
    };
    box.querySelectorAll(".app-flash").forEach((flash) => {
      flash.querySelector("[data-flash-close]").addEventListener("click", () => dismiss(flash));
      if (flash.dataset.tone !== "error") setTimeout(() => dismiss(flash), 6000);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initSidebar();
    initFlashes();
  });
})();
