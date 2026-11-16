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

  // ---------- Upload ----------

  var loading = document.getElementById("loading");
  var uploadError = document.getElementById("upload-error");
  // The upload form needs exactly one of a file or pasted text; say so here instead of a round trip.
  function uploadProblem(form) {
    var file = form.querySelector("input[type=file]");
    var area = form.querySelector("textarea[name=text]");
    var hasFile = Boolean(file && file.files && file.files.length);
    var hasText = Boolean(area && area.value.trim());
    if (!hasFile && !hasText) return "Choose a file or paste your policy text.";
    if (hasFile && hasText) return "Choose a file or paste text, not both. Clear one to continue.";
    return "";
  }
  var uploadForm = document.getElementById("upload-form");
  if (uploadForm && uploadError) {
    ["input", "change"].forEach(function (type) {
      uploadForm.addEventListener(type, function () { uploadError.textContent = ""; });
    });
  }
  toArray(document.querySelectorAll(".js-analyze-form")).forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.id === "upload-form" && uploadError) {
        var problem = uploadProblem(form);
        if (problem) {
          event.preventDefault();
          uploadError.textContent = problem;
          var area = form.querySelector("textarea[name=text]");
          if (area) area.focus();
          return;
        }
      }
      // The browser keeps this page up until the results arrive. Fast reviews
      // show nothing; slower ones show a skeleton of the results page after 300ms.
      toArray(document.querySelectorAll(".js-analyze-form button[type=submit]")).forEach(function (b) {
        b.disabled = true;
      });
      setTimeout(function () {
        main.classList.add("is-submitting");
        main.setAttribute("aria-busy", "true");
        loading.hidden = false;
        if (form.id === "upload-form") loading.scrollIntoView({ block: "nearest", behavior: scrollBehavior() });
      }, 300);
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

  // ---------- Results: copy wording ----------

  var copyStatus = document.getElementById("copy-status");
  function announceCopy(message) {
    if (!copyStatus) return;
    copyStatus.textContent = "";
    setTimeout(function () { copyStatus.textContent = message; }, 50);
  }
  function selectText(el) {
    var range = document.createRange();
    range.selectNodeContents(el);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  toArray(document.querySelectorAll(".copy-button[data-copy]")).forEach(function (button) {
    var source = document.getElementById(button.dataset.copy);
    if (!source) return;
    button.hidden = false;
    button.addEventListener("click", function () {
      var done = function () {
        button.textContent = "Copied";
        announceCopy("Wording copied.");
        setTimeout(function () { button.textContent = "Copy wording"; }, 2000);
      };
      // Without clipboard access (an insecure origin or a blocked permission), select the text instead.
      var fallback = function () {
        selectText(source);
        announceCopy("Wording selected. Press Control C, or Command C on a Mac, to copy it.");
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(source.textContent.trim()).then(done, fallback);
      } else {
        fallback();
      }
    });
  });

  // ---------- Results: print, JSON export and draft fixes ----------

  var printButton = document.getElementById("print-summary");
  if (printButton) printButton.addEventListener("click", function () { window.print(); });

  function baseName(source) { return source.replace(/\.[^.]+$/, "") || "policy"; }
  function saveFile(name, body, type) {
    var blob = new Blob([body], { type: type });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    URL.revokeObjectURL(link.href);
  }
  function citation(rule) {
    var joiner = /^[sr]\./.test(rule.section) ? " " : ", ";
    return rule.law_name + joiner + rule.section;
  }

  // The policy with a note after each clause that has a possible issue, then the missing clauses
  // with template wording. Nothing in the policy is rewritten: a keyword match can't know what
  // else a clause does.
  // "Subscription trap" reads "subscription trap" mid-sentence; "SaaS billing" keeps its capitals.
  function midSentence(title) { return /[A-Z]/.test(title.split(" ")[0].slice(1)) ? title : title.charAt(0).toLowerCase() + title.slice(1); }
  function draftFixes(result) {
    var rules = {};
    result.rules.forEach(function (r) { rules[r.rule_id] = r; });
    var notes = {};
    result.findings.forEach(function (f) {
      if (f.verdict === "compliant") return;
      (notes[f.clause_index] = notes[f.clause_index] || []).push(f);
    });
    var out = [
      "# Draft fixes: " + result.source,
      "",
      "LegalLens " + (result.mode === "full" ? "audit" : "keyword check") + ", rulebook " + result.rulebook_version +
        ", generated " + result.generated_at.slice(0, 10) + ".",
      "Review every suggestion before using it. " + result.disclaimer,
      "",
    ];
    var plan = result.guidance;
    if (plan && plan.groups && plan.groups.length) {
      out.push("## Action plan: " + plan.label.toLowerCase(), "", plan.intro, "");
      plan.groups.forEach(function (g) {
        out.push("### " + g.label, "");
        g.items.forEach(function (i) {
          out.push("- [ ] " + i.action_label + ": " + i.title + " (" + citation(i) + ", " + i.severity + ")");
        });
        out.push("");
      });
      [["Keep it in shape", plan.manage], ["Watch out for", plan.watch_out]].forEach(function (pair) {
        if (!pair[1].length) return;
        out.push("### " + pair[0], "");
        pair[1].forEach(function (t) { out.push("- **" + t.title + ".** " + t.points.join(" ")); });
        out.push("");
      });
    }
    out.push("## Your policy, with notes", "");
    var pos = 0;
    result.clauses.slice().sort(function (a, b) { return a.start - b.start; }).forEach(function (c) {
      var between = result.text.slice(pos, c.start).trim();
      if (between) out.push(between, "");
      out.push(result.text.slice(c.start, c.end).trim(), "");
      (notes[c.index] || []).forEach(function (f) {
        var rule = rules[f.rule_id];
        out.push("> **LegalLens: " + (f.verdict === "unclear" ? "possible issue" : "not met") + " under " +
          citation(rule) + ", " + midSentence(rule.title) + ".** Consider: " + (f.suggested_rewrite || f.how_to_fix), "");
      });
      pos = c.end;
    });
    var tail = result.text.slice(pos).trim();
    if (tail) out.push(tail, "");
    if (result.missing.length) {
      out.push("## Clauses to add", "", "Adapt this wording and replace each [placeholder].", "");
      result.missing.forEach(function (m) {
        out.push("### " + m.title + " (" + citation(m) + ", " + m.severity + ")", "", m.how_to_fix, "");
      });
    }
    return out.join("\n");
  }

  var data = document.getElementById("result-data");
  var fixesButton = document.getElementById("download-fixes");
  if (fixesButton && data) {
    fixesButton.hidden = false;
    document.getElementById("fixes-hint").hidden = false;
    fixesButton.addEventListener("click", function () {
      var result = JSON.parse(data.textContent);
      saveFile(baseName(result.source) + ".draft-fixes.md", draftFixes(result), "text/markdown");
    });
  }

  var download = document.getElementById("download-json");
  if (download && data) {
    download.addEventListener("click", function () {
      var result = JSON.parse(data.textContent);
      var blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = baseName(result.source) + ".audit.json";
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }
})();
