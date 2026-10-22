// LegalLens page behaviour. Motion follows DESIGN.md and is skipped under
// prefers-reduced-motion. Document text is never inserted as HTML here; it
// arrives escaped from the server.
(function () {
  "use strict";

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var DUR_BASE = 220;
  var EASE_OUT = "cubic-bezier(0.2, 0.7, 0.2, 1)";
  var EASE_IN_OUT = "cubic-bezier(0.6, 0, 0.3, 1)";
  var main = document.getElementById("content");

  function scrollBehavior() {
    return reducedMotion.matches ? "auto" : "smooth";
  }

  // ---------- Reveal on scroll ----------

  var onReveal = []; // callbacks run when a [data-reveal] element first appears
  var revealables = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && !reducedMotion.matches) {
    var revealer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        revealer.unobserve(entry.target);
        onReveal.forEach(function (fn) { fn(entry.target); });
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    revealables.forEach(function (el) { revealer.observe(el); });
  } else {
    revealables.forEach(function (el) { el.classList.add("is-visible"); });
    window.addEventListener("DOMContentLoaded", function () {
      revealables.forEach(function (el) { onReveal.forEach(function (fn) { fn(el); }); });
    });
  }

  // ---------- Upload page ----------

  var loading = document.getElementById("loading");
  document.querySelectorAll(".js-analyze-form").forEach(function (form) {
    form.addEventListener("submit", function () {
      // The browser keeps this page up until the results arrive; show a
      // skeleton instead. Inputs stay enabled so their values are submitted.
      main.classList.add("is-submitting");
      main.setAttribute("aria-busy", "true");
      loading.hidden = false;
      document.querySelectorAll(".js-analyze-form button[type=submit]").forEach(function (b) { b.disabled = true; });
      var status = document.getElementById("file-status");
      if (status) status.textContent = "Reviewing your document…";
      loading.scrollIntoView({ block: "center", behavior: scrollBehavior() });
    });
  });

  // Coming back with the Back button can restore this page from cache mid-load.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted || !loading) return;
    main.classList.remove("is-submitting");
    main.removeAttribute("aria-busy");
    loading.hidden = true;
    document.querySelectorAll(".js-analyze-form button[type=submit]").forEach(function (b) { b.disabled = false; });
  });

  var dropzone = document.getElementById("dropzone");
  if (dropzone) {
    var input = document.getElementById("file-input");
    var fileName = document.getElementById("file-name");
    var fileStatus = document.getElementById("file-status");

    var showFile = function () {
      var file = input.files && input.files[0];
      dropzone.classList.toggle("has-file", Boolean(file));
      fileName.textContent = file ? file.name : "";
      fileStatus.textContent = file ? "Selected " + file.name : "";
    };
    input.addEventListener("change", showFile);
    window.addEventListener("pageshow", showFile);

    // Only real file drags light the zone up; text dragged from the page does not.
    var isFileDrag = function (event) {
      return Array.prototype.indexOf.call(event.dataTransfer.types, "Files") !== -1;
    };
    var depth = 0;
    dropzone.addEventListener("dragenter", function (event) {
      if (!isFileDrag(event)) return;
      event.preventDefault();
      depth += 1;
      dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragover", function (event) {
      if (!isFileDrag(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    });
    dropzone.addEventListener("dragleave", function () {
      depth = Math.max(0, depth - 1);
      if (depth === 0) dropzone.classList.remove("is-dragover");
    });
    dropzone.addEventListener("drop", function (event) {
      if (!isFileDrag(event)) return;
      event.preventDefault();
      depth = 0;
      dropzone.classList.remove("is-dragover");
      if (event.dataTransfer.files.length) {
        var transfer = new DataTransfer();
        transfer.items.add(event.dataTransfer.files[0]);
        input.files = transfer.files;
        showFile();
      }
    });
  }

  // ---------- Results: risk overview ----------

  function countUp(el) {
    var target = Number(el.dataset.count);
    if (reducedMotion.matches || !target) return;
    var start = null;
    var duration = 900;
    el.textContent = "0";
    function tick(now) {
      if (start === null) start = now;
      var p = Math.min(1, (now - start) / duration);
      el.textContent = String(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  onReveal.push(function (el) {
    if (el.classList.contains("risk-summary")) el.querySelectorAll(".count[data-count]").forEach(countUp);
  });

  // ---------- Results: marker-sweep highlights ----------

  var marks = document.querySelectorAll("mark.span");
  function settle(mark) {
    mark.classList.add("is-inked");
    var done = function () { mark.classList.add("is-settled"); };
    if (reducedMotion.matches) return done();
    mark.addEventListener("transitionend", done, { once: true });
    setTimeout(done, 900); // in case the transition never fires (e.g. already drawn)
  }
  if ("IntersectionObserver" in window && !reducedMotion.matches) {
    var inker = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        inker.unobserve(entry.target);
        settle(entry.target);
      });
    }, { threshold: 0.2 });
    marks.forEach(function (m) { inker.observe(m); });
  } else {
    marks.forEach(settle);
  }

  // ---------- Results: clause cards ----------

  var cards = document.querySelectorAll(".clause-card");
  var expanded = null;
  var running = new WeakMap(); // element -> its current WAAPI animation

  function play(el, keyframes, duration, easing, done) {
    // A new animation replaces the old one; cancel() skips its onfinish, so a
    // stale collapse or fade-out can't undo a newer state.
    if (running.has(el)) running.get(el).cancel();
    if (reducedMotion.matches || !el.animate) {
      if (done) done();
      return;
    }
    var animation = el.animate(keyframes, { duration: duration, easing: easing });
    running.set(el, animation);
    animation.onfinish = function () {
      running.delete(el);
      if (done) done();
    };
  }

  function setExpanded(card, open) {
    var body = card.querySelector(".clause-body");
    var toggle = card.querySelector(".clause-toggle");
    var from = body.getBoundingClientRect().height;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) {
      card.classList.remove("is-collapsing");
      card.classList.add("is-expanded");
      var to = body.getBoundingClientRect().height;
      play(body, [{ height: from + "px" }, { height: to + "px" }], DUR_BASE, EASE_OUT);
    } else {
      // Measure the preview, but keep the full text while the card shrinks.
      card.classList.remove("is-expanded");
      var target = body.getBoundingClientRect().height;
      card.classList.add("is-expanded", "is-collapsing");
      play(body, [{ height: from + "px" }, { height: target + "px" }], DUR_BASE, EASE_IN_OUT, function () {
        card.classList.remove("is-expanded", "is-collapsing");
      });
    }
  }

  function clearActiveMark() {
    document.querySelectorAll("mark.span.active").forEach(function (el) { el.classList.remove("active"); });
  }

  function select(index, from) {
    var card = document.querySelector('.clause-card[data-clause="' + index + '"]');
    clearActiveMark();
    if (expanded && expanded !== card) setExpanded(expanded, false);
    if (expanded === card) {
      setExpanded(card, false);
      expanded = null;
      return;
    }
    expanded = card;
    setExpanded(card, true);
    var span = document.getElementById("span-" + index);
    if (span) {
      settle(span);
      span.classList.add("active");
      if (from === "card") span.scrollIntoView({ block: "center", behavior: scrollBehavior() });
    }
    if (from === "text") card.scrollIntoView({ block: "nearest", behavior: scrollBehavior() });
  }

  document.querySelectorAll(".clause-toggle").forEach(function (toggle) {
    toggle.addEventListener("click", function () { select(toggle.dataset.clause, "card"); });
  });
  // Clicking the text also toggles, as a larger mouse target; keyboard users use the button.
  document.querySelectorAll(".clause-body").forEach(function (body) {
    body.addEventListener("click", function () {
      if (window.getSelection().toString()) return; // let people select text
      select(body.closest(".clause-card").dataset.clause, "card");
    });
  });
  marks.forEach(function (span) {
    span.addEventListener("click", function () {
      if (window.getSelection().toString()) return;
      var card = document.querySelector('.clause-card[data-clause="' + span.dataset.clause + '"]');
      var item = card && card.closest(".clause");
      if (card === expanded || (item && item.hidden)) return;
      select(span.dataset.clause, "text");
    });
  });

  // ---------- Results: tier filters ----------

  var filters = document.querySelectorAll(".filter");
  var items = document.querySelectorAll(".clause");
  var filterStatus = document.getElementById("filter-status");
  filters.forEach(function (button) {
    button.addEventListener("click", function () {
      var tier = button.dataset.filter;
      filters.forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
      var shown = 0;
      items.forEach(function (li) {
        var match = tier === "all" || li.dataset.tier === tier;
        if (match) shown += 1;
        if (match && li.hidden) {
          li.hidden = false;
          play(li, [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], DUR_BASE, EASE_OUT);
        } else if (!match && !li.hidden) {
          var card = li.querySelector(".clause-card");
          if (card === expanded) {
            setExpanded(card, false);
            expanded = null;
            clearActiveMark();
          }
          play(li, [{ opacity: 1 }, { opacity: 0, transform: "translateY(4px)" }], 160, EASE_OUT, function () {
            li.hidden = true;
          });
        }
      });
      var name = button.childNodes[0].textContent.trim();
      filterStatus.textContent = tier === "all"
        ? "Showing all " + items.length + " clauses."
        : "Showing " + shown + " of " + items.length + " clauses: " + name + ".";
    });
  });

  // ---------- Results: print summary ----------

  var printButton = document.getElementById("print-summary");
  if (printButton) printButton.addEventListener("click", function () { window.print(); });

  // ---------- Results: JSON export ----------

  var download = document.getElementById("download-json");
  var data = document.getElementById("result-data");
  if (download && data) {
    download.addEventListener("click", function () {
      var result = JSON.parse(data.textContent);
      var blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = result.source.replace(/\.[^.]+$/, "") + ".clauses.json";
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }
})();
