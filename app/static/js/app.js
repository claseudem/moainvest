/**
 * Front-end de la vista de dashboard: dibuja el gráfico de velas (con la
 * librería lightweight-charts de TradingView) y mantiene precios en vivo
 * en la cabecera y en el sidebar, todo alimentado por la API JSON de
 * `app/controllers/api.py`.
 */
(function () {
  "use strict";

  const QUOTE_POLL_MS = 15000;

  function fmtPrice(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }

  function fmtChange(quote) {
    if (quote.change === null || quote.change === undefined) return "—";
    const sign = quote.change >= 0 ? "+" : "";
    return `${sign}${fmtPrice(quote.change)} (${sign}${quote.change_percent.toFixed(2)}%)`;
  }

  function applyUpDown(el, isUp) {
    el.classList.remove("is-up", "is-down");
    el.classList.add(isUp ? "is-up" : "is-down");
  }

  // ---------------------------------------------------------------------
  // Sidebar: colapsar/expandir panel completo y secciones individuales
  // ---------------------------------------------------------------------
  function initSidebar() {
    const layout = document.querySelector(".layout");
    const toggleBtn = document.getElementById("sidebar-toggle");
    if (toggleBtn) {
      const collapsed = localStorage.getItem("sidebar-collapsed") === "1";
      layout.classList.toggle("is-sidebar-collapsed", collapsed);
      toggleBtn.addEventListener("click", () => {
        const isCollapsed = layout.classList.toggle("is-sidebar-collapsed");
        localStorage.setItem("sidebar-collapsed", isCollapsed ? "1" : "0");
      });
    }

    document.querySelectorAll(".sidebar__section").forEach((section) => {
      const header = section.querySelector(".sidebar__section-header");
      const list = section.querySelector(".sidebar__symbols");
      if (!header || !list) return;
      header.addEventListener("click", (event) => {
        if (section.classList.contains("is-active")) {
          // Ya estamos en esta watchlist: solo alternamos visibilidad, sin recargar.
          event.preventDefault();
          list.hidden = !list.hidden;
        }
        // Si no está activa, se deja navegar con el <a> normal.
      });
    });
  }

  function pollSidebarQuotes() {
    const activeList = document.querySelector(".sidebar__symbols:not([hidden])");
    if (!activeList) return;
    const slug = activeList.dataset.watchlistSlug;
    fetch(`/api/watchlist/${encodeURIComponent(slug)}/quotes`)
      .then((res) => res.json())
      .then((quotes) => {
        activeList.querySelectorAll("a[data-ticker]").forEach((link) => {
          const quote = quotes[link.dataset.ticker];
          if (!quote) return;
          link.querySelector("[data-price]").textContent = fmtPrice(quote.price);
          const changeEl = link.querySelector("[data-change]");
          changeEl.textContent =
            quote.change_percent === null || quote.change_percent === undefined
              ? "—"
              : `${quote.change_percent >= 0 ? "+" : ""}${quote.change_percent.toFixed(2)}%`;
          applyUpDown(changeEl, quote.is_up);
        });
      })
      .catch(() => {
        /* si Yahoo Finance falla, dejamos los últimos valores mostrados */
      });
  }

  // ---------------------------------------------------------------------
  // Página de gráfico
  // ---------------------------------------------------------------------
  function initChartPage() {
    const page = document.getElementById("chart-page");
    if (!page) return;

    const ticker = page.dataset.ticker;
    const container = document.getElementById("chart-container");
    const loadingEl = document.getElementById("chart-loading");
    const lastPriceEl = document.getElementById("last-price");
    const priceDeltaEl = document.getElementById("price-delta");
    const toolbar = document.getElementById("range-toolbar");

    const chart = LightweightCharts.createChart(container, {
      layout: {
        background: { color: "#ffffff" },
        textColor: "#6b7280",
      },
      grid: {
        vertLines: { color: "#f1f3f5" },
        horzLines: { color: "#f1f3f5" },
      },
      rightPriceScale: { borderColor: "#e5e7eb" },
      timeScale: { borderColor: "#e5e7eb", timeVisible: true, secondsVisible: false },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#0f8a5f",
      downColor: "#d93025",
      borderVisible: false,
      wickUpColor: "#0f8a5f",
      wickDownColor: "#d93025",
    });

    new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    }).observe(container);

    function loadCandles(range, interval) {
      loadingEl.hidden = false;
      fetch(`/api/candles/${encodeURIComponent(ticker)}?range=${range}&interval=${interval}`)
        .then((res) => res.json())
        .then((candles) => {
          series.setData(candles);
          chart.timeScale().fitContent();
        })
        .finally(() => {
          loadingEl.hidden = true;
        });
    }

    function loadQuote() {
      fetch(`/api/quote/${encodeURIComponent(ticker)}`)
        .then((res) => res.json())
        .then((quote) => {
          lastPriceEl.textContent = fmtPrice(quote.price);
          priceDeltaEl.textContent = fmtChange(quote);
          applyUpDown(priceDeltaEl, quote.is_up);
        })
        .catch(() => {});
    }

    if (toolbar) {
      toolbar.addEventListener("click", (event) => {
        const btn = event.target.closest(".chart-toolbar__btn");
        if (!btn) return;
        toolbar.querySelectorAll(".chart-toolbar__btn").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        loadCandles(btn.dataset.range, btn.dataset.interval);
      });
    }

    const initialBtn = toolbar ? toolbar.querySelector(".chart-toolbar__btn.is-active") : null;
    loadCandles(initialBtn ? initialBtn.dataset.range : "1mo", initialBtn ? initialBtn.dataset.interval : "1d");
    loadQuote();
    setInterval(loadQuote, QUOTE_POLL_MS);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initSidebar();
    initChartPage();
    pollSidebarQuotes();
    setInterval(pollSidebarQuotes, QUOTE_POLL_MS);
  });
})();
