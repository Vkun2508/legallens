# Direction contract: LegalLens homepage

This is the referee for the landing page. The audit page follows DESIGN.md v4, which brings it into
this world (palette, faces, shape, mark) while keeping its own layout.

```
DIRECTION   Case file: Kettle (dark cinematic scan). Chosen over "The blank" (highlighter blanks) and
            "The report" (lab report), and over three flat scanner variations (Horizon, Band, Printout).
            The user kept only the v3.3 scanner and asked for "smooth, visually appealing, out of the
            ordinary", with unbelievablycrap.com, grids03.obys.agency, grail-app.com, era-residence.com
            and lamalama.com as references.
IDEA        On this page, LegalLens's audit of a real sample policy becomes a scan you watch: the
            flagged clauses lift off the sheet with their section, and the clauses that should be
            there open as empty slots. Competitor test: a policy generator or a consent tool has no
            missing-clause output to perform, so the sentence fails for them.
SURFACES    / → Persuade (hero and every section below it built in this world).
            /audit → Operate, restyled into this world (DESIGN.md v4: paper and ink, same faces,
            square corners, the same mark). 404 → the same.
FIRST VIEW  1440: the headline "Is your privacy policy DPDP-ready?" in two condensed lines, a lede,
            and the scan box on the left; Kettle's sheet tilted in 3D on the right, scanning; the
            case-file bar along the bottom. 375: the headline, lede and scan box, then the sheet,
            which plays when it scrolls into view.
LIVE THING  The scan box: a web address (POST /audit with url, through /api/audit-url's fetcher), or
            paste or upload below. Fallback without JS: the plain form post.
SIGNATURE   One GSAP timeline, scrubbed by the pinned scroll on desktop (Lenis):
            1. The sheet tilts in and drifts up through a fixed beam.
            2. Flagged clauses lift off with their section, and slots open.
            3. The camera flies down the clauses in reading order.
            4. The findings stack beside the score.
            Reduced motion: the read sheet, still. No JS: the read sheet laid flat, in CSS.
PALETTE     Ground #0A0B0D, ink #EBEBE6, muted #A5A7A3, paper #EFEFEC, paper ink #1C1C1A, unread
            #6B6B68, beam #FFF1D0. Flags: critical #FF6A5E / #B3261E, major #F2A93B / #8A5A0F.
            Strategy: restrained (dark ground; colour only on findings).
TYPE        Display: Bricolage Grotesque 700, wdth 75, uppercase, 0.88 leading (OFL).
            Text: Switzer 400/500/600 (ITF FFL), with tabular figures in the case-file bar.
SHAPE       Square corners everywhere. Depth from real 3D: the sheet and the lifted flags float.
IMAGERY     The product's own output: the real audit of data/samples/sample_privacy_policy.txt,
            rendered as paper. A dot-matrix light pool on canvas. Below the hero, three more
            sheets of real output: the § 4 redline (how it works), one rule as the rulebook holds
            it (what it checks) and an excerpt of the draft-fixes download (audit a policy).
            No stock photography: the subject's world is text, and the product's text is the picture.
MOTION      Interface: 100–300ms, cubic-bezier(0.22, 1, 0.36, 1).
            Narrative: expo curves, 0.8–2s, scroll-scrubbed. Only transform, opacity, clip-path and
            colour animate.
LIFTED      gradient: the beam's light spill only (scene lighting).
            shadow: the floating sheet and lifted flags only (they float).
            Both are inside the data-ui scene.
NOT THIS    Notion-style stone and serif (v3.3), the SaaS card kit, the "AI legal" navy and gold.
```
