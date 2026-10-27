// LegalLens page behaviour. Motion rules are in .ux-profile.md: transform and
// opacity only, and nothing moves on its own under prefers-reduced-motion.
// Document text is never inserted as HTML here; it arrives escaped from the server.
(function () {
  "use strict";

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var main = document.getElementById("content");

  function scrollBehavior() {
    return reducedMotion.matches ? "auto" : "smooth";
  }
  function isTyping(el) {
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  }
  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }
  function toArray(list) {
    return Array.prototype.slice.call(list);
  }

  // ---------- Theme toggle ----------

  var themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    var systemDark = window.matchMedia("(prefers-color-scheme: dark)");
    var root = document.documentElement;
    var currentTheme = function () {
      return root.dataset.theme || (systemDark.matches ? "dark" : "light");
    };
    var syncToggle = function () {
      var dark = currentTheme() === "dark";
      themeToggle.setAttribute("aria-pressed", String(dark));
      themeToggle.title = dark ? "Switch to light theme" : "Switch to dark theme";
    };
    themeToggle.hidden = false;
    syncToggle();
    themeToggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) { /* the choice just won't persist */ }
      syncToggle();
    });
    systemDark.addEventListener("change", syncToggle);
  }

  // ---------- Landing backdrop: fine print drifting past the scan line ----------

  var scanText = document.querySelector(".scan-text");
  var scanline = document.querySelector(".scanline");
  if (scanText && scanline) initScanner(scanText, scanline);

  function initScanner(el, line) {
    var DRIFT_MS = 90000; // one copy's height every 90s
    var first = el.querySelector(".scan-copy");
    var unit = toArray(first.childNodes).map(function (n) { return n.cloneNode(true); });
    var hero = line.parentNode;
    var drift = null, marks = [], mids = [], copyHeight = 1, lineDocY = 0;
    var flaggedCount = 0, running = false, heroVisible = true, builtFor = 0;

    // Two identical copies, each at least a screen tall: drifting up by one copy
    // lands on the same picture, so the loop has no seam.
    function build() {
      if (window.innerWidth === builtFor) return measure();
      builtFor = window.innerWidth;
      while (el.children.length > 1) el.removeChild(el.lastChild);
      first.textContent = "";
      unit.forEach(function (n) { first.appendChild(n.cloneNode(true)); });
      for (var i = 0; i < 12 && first.offsetHeight < window.innerHeight; i++) {
        first.appendChild(document.createTextNode(" "));
        unit.forEach(function (n) { first.appendChild(n.cloneNode(true)); });
      }
      el.appendChild(first.cloneNode(true));
      measure();
    }

    // Layout is read here only, never per frame.
    function measure() {
      copyHeight = first.offsetHeight || 1;
      marks = toArray(el.querySelectorAll(".scan-hit"));
      mids = marks.map(function (m) { return m.offsetTop + m.offsetHeight / 2; });
      lineDocY = line.getBoundingClientRect().top + window.scrollY;
      marks.forEach(function (m) { m.classList.remove("is-flagged"); });
      flaggedCount = 0;
      update();
    }

    // A phrase is flagged exactly when it is above the line. Flagged phrases are the
    // first k in document order, so only those between the old and new k change.
    function update() {
      var offset = drift ? ((drift.currentTime || 0) % DRIFT_MS) / DRIFT_MS * copyHeight : 0;
      var threshold = lineDocY - window.scrollY + offset;
      var lo = 0, hi = mids.length;
      while (lo < hi) {
        var mid = (lo + hi) >> 1;
        if (mids[mid] < threshold) lo = mid + 1; else hi = mid;
      }
      if (lo === flaggedCount) return;
      // The loop wrapping (or a jump in scroll) changes many at once: switch those without the fade.
      var jump = Math.abs(lo - flaggedCount) > 3;
      if (jump) el.classList.add("is-jumping");
      for (var i = Math.min(lo, flaggedCount); i < Math.max(lo, flaggedCount); i++) {
        marks[i].classList.toggle("is-flagged", i < lo);
      }
      flaggedCount = lo;
      if (jump) requestAnimationFrame(function () { el.classList.remove("is-jumping"); });
    }

    function frame() {
      if (!running) return;
      update();
      requestAnimationFrame(frame);
    }
    function setRunning(on) {
      on = on && !document.hidden && heroVisible && !reducedMotion.matches;
      if (drift) {
        if (on) drift.play(); else if (document.hidden) drift.pause();
      }
      if (on && !running) {
        running = true;
        requestAnimationFrame(frame);
      }
      running = on;
    }

    if (!reducedMotion.matches && el.animate) {
      // Web Animations keeps the drift on the compositor; currentTime keeps the flags in step with it.
      drift = el.animate(
        [{ transform: "translate3d(0, 0, 0)" }, { transform: "translate3d(0, -50%, 0)" }],
        { duration: DRIFT_MS, iterations: Infinity }
      );
    }

    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(build, 250);
    });
    // Static (reduced motion, or the hero off screen): scrolling still moves the line.
    window.addEventListener("scroll", function () { if (!running) update(); }, { passive: true });
    document.addEventListener("visibilitychange", function () { setRunning(true); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        heroVisible = entries[0].isIntersecting;
        setRunning(true);
      }).observe(hero);
    }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(build);
    else build();
    setRunning(true);
  }

  // ---------- Navigation menu (narrow screens) ----------

  var navToggle = document.querySelector(".nav-toggle");
  var navLinks = document.getElementById("nav-links");
  if (navToggle && navLinks) {
    var setNavOpen = function (open) {
      navToggle.setAttribute("aria-expanded", String(open));
      navLinks.classList.toggle("is-open", open);
    };
    navToggle.addEventListener("click", function () {
      setNavOpen(navToggle.getAttribute("aria-expanded") !== "true");
    });
    navLinks.addEventListener("click", function (event) {
      if (event.target.closest("a")) setNavOpen(false);
    });
    document.addEventListener("click", function (event) {
      if (!event.target.closest(".site-nav")) setNavOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && navLinks.classList.contains("is-open")) {
        setNavOpen(false);
        navToggle.focus();
      }
    });
  }

  // ---------- Homepage: the lens ----------

  var loupe = document.getElementById("loupe");
  if (loupe) {
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { initLens(loupe); });
    else initLens(loupe);
  }

  function initLens(loupe) {
    var ZOOM = 2;
    var KEY_STEP = 24;
    var FIRST_PASS_MS = 900; // the one documented motion exception
    var STEP_MS = 300;

    var base = loupe.querySelector(".fine-print");
    var lens = loupe.querySelector(".lens");
    var view = lens.querySelector(".lens-view");
    var copy = view.querySelector(".fine-print");
    var tag = document.getElementById("lens-tag");
    var tagTier = tag.querySelector(".lens-tag-tier");
    var tagNote = tag.querySelector(".lens-tag-note");
    var side = document.querySelector(".lens-side");
    var controls = document.querySelector(".lens-controls");

    var width = 0, height = 0, radius = 0;
    var clauses = [], flags = [], flagIndex = -1;
    var pos = { x: 0, y: 0 };
    var queued = false, glide = null, shown = null;

    function measure() {
      width = base.offsetWidth;
      height = base.offsetHeight;
      radius = lens.offsetWidth / 2;
      copy.style.width = width + "px";
      var origin = loupe.getBoundingClientRect();
      clauses = toArray(base.querySelectorAll(".fp-clause")).map(function (el) {
        return { el: el, top: el.offsetTop, bottom: el.offsetTop + el.offsetHeight };
      });
      flags = clauses.filter(function (c) { return c.el.dataset.tier !== "none"; }).map(function (c) {
        // Aim at the first matched phrase: that is what the lens should show.
        var mark = c.el.querySelector("mark.hit");
        var box = (mark || c.el).getClientRects()[0];
        return {
          clause: c,
          x: box.left - origin.left + box.width / 2,
          y: box.top - origin.top + box.height / 2,
        };
      });
    }

    function render() {
      queued = false;
      lens.style.transform = "translate(" + (pos.x - radius) + "px," + (pos.y - radius) + "px)";
      view.style.transform =
        "translate(" + (radius - pos.x * ZOOM) + "px," + (radius - pos.y * ZOOM) + "px) scale(" + ZOOM + ")";
      showClauseAt(pos.y);
    }

    function moveTo(x, y) {
      pos.x = clamp(x, 0, width);
      pos.y = clamp(y, 0, height);
      if (!queued) {
        queued = true;
        requestAnimationFrame(render);
      }
    }

    function stopGlide() {
      if (glide) cancelAnimationFrame(glide);
      glide = null;
    }

    function glideTo(x, y, duration) {
      stopGlide();
      if (reducedMotion.matches || !duration) return moveTo(x, y);
      var fromX = pos.x, fromY = pos.y, start = null;
      function frame(now) {
        if (start === null) start = now;
        var p = Math.min(1, (now - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        pos.x = fromX + (x - fromX) * eased;
        pos.y = fromY + (y - fromY) * eased;
        render();
        glide = p < 1 ? requestAnimationFrame(frame) : null;
      }
      glide = requestAnimationFrame(frame);
    }

    // The margin tag names the clause under the lens and sits level with it.
    function showClauseAt(y) {
      var hit = null;
      for (var i = 0; i < clauses.length; i++) {
        if (y >= clauses[i].top && y < clauses[i].bottom) { hit = clauses[i]; break; }
      }
      if (!hit || hit === shown) return;
      shown = hit;
      var d = hit.el.dataset;
      tag.className = "lens-tag tier-" + d.tier;
      tagTier.textContent = d.tier === "none" ? "" : d.tierLabel;
      tagNote.textContent = d.tier === "none" ? "No watched phrases in this clause." : d.note;
      var room = side.offsetHeight - controls.offsetHeight - tag.offsetHeight - 16;
      tag.style.setProperty("--tag-y", clamp(hit.top, 0, Math.max(0, room)) + "px");
    }

    function stepFlag(dir) {
      if (!flags.length) return;
      if (flagIndex < 0) {
        // Continue from wherever the lens is: k is the last flag at or above it.
        var k = -1;
        for (var i = 0; i < flags.length; i++) if (flags[i].y <= pos.y + 1) k = i;
        flagIndex = dir > 0 ? k : k + 1;
      }
      flagIndex = (flagIndex + dir + flags.length) % flags.length;
      glideTo(flags[flagIndex].x, flags[flagIndex].y, STEP_MS);
    }

    loupe.addEventListener("pointermove", function (event) {
      if (event.pointerType === "touch") return; // touch scrolls the page; tap places the lens
      var origin = loupe.getBoundingClientRect();
      stopGlide();
      flagIndex = -1;
      loupe.classList.add("is-tracking");
      moveTo(event.clientX - origin.left, event.clientY - origin.top);
    });
    loupe.addEventListener("pointerleave", function () {
      loupe.classList.remove("is-tracking");
    });
    loupe.addEventListener("pointerdown", function (event) {
      if (event.pointerType !== "touch") return;
      var origin = loupe.getBoundingClientRect();
      flagIndex = -1;
      glideTo(event.clientX - origin.left, event.clientY - origin.top, STEP_MS);
    });
    loupe.addEventListener("keydown", function (event) {
      var dx = { ArrowLeft: -1, ArrowRight: 1 }[event.key] || 0;
      var dy = { ArrowUp: -1, ArrowDown: 1 }[event.key] || 0;
      if (!dx && !dy) return;
      event.preventDefault();
      stopGlide();
      flagIndex = -1;
      moveTo(pos.x + dx * KEY_STEP, pos.y + dy * KEY_STEP);
    });
    toArray(document.querySelectorAll("[data-lens-step]")).forEach(function (button) {
      button.addEventListener("click", function () { stepFlag(Number(button.dataset.lensStep)); });
    });

    if ("ResizeObserver" in window) {
      new ResizeObserver(function () {
        measure();
        shown = null;
        moveTo(pos.x, pos.y);
      }).observe(loupe);
    }

    measure();
    // Park on automatic renewal: a flag everyone recognises, and high enough on the sheet to be in view.
    var park = flags.filter(function (f) { return /automatic renewal/i.test(f.clause.el.dataset.note); })[0] || flags[0];
    if (!park) return;
    flagIndex = flags.indexOf(park);
    if (reducedMotion.matches) {
      moveTo(park.x, park.y);
    } else {
      // One pass on load: the lens reads down from the title to the flag.
      moveTo(width * 0.3, 0);
      setTimeout(function () {
        if (!loupe.classList.contains("is-tracking")) glideTo(park.x, park.y, FIRST_PASS_MS);
      }, 300);
    }
  }

  // ---------- Upload ----------

  var loading = document.getElementById("loading");
  toArray(document.querySelectorAll(".js-analyze-form")).forEach(function (form) {
    form.addEventListener("submit", function () {
      // The browser keeps this page up until the results arrive. Fast reviews
      // show nothing; slower ones show a skeleton of the results page after 100ms.
      toArray(document.querySelectorAll(".js-analyze-form button[type=submit]")).forEach(function (b) {
        b.disabled = true;
      });
      setTimeout(function () {
        main.classList.add("is-submitting");
        main.setAttribute("aria-busy", "true");
        loading.hidden = false;
        if (form.id === "upload-form") loading.scrollIntoView({ block: "nearest", behavior: scrollBehavior() });
      }, 100);
    });
  });

  // Coming back with the Back button can restore this page from cache mid-load.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted || !loading) return;
    main.classList.remove("is-submitting");
    main.removeAttribute("aria-busy");
    loading.hidden = true;
    toArray(document.querySelectorAll(".js-analyze-form button[type=submit]")).forEach(function (b) {
      b.disabled = false;
    });
  });

  var dropzone = document.getElementById("dropzone");
  if (dropzone) {
    var fileInput = document.getElementById("file-input");
    var fileName = document.getElementById("file-name");
    var fileStatus = document.getElementById("file-status");

    var showFile = function () {
      var file = fileInput.files && fileInput.files[0];
      dropzone.classList.toggle("has-file", Boolean(file));
      fileName.textContent = file ? file.name : "";
      fileStatus.textContent = file ? "Selected " + file.name : "";
    };
    fileInput.addEventListener("change", showFile);
    window.addEventListener("pageshow", showFile);

    // Only real file drags light the zone up; text dragged from the page does not.
    var isFileDrag = function (event) {
      return toArray(event.dataTransfer.types).indexOf("Files") !== -1;
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
        fileInput.files = transfer.files;
        showFile();
      }
    });
  }

  // ---------- Results: the annotated document ----------

  var reader = document.getElementById("reader");
  if (reader) initReader(reader);

  function initReader(reader) {
    var rows = toArray(reader.querySelectorAll(".row"));
    var clauseRows = rows.filter(function (r) { return r.classList.contains("row-clause"); });
    var ticks = toArray(reader.querySelectorAll(".tick"));
    var track = reader.querySelector(".rail-track");
    var railWindow = reader.querySelector(".rail-window");
    var doc = reader.querySelector(".doc");
    var toolbar = document.getElementById("toolbar");
    var status = document.getElementById("reader-status");
    var count = document.getElementById("flag-count");
    var foldToggle = document.getElementById("fold-toggle");
    var filters = toArray(document.querySelectorAll(".filter[data-filter]"));
    var current = null;

    function flagged() {
      return clauseRows.filter(function (r) { return r.dataset.tier !== "none" && !r.hidden; });
    }

    function describe(row) {
      var labels = toArray(row.querySelectorAll(".note-label")).map(function (el) { return el.textContent; });
      var tier = row.dataset.tier === "none" ? "" : ", " + row.getAttribute("aria-label").split(", ").pop();
      return row.dataset.ref + tier + (labels.length ? ": " + labels.join(", ") : "");
    }

    function updateCount() {
      if (!count) return;
      var list = flagged();
      var i = list.indexOf(current);
      count.textContent = i >= 0 ? "Flag " + (i + 1) + " of " + list.length : list.length + " flagged";
    }

    function unfold(row) {
      row.classList.remove("is-folded");
      row.querySelector(".row-stub").hidden = true;
    }

    function setCurrent(row, options) {
      options = options || {};
      if (current) current.classList.remove("is-current");
      current = row;
      reader.classList.toggle("has-current", Boolean(row));
      if (row) {
        if (row.classList.contains("is-folded")) unfold(row);
        row.classList.add("is-current");
        if (options.scroll) row.scrollIntoView({ block: "center", behavior: scrollBehavior() });
        if (options.focus) row.focus({ preventScroll: true });
        if (options.announce) status.textContent = describe(row);
      }
      updateCount();
    }

    function step(dir) {
      var list = flagged();
      if (!list.length) return;
      var i = list.indexOf(current);
      var next;
      if (i >= 0) {
        next = list[(i + dir + list.length) % list.length];
      } else {
        // From an unflagged clause or nothing: the next flag in reading order.
        var from = current ? rows.indexOf(current) : -1;
        var ahead = list.filter(function (r) { return dir > 0 ? rows.indexOf(r) > from : from < 0 || rows.indexOf(r) < from; });
        next = dir > 0 ? (ahead[0] || list[0]) : (ahead[ahead.length - 1] || list[list.length - 1]);
      }
      setCurrent(next, { scroll: true, focus: true, announce: true });
    }

    toArray(document.querySelectorAll("[data-step]")).forEach(function (button) {
      button.addEventListener("click", function () { step(Number(button.dataset.step)); });
    });

    document.addEventListener("keydown", function (event) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (event.key === "j") step(1);
      else if (event.key === "k") step(-1);
      else if (event.key === "Escape" && current) setCurrent(null);
    });

    clauseRows.forEach(function (row) {
      row.addEventListener("click", function (event) {
        if (event.target.closest("a, button") || window.getSelection().toString()) return;
        setCurrent(row === current ? null : row);
      });
      row.querySelector(".row-stub").addEventListener("click", function () {
        unfold(row);
        setCurrent(row, { focus: true });
        layout();
      });
    });

    toArray(document.querySelectorAll("[data-goto]")).forEach(function (link) {
      link.addEventListener("click", function (event) {
        var row = document.getElementById("clause-" + link.dataset.goto);
        if (!row) return;
        event.preventDefault();
        if (row.hidden) applyFilter(filters[0]);
        setCurrent(row, { scroll: true, focus: true, announce: true });
      });
    });

    // Filters hide whole rows; headings between clauses only show with "All".
    function applyFilter(button) {
      var tier = button.dataset.filter;
      filters.forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
      rows.forEach(function (row, i) {
        var show = tier === "all" || row.dataset.tier === tier;
        row.hidden = !show;
        if (ticks[i]) ticks[i].hidden = !show;
      });
      if (current && current.hidden) setCurrent(null);
      var shown = clauseRows.filter(function (r) { return !r.hidden; }).length;
      status.textContent = tier === "all"
        ? "Showing all " + clauseRows.length + " clauses."
        : "Showing " + shown + " of " + clauseRows.length + " clauses: " + button.dataset.label + ".";
      updateCount();
      layout();
    }
    filters.forEach(function (button) {
      button.addEventListener("click", function () { applyFilter(button); });
    });

    if (foldToggle) {
      foldToggle.addEventListener("click", function () {
        var fold = foldToggle.getAttribute("aria-pressed") !== "true";
        foldToggle.setAttribute("aria-pressed", String(fold));
        clauseRows.forEach(function (row) {
          if (row.dataset.tier !== "none") return;
          row.classList.toggle("is-folded", fold);
          row.querySelector(".row-stub").hidden = !fold;
        });
        if (fold && current && current.dataset.tier === "none") setCurrent(null);
        status.textContent = fold ? "Unflagged clauses are folded." : "All clauses are shown in full.";
        layout();
      });
    }

    // Minimap: each tick is as tall as its row, so the window maps onto the page exactly.
    var railQueued = false;
    function layout() {
      document.documentElement.style.setProperty("--toolbar-h", toolbar.offsetHeight + "px");
      rows.forEach(function (row, i) {
        if (ticks[i]) ticks[i].style.flexGrow = String(row.offsetHeight);
      });
      placeWindow();
    }
    function placeWindow() {
      railQueued = false;
      if (!track || !track.offsetHeight) return;
      var box = doc.getBoundingClientRect();
      var top = toolbar.offsetHeight;
      var scale = track.offsetHeight / box.height;
      var seen = Math.max(0, top - box.top);
      var h = Math.min(track.offsetHeight, (window.innerHeight - top) * scale);
      railWindow.style.height = h + "px";
      railWindow.style.transform = "translateY(" + clamp(seen * scale, 0, track.offsetHeight - h) + "px)";
    }
    window.addEventListener("scroll", function () {
      if (!railQueued) {
        railQueued = true;
        requestAnimationFrame(placeWindow);
      }
    }, { passive: true });
    window.addEventListener("resize", layout);
    ticks.forEach(function (tick) {
      tick.addEventListener("click", function () {
        var row = rows[Number(tick.dataset.row)];
        if (row.classList.contains("row-clause")) setCurrent(row, { scroll: true, focus: true, announce: true });
        else row.scrollIntoView({ block: "center", behavior: scrollBehavior() });
      });
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(layout);
    layout();
  }

  // ---------- Results: print summary and JSON export ----------

  var printButton = document.getElementById("print-summary");
  if (printButton) printButton.addEventListener("click", function () { window.print(); });

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
