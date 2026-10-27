/* ==========================================================================
   A²M² — shared behaviour
   Plain ES2019+, no dependencies, no build step.

   Everything here is progressive enhancement: with JavaScript disabled the
   site stays fully readable and navigable.
     - mobile navigation drawer
     - reveal-on-scroll
     - publication filtering (year / type / free text)
     - current year in the footer
   ========================================================================== */

(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  /* ---------------------------------------------------------------------
     Mobile navigation
     --------------------------------------------------------------------- */

  function initNav() {
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("primary-nav");
    if (!toggle || !nav) return;

    var MOBILE = "(max-width: 1000px)";

    function isOpen() {
      return nav.getAttribute("data-open") === "true";
    }

    function setOpen(open) {
      nav.setAttribute("data-open", open ? "true" : "false");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute(
        "aria-label",
        open ? "Close navigation menu" : "Open navigation menu"
      );
      // Stop the page scrolling behind the open drawer.
      document.body.style.overflow = open ? "hidden" : "";
    }

    setOpen(false);

    toggle.addEventListener("click", function () {
      setOpen(!isOpen());
    });

    // Escape closes the drawer and returns focus to the button.
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && isOpen()) {
        setOpen(false);
        toggle.focus();
      }
    });

    // Tapping outside the drawer closes it.
    document.addEventListener("click", function (event) {
      if (!isOpen()) return;
      if (nav.contains(event.target) || toggle.contains(event.target)) return;
      setOpen(false);
    });

    // Following a link closes the drawer (same-page anchors would otherwise
    // leave it covering the content).
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a") && isOpen()) setOpen(false);
    });

    // Reset when the viewport grows past the breakpoint, so the desktop nav
    // never inherits a locked body or a stale state.
    var mq = window.matchMedia(MOBILE);
    var onChange = function (event) {
      if (!event.matches) setOpen(false);
    };
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(onChange);
    }
  }

  /* ---------------------------------------------------------------------
     Reveal on scroll
     Elements marked [data-reveal] fade up as they enter the viewport.
     Siblings inside a [data-reveal-group] are staggered.
     --------------------------------------------------------------------- */

  function initReveal() {
    var targets = Array.prototype.slice.call(
      document.querySelectorAll("[data-reveal]")
    );
    if (!targets.length) return;

    // No observer support, or the user asked for less motion: just show it.
    if (!("IntersectionObserver" in window) || prefersReducedMotion) {
      targets.forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }

    // Stagger each group's children a little.
    document
      .querySelectorAll("[data-reveal-group]")
      .forEach(function (group) {
        Array.prototype.slice
          .call(group.querySelectorAll("[data-reveal]"))
          .forEach(function (el, i) {
            el.style.setProperty("--reveal-delay", Math.min(i, 6) * 70 + "ms");
          });
      });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );

    targets.forEach(function (el) {
      // Anything already on screen at load shows immediately, so the first
      // viewport never looks blank.
      if (el.getBoundingClientRect().top < window.innerHeight * 0.92) {
        el.classList.add("is-visible");
      } else {
        observer.observe(el);
      }
    });
  }

  /* ---------------------------------------------------------------------
     Publication filtering
     --------------------------------------------------------------------- */

  function initPublicationFilter() {
    var root = document.getElementById("pub-results");
    if (!root) return;

    var groups = Array.prototype.slice.call(root.querySelectorAll(".pub-group"));
    var items = Array.prototype.slice.call(root.querySelectorAll(".pub"));
    if (!items.length) return;

    var searchInput = document.getElementById("pub-search");
    var emptyState = document.getElementById("pub-empty");
    var countOutput = document.getElementById("pub-count");
    var chips = Array.prototype.slice.call(
      document.querySelectorAll("[data-filter]")
    );

    // Cache lowercased text once rather than re-reading the DOM per keystroke.
    items.forEach(function (item) {
      item.dataset.haystack = (item.textContent || "").toLowerCase();
    });

    var state = { year: "all", type: "all", query: "" };

    function matches(item) {
      if (state.year !== "all" && item.dataset.year !== state.year) return false;
      if (state.type !== "all" && item.dataset.type !== state.type) return false;
      if (state.query && item.dataset.haystack.indexOf(state.query) === -1) {
        return false;
      }
      return true;
    }

    function apply() {
      var visible = 0;

      items.forEach(function (item) {
        var show = matches(item);
        item.hidden = !show;
        if (show) visible++;
      });

      // Hide a year heading once every entry beneath it is filtered out.
      groups.forEach(function (group) {
        var anyVisible = Array.prototype.slice
          .call(group.querySelectorAll(".pub"))
          .some(function (item) {
            return !item.hidden;
          });
        group.hidden = !anyVisible;
      });

      if (emptyState) emptyState.hidden = visible !== 0;

      if (countOutput) {
        countOutput.textContent =
          visible === items.length
            ? items.length + " publications"
            : visible + " of " + items.length + " publications";
      }
    }

    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var kind = chip.dataset.filter; // "year" | "type"
        var value = chip.dataset.value;

        state[kind] = value;

        // Only one chip per group stays pressed.
        chips
          .filter(function (other) {
            return other.dataset.filter === kind;
          })
          .forEach(function (other) {
            other.setAttribute(
              "aria-pressed",
              other === chip ? "true" : "false"
            );
          });

        apply();
      });
    });

    if (searchInput) {
      var timer = null;
      searchInput.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
          state.query = searchInput.value.trim().toLowerCase();
          apply();
        }, 140);
      });
    }

    apply();
  }

  /* ---------------------------------------------------------------------
     Footer year
     --------------------------------------------------------------------- */

  function initYear() {
    document.querySelectorAll("[data-current-year]").forEach(function (el) {
      el.textContent = String(new Date().getFullYear());
    });
  }

  /* ---------------------------------------------------------------------
     Boot
     --------------------------------------------------------------------- */

  function boot() {
    document.documentElement.classList.remove("no-js");
    initNav();
    initReveal();
    initPublicationFilter();
    initYear();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
