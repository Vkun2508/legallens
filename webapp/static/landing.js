// Homepage: "Case file: Kettle". The sample policy's real audit (server-rendered in .scan-stage) is
// played as one GSAP timeline: the sheet tilts in and drifts up through a fixed beam, clauses with
// possible issues lift off with their section, missing clauses open as slots, then the camera flies
// through the clauses and the findings stack beside the score. On desktop the hero pins and the
// scroll drives the timeline (smoothed by Lenis); on a phone it plays once when it comes into view.
// Under reduced motion it shows the finished scan, still. Without JS the CSS shows the same.
(() => {
  const scene = document.getElementById("scan");
  if (!scene || !window.gsap || !window.ScrollTrigger) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const desktop = matchMedia("(min-width: 1024px)").matches;
  gsap.registerPlugin(ScrollTrigger);

  const D = { score: +scene.dataset.score, issues: +scene.dataset.issues, missing: +scene.dataset.missing, clauses: +scene.dataset.clauses };
  const drift = $(".scan-drift"), group = $(".scan-group"), paper = $(".scan-paper"), beam = $(".scan-beam"), world = $(".scan-world");
  const items = $$(".scan-drift > .scan-card, .scan-drift > .scan-slot").map((el, i) => ({
    el, kind: el.classList.contains("scan-slot") ? "slot" : el.classList.contains("scan-title") ? "title" : "clause",
    flag: el.classList.contains("is-flag"), findings: +(el.dataset.findings || 0), n: 0,
  }));
  let clauseNo = 0;
  items.forEach((it) => { if (it.kind === "clause") it.n = ++clauseNo; it.finding = it.flag || it.kind === "slot"; });

  // ---------- Layout on the sheet ----------
  const PAD = 30, GAP = 2, SLOT_H = 86, INK = "#1C1C1A", UNREAD = "#6B6B68";
  let W;
  const measure = () => {
    W = items[0].el.offsetWidth;
    items.forEach((it) => { it.h = it.kind === "slot" ? SLOT_H : it.el.offsetHeight; });
  };
  const layout = (open) => {
    let y = PAD, seen = 0;
    return items.map((it) => {
      const at = y;
      if (it.kind === "slot") { y += seen < open ? SLOT_H : 0; seen++; } else y += it.h + GAP;
      return at;
    });
  };
  const slots = items.filter((it) => it.kind === "slot").length;

  // ---------- The timeline ----------
  const tl = gsap.timeline({ paused: true });
  const marks = [];
  let T = {};

  function build() {
    tl.clear(); marks.length = 0;
    gsap.set([world, group, drift, paper, beam, ...items.map((it) => it.el)], { clearProps: "all" });
    measure();
    const x0 = -W / 2;
    const TILT = desktop ? { rotationX: 50, rotationZ: -16 } : { rotationX: 40, rotationZ: -8 };
    const finalY = layout(slots);
    const y0 = layout(0);

    gsap.set(paper, { x: x0 - 26, y: 0, width: W + 52, height: finalY[finalY.length - 1] + SLOT_H + PAD, opacity: 0 });
    gsap.set(beam, { x: x0 - 26, y: 0, width: W + 52, opacity: 0 }); // the paper's width, edge to edge
    items.forEach((it, i) => {
      gsap.set(it.el, { x: x0, y: y0[i], z: 0, rotationX: 0, rotationY: 0, rotationZ: 0, opacity: 1 });
      const tx = $(".scan-tx", it.el); if (tx) gsap.set(tx, { color: it.kind === "title" ? INK : UNREAD });
      const tag = $(".scan-tag", it.el); if (tag) gsap.set(tag, { opacity: 1, z: 40, y: 8, clipPath: "inset(0% 100% 0% 0%)" });
      const box = $(".scan-box", it.el); if (box) gsap.set(box, { opacity: 0, scaleY: 0.5 });
      it.base = it.el.className.replace(/\s*is-lit/g, "");
    });
    const startDrift = 24;
    gsap.set(drift, { y: startDrift });
    gsap.set(group, { rotationX: 6, rotationZ: 0, z: -700 });

    // Intro: the sheet settles into its tilt, the beam comes on.
    tl.to(group, { ...TILT, z: 0, duration: 1.8, ease: "expo.out" }, 0)
      .to(paper, { opacity: 1, duration: 0.9, ease: "power2.out" }, 0)
      .to(beam, { opacity: 1, duration: 0.6, ease: "power2.out" }, 0.9);

    // Scan: each item is carried up to the beam; what passes it is read.
    let t = 1.5, open = 0, driftY = startDrift;
    const speed = desktop ? 340 : 260;
    items.forEach((it, i) => {
      if (it.kind === "title") return;
      const ys = layout(open);
      const target = -(ys[i] + (it.kind === "slot" ? SLOT_H / 2 : it.h * 0.55));
      const d = Math.max(0.35, Math.abs(target - driftY) / speed);
      tl.to(drift, { y: target, duration: d, ease: "sine.inOut" }, t);
      driftY = target; t += d;
      if (it.kind === "clause") {
        tl.to($(".scan-tx", it.el), { color: INK, duration: 0.35, ease: "power2.out" }, t - 0.2);
        marks.push({ t: t - 0.1, kind: "clause", n: it.n });
        if (it.flag) {
          tl.set(it.el, { attr: { class: it.base + " is-lit" } }, t - 0.05)
            .to(it.el, { z: desktop ? 46 : 34, rotationX: -8, duration: 0.8, ease: "expo.out" }, t)
            .to($(".scan-cast", it.el), { opacity: 0.5, duration: 0.8, ease: "expo.out" }, t)
            .to($(".scan-bgl", it.el), { opacity: 1, duration: 0.3 }, t)
            .to($(".scan-tag", it.el), { clipPath: "inset(0% 0% 0% 0%)", y: 0, duration: 0.5, ease: "expo.out" }, t + 0.25);
          marks.push({ t: t + 0.2, kind: "issue", count: it.findings || 1 });
          t += 0.75;
        }
        if (it.n === 4) tl.addLabel("firstRead", t + 0.2);
      } else {
        open++;
        const ys2 = layout(open);
        items.forEach((o, j) => { if (j > i) tl.to(o.el, { y: ys2[j], duration: 0.7, ease: "expo.inOut" }, t - 0.1); });
        tl.to($(".scan-box", it.el), { opacity: 1, scaleY: 1, duration: 0.7, ease: "expo.out" }, t + 0.15);
        marks.push({ t: t + 0.3, kind: "missing" });
        t += 0.8;
      }
    });
    if (!tl.labels.firstRead) tl.addLabel("firstRead", t * 0.4);
    marks.push({ t: t + 0.15, kind: "done" });
    tl.addLabel("scanned", t + 0.2);
    t += 0.4;

    // The read: the camera flattens the sheet and comes in close on two findings, one at a time:
    // a clause with a possible issue, then the slot where a required clause should be. Each gets its
    // verdict set large beside it.
    const focus = (k) => items.find((it) => it.el.dataset.focus === String(k));
    const centreOn = (it) => -(driftY + finalY[items.indexOf(it)] + (it.kind === "slot" ? SLOT_H / 2 : it.h / 2));
    const ZOOM = desktop ? 520 : 260, others = (keep) => items.filter((o) => o !== keep).map((o) => o.el);
    const v1 = $('.scan-verdict[data-v="1"]'), v2 = $('.scan-verdict[data-v="2"]');
    const f1 = focus(1), f2 = focus(2);
    tl.addLabel("read", t)
      .to(beam, { opacity: 0, duration: 0.4 }, t)
      .to(paper, { opacity: 0, duration: 1, ease: "power2.inOut" }, t + 0.3)
      .to($$(".scan-tag"), { clipPath: "inset(0% 100% 0% 0%)", duration: 0.4, ease: "power2.in" }, t);
    if (f1) {
      tl.to(group, { rotationX: 0, rotationZ: 0, x: 0, y: centreOn(f1), z: ZOOM, duration: 1.6, ease: "expo.inOut" }, t)
        .to(others(f1), { opacity: 0.07, duration: 0.8 }, t + 0.4)
        .to(f1.el, { rotationX: 0, z: 30, duration: 1.2, ease: "expo.inOut" }, t + 0.2)
        .fromTo(v1, { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.8, ease: "expo.out", immediateRender: false }, t + 1.1);
      t += 3.2;
    }
    if (f2) {
      const bb = $(".scan-boxbg", f2.el);
      // The climax: the empty slot comes to the centre of the frame, large, under the verdict.
      tl.to(v1, { autoAlpha: 0, y: -24, duration: 0.5, ease: "power2.in" }, t)
        .to(group, { y: centreOn(f2) + (desktop ? innerHeight * 0.1 : 0), z: desktop ? 640 : 300, duration: 1.4, ease: "expo.inOut" }, t)
        .to(others(f2), { opacity: 0.05, duration: 0.6 }, t + 0.2)
        .to(f2.el, { opacity: 1, duration: 0.6 }, t + 0.2);
      if (bb) tl.to(bb, { opacity: 1, duration: 0.5 }, t + 0.6);
      if (desktop) tl.to(world, { x: -innerWidth * 0.14, duration: 1.4, ease: "expo.inOut" }, t);
      tl.fromTo(v2, { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.8, ease: "expo.out", immediateRender: false }, t + 1.0);
      t += 3.2;
      tl.to(v2, { autoAlpha: 0, y: -24, duration: 0.3, ease: "power2.in" }, t - 0.15);
    }

    // Collapse: the findings come forward into a stack beside the score; the rest of the sheet goes.
    tl.addLabel("collapse", t)
      .to(paper, { opacity: 0, duration: 0.6 }, t)
      .to(drift, { y: 0, duration: 1.5, ease: "expo.inOut" }, t)
      .to(group, { x: 0, y: 0, z: 0, rotationX: -4, duration: 1.5, ease: "expo.inOut" }, t);
    if (desktop) tl.to(world, { x: 0, duration: 1.5, ease: "expo.inOut" }, t);
    items.filter((it) => it.finding).forEach((it, k) => {
      $$(".scan-bg, .scan-boxbg", it.el).forEach((b) => tl.to(b, { opacity: 1, duration: 0.4 }, t));
      $$(".scan-cast", it.el).forEach((b) => tl.to(b, { opacity: 0, duration: 0.4 }, t));
      tl.to(it.el, { opacity: 1, duration: 0.4 }, t)
        // On a phone the stack stays square to the screen and inside the gutter.
        .to(it.el, desktop
          ? { x: -W / 2 + 40 + k * 12, y: -300 + k * 64, z: 40 + k * 14, rotationY: -14, rotationX: 6, rotationZ: -1.5, duration: 1.5, ease: "expo.inOut" }
          : { x: -W / 2, y: -190 + k * 42, z: k * 3, rotationY: 0, rotationX: 0, rotationZ: 0, duration: 1.5, ease: "expo.inOut" }, t + k * 0.05);
    });
    items.filter((it) => !it.finding).forEach((it) => tl.to(it.el, { opacity: 0, duration: 0.4 }, t));
    if (desktop) tl.fromTo(".scan-result", { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 1, ease: "expo.out", immediateRender: false }, t + 0.2);
    tl.addLabel("end", t + 1.9).set({}, {}, t + 1.9);
    T = { firstRead: tl.labels.firstRead, scanned: tl.labels.scanned, read: tl.labels.read, end: tl.duration() };
  }

  // ---------- HUD, read from the timeline's time so it scrubs both ways ----------
  const hud = { clause: $("#hud-clause"), bar: $("#hud-bar"), issues: $("#hud-issues"), missing: $("#hud-missing") };
  let last = "";
  function updateHud() {
    const now = tl.time();
    let n = 0, issues = 0, missing = 0, done = false;
    for (const m of marks) {
      if (m.t > now) break;
      if (m.kind === "clause") n = m.n;
      else if (m.kind === "issue") issues += m.count;
      else if (m.kind === "missing") missing++;
      else done = true;
    }
    if (done) { missing = D.missing; issues = D.issues; }
    const label = done ? (now >= T.end - 0.05 ? `Estimated score ${D.score} / 100` : `Read all ${D.clauses} clauses`)
      : n ? `Reading clause ${n} of ${D.clauses}` : "Opening the document";
    const key = label + issues + "/" + missing;
    if (key !== last) { hud.clause.textContent = label; hud.issues.textContent = issues; hud.missing.textContent = missing; last = key; }
    hud.bar.style.transform = `scaleX(${Math.min(1, now / T.scanned)})`;
  }
  tl.eventCallback("onUpdate", updateHud);

  // ---------- The light pool, drawn as a dot matrix ----------
  const canvas = $(".scan-dither");
  function drawDither() {
    const dpr = Math.min(devicePixelRatio || 1, 1.5), w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const pitch = desktop ? 6 : 5;
    const hash = (x, y) => { const s = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453; return s - Math.floor(s); };
    for (let y = pitch / 2; y < h; y += pitch) {
      for (let x = pitch / 2; x < w; x += pitch) {
        const L = 0.32 + (hash(x, y) - 0.5) * 0.2;
        const r = 0.35 + L * 1.05;
        g.fillStyle = `rgba(235,235,230,${(0.03 + L * 0.12).toFixed(3)})`;
        g.fillRect(x - r, y - r, r * 2, r * 2);
      }
    }
  }

  // ---------- Days until most DPDP duties apply (counted in India's date) ----------
  const days = $("#hud-days");
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const left = Math.max(0, Math.round((Date.parse(days.dataset.inForce) - Date.parse(today)) / 864e5));
  days.textContent = `${left} days`;

  // ---------- The bar is see-through over the hero and solid after it ----------
  // While pinned the scene sits at the top; once it starts to scroll away, the bar takes the ground.
  const nav = $(".scan-nav");
  const solid = () => nav && nav.classList.toggle("is-solid", scene.getBoundingClientRect().top < -1);
  addEventListener("scroll", solid, { passive: true }); solid();

  // ---------- How it works: the sample clause gets marked as it comes into view ----------
  // Armed here, not in CSS, so the sheet is never hidden when this script doesn't run.
  const redline = $(".ll-redline");
  if (redline && !reduce && "IntersectionObserver" in window) {
    redline.classList.add("is-armed");
    const ro = new IntersectionObserver((es) => {
      if (!es[0].isIntersecting) return;
      redline.classList.add("is-read"); ro.disconnect();
    }, { threshold: 0.55 });
    ro.observe(redline);
  }

  // ---------- The scan box: say it's working ----------
  const form = $("#scan-form");
  form.addEventListener("submit", () => {
    const b = $("button[type=submit]", form);
    b.textContent = "Scanning…"; b.setAttribute("aria-busy", "true");
  });
  addEventListener("pageshow", (e) => {
    if (!e.persisted) return;
    const b = $("button[type=submit]", form);
    b.textContent = "Scan it free"; b.removeAttribute("aria-busy"); b.disabled = false;
  });

  // ---------- Playback ----------
  let lenis = null;
  $$("[data-rescan]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    const input = $("#policy-url");
    if (lenis) lenis.scrollTo(0, { duration: 1.4, onComplete: () => input.focus() });
    else { scrollTo(0, 0); input.focus(); }
  }));
  function start() {
    build(); drawDither();
    if (reduce) { tl.seek("scanned"); updateHud(); return; }
    if (desktop) {
      gsap.from(".scan-line > span", { yPercent: 105, duration: 1, ease: "expo.out", stagger: 0.09 });
      tl.tweenTo("firstRead", { duration: 5.2, ease: "power1.inOut" });
      if (window.Lenis) {
        lenis = new Lenis({ lerp: 0.09, smoothWheel: true, anchors: true });
        lenis.on("scroll", ScrollTrigger.update);
        gsap.ticker.add((time) => lenis.raf(time * 1000));
        gsap.ticker.lagSmoothing(0);
      }
      // The headline and form stay while the sheet is scanned, then slide off as the read begins.
      const copyOut = gsap.to(".scan-copy", { y: -24, autoAlpha: 0, ease: "power1.in", paused: true }); // fades where it stands, clear of the bar
      ScrollTrigger.create({
        trigger: scene, start: "top top", end: "+=320%", pin: true, anticipatePin: 1,
        onUpdate: (self) => {
          gsap.to(tl, { time: T.firstRead + self.progress * (T.end - T.firstRead), duration: 0.7, ease: "power3.out", overwrite: true });
          const pe = (T.read - T.firstRead) / (T.end - T.firstRead);
          gsap.to(copyOut, { progress: gsap.utils.clamp(0, 1, (self.progress - pe + 0.01) / 0.05), duration: 0.5, ease: "power3.out", overwrite: true });
        },
      });
    } else {
      updateHud();
      const io = new IntersectionObserver((es) => { if (es[0].isIntersecting) { tl.timeScale(1.5).play(); io.disconnect(); } }, { threshold: 0.35 });
      io.observe($(".scan-stage-wrap"));
    }
    document.addEventListener("visibilitychange", () => (document.hidden ? gsap.globalTimeline.pause() : gsap.globalTimeline.resume()));
  }
  // After a failed upload the page comes back at the top; take the visitor back to the form and its message.
  function showUploadError() {
    const err = $("#upload-error");
    if (!err || !err.textContent.trim()) return;
    // The pinned scene keeps adding scroll length for a moment after load, which pushes the form
    // down after a jump. So look again a few times, and stop as soon as the visitor scrolls.
    let userMoved = false;
    const stop = () => { userMoved = true; };
    ["wheel", "touchstart", "keydown"].forEach((t) => addEventListener(t, stop, { once: true, passive: true }));
    const jump = () => {
      if (userMoved) return;
      const r = err.getBoundingClientRect();
      if (r.top >= 80 && r.bottom <= innerHeight) return; // already in view
      const y = Math.max(0, r.top + scrollY - innerHeight / 2);
      if (lenis) lenis.scrollTo(y, { immediate: true, force: true });
      else scrollTo(0, y);
    };
    const go = () => {
      if (window.ScrollTrigger) ScrollTrigger.refresh();
      err.focus({ preventScroll: true });
      [0, 250, 700, 1500].forEach((ms) => setTimeout(() => requestAnimationFrame(jump), ms));
    };
    if (document.readyState === "complete") go();
    else addEventListener("load", go, { once: true });
  }
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(start).then(showUploadError);
  let rt;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(drawDither, 200); });
})();
