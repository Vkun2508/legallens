# LegalLens design system (v4)

**v4: one world with the homepage.** The homepage was redesigned as "Case file: Kettle", a dark,
cinematic scan of a sample policy. Its contract is `docs/DIRECTION.md`, and it is the reference for
the homepage. This file covers the **audit page** (and the 404 page), which keeps its v3.3 layout and
behaviour but now uses the homepage's world:
- **Colour:** paper and ink, with colour only on findings (critical red, major amber). The olive accent is gone; actions are ink.
- **Type:** Bricolage Grotesque (condensed, 700) for headings and the score; Switzer for text. Libre Caslon and Source Sans are gone.
- **Shape:** square corners everywhere.
- **Mark:** the homepage's mark, a sheet crossed by the scan line. The loupe (§ in a lens) is retired.

**Earlier versions, in short:** v2 ("law library": cream, navy, Caslon) read as generated; v3 made
the document the interface; v3.2 took the Notion archetype (stone paper, olive accent); v3.3 turned the
consumer reader into the compliance audit, with rule severity in the three tier slots.

Project rules for the UI/UX skills (accessibility target, banned patterns, motion exceptions) are in
`.ux-profile.md`. Tokens are CSS custom properties in `webapp/static/app.css`. Pages use the names,
never raw values.

## Color

- **Source:** the homepage palette (`docs/DIRECTION.md`): ground `#0A0B0D`, paper `#EFEFEC`, paper ink `#1C1C1A`, flags red and amber.
- **How tokens are written:** each token holds both themes with CSS `light-dark()`.
  - **Default:** the page follows the system theme.
  - **Toggle:** the masthead toggle pins a theme by setting `data-theme` on `<html>`.
  - **Remembered:** the choice is saved in `localStorage` and applied before first paint.
  - **Print:** always ink on white.
- **Actions are ink:** primary buttons, links, focus and the spotlight use `--lens`, which is now ink. Colour is kept for findings.
- **Tiers:** critical red, major amber, minor grey. They are always shown next to their word.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--desk` | `#E7E7E3` | `#0A0B0D` | L0 page background (set on `html`); dark is the homepage's ground |
| `--sheet` | `#EFEFEC` | `#15171A` | L1: the paper; the document, tables, inputs, upload zone |
| `--ink` | `#1C1C1A` | `#EBEBE6` | Text |
| `--ink-2` | `#5E5D58` | `#A5A7A3` | Secondary text, notes, headings between clauses |
| `--rule` | ink at 12% | ink at 10% | Hairlines, the margin rule |
| `--rule-strong` | `#7A7975` | `#6B6E72` | Borders that identify a control |
| `--lens` / `--on-lens` | `#1C1C1A` / `#EFEFEC` | `#EBEBE6` / `#0A0B0D` | Actions, links, the spotlight: ink |
| `--focus` | `#1C1C1A` | `#FFF1D0` | Focus ring (dark uses the homepage's beam colour) |
| `--lens-tint` | `#E2E2DD` | `#22252A` | Pressed filter, selected option, drag-over |
| `--current` | `#F7F7F5` | `#1C1F23` | Background of the clause in the spotlight |
| `--high` / `--high-tint` | `#B3261E` / `#F9D7D2` | `#FF6A5E` / `#3A1D1B` | Critical ("fix first"). Also errors |
| `--medium` / `--medium-tint` | `#8A5A0F` / `#F8ECD2` | `#F2A93B` / `#33270F` | Major ("fix soon"). Also warnings |
| `--low` / `--low-tint` | `#5E5D58` / `#E2E2DD` | `#A5A7A3` / `#22252A` | Minor ("worth fixing"); grey |

**Measured contrast** (WCAG 2.1, every pair the pages use):
- **Text:** at least 4.77:1 in light and 5.45:1 in dark, including each tier colour on the sheet, the desk and its own tint.
- **Controls and focus rings:** at least 3.5:1.
- **Selected business-type option** (`--ink-2` hint on `--lens-tint`): 5.08:1 light, 6.34:1 dark.
- **Checked:** axe (WCAG 2.1 AA) finds no violations on the audit and 404 pages, light and dark, at 1440 and 375px.

"No issues found" means no rule's wording matched. It never means "compliant".

## Typography

Self-hosted, with no third-party requests: Bricolage Grotesque (SIL Open Font License) and Switzer
(ITF Free Font License). Both are declared once, in `app.css`, and the homepage reuses them.

| Token | Size / line height | Face | Use |
|---|---|---|---|
| `--step-6` | 2.986rem / 0.9 | Bricolage Grotesque 700, wdth 75 | The score; the 404 headline |
| `--step-5` | 2.488rem / 0.95 | Bricolage Grotesque 700, wdth 75 | Results title (the document's name, in its own case) |
| `--step-3` | 1.728rem / 0.95 | Bricolage Grotesque 700, wdth 75, capitals | Section titles |
| `--step-1` | 1.2rem / 1.25 | Switzer 600 | Sub-heads (`h3`) |
| wordmark | 20px / 1 | Bricolage Grotesque 700, wdth 75, capitals | "LEGALLENS" beside the mark |
| `--text-body` | 1rem / 1.55 | Switzer 400/500 | Interface copy and controls |
| document | 1rem / 1.7 | Switzer 400 | Clause text: open leading for legal reading, set like the homepage's sheet |
| `--text-secondary` | 0.875rem / 1.4–1.5 | Switzer | Margin notes, hints, filters |
| `--text-meta` | 0.75rem / 1.4–1.45 | Switzer | Offsets, `kbd`. This is the floor |

- **Clause references:** "§ 2.1". An unnumbered clause is "Clause 7", by its position.
- **Case:** sentence case for text and labels. Section titles and the wordmark are set in capitals, as on the homepage; the document's own name keeps its case.
- **No italics:** Switzer is loaded without an italic, so notes that were italic (good-practice notes, "not yet checked") are set in `--ink-2` instead.
- **Numbers:** counts and offsets use tabular figures.

## Spacing and layout

- **Scale:** `--space-1` 4, `-2` 8, `-3` 12, `-4` 16, `-6` 24, `-8` 32, `-12` 48, `-16` 64, `-24` 96 (px).
- **Breakpoints:** narrow below 768px, wide from 768px up. `main` is capped at 1280px; the chrome is not.
- **Gutter:** 16px narrow, 32px wide.
- **Safe areas:** the viewport uses `viewport-fit=cover`. `--gutter-left` and `--gutter-right` grow to clear a notch
  in landscape; the phone's bottom bar and the footer add `env(safe-area-inset-bottom)`.
- **Homepage:** see `docs/DIRECTION.md` (hero scan, how it works, what it checks, pricing, audit a policy, questions).
- **Audit** (Pattern 2, Detail/Record):
  1. **Header:** document name, the score, three status sentences, and actions (Print report, Download draft fixes, Audit another policy).
  2. **Keyword-check banner.**
  3. **Action plan, then missing clauses.** The action plan follows the review goal (first policy, live policy, quick check-up): fixes grouped by when, each linking to its detail below, then "Alongside the fixes", "Keep it in shape" and "Watch out for". It is built from the missing-list and screens-checklist parts, with no new component. Missing clauses follow, most severe first.
  4. **"How to read these results".**
  5. **Toolbar:** sticky from 768px; severity filters, fold toggle, issue navigation.
  6. **Reader:** the minimap rail and the sheet.
     - **Sheet:** each clause is a grid row of text plus a 15rem margin note, and a margin rule runs down the sheet.
     - **Below 768px:** notes drop under their clause, the rail is hidden, and issue navigation is pinned to the bottom.
  7. **Check your app's screens too:** the interface-only dark patterns.
  8. **Keep a copy:** JSON export.

## Shape and depth

- **Radius:** none. Square corners for the sheet, tables, badges and controls, as on the homepage.
- **Elevation:** a 1px border first, then one shadow: `--shadow-sheet` (alpha ≤ 0.06) in light, and an inset top highlight in dark.

## Motion

Tokens: 100 / 150 / 200 / 300ms. Ease-out on entry, ease-in on exit. Only
transform and opacity animate (colour and border changes take ≤150ms).

| Where | What moves |
|---|---|
| Spotlight | The other rows fade to 45% (200ms) |
| Buttons, filters, upload zone | Border and background colour (150ms) |
| Pop press | `scaleY(0.95)` from the base, 100ms ease-out. The bottom edge snaps from 3px to 1px (layout is not animated) |
| Loading | Shown after 300ms, so a fast audit never flashes it. The skeleton pulses (the only functional loop) |
| Page change | A cross-document view transition: 200ms crossfade, with the masthead held in place (opacity only) |
| Disclosure chevron | Turns 90° when a "Suggested wording" or "How to read" disclosure opens (150ms) |

**Under `prefers-reduced-motion: reduce`:** every state still changes, instantly. The skeleton is
static. The homepage's motion (the scan, the marking beat) is in `docs/DIRECTION.md`.

## Components

- **Masthead:**
  - **Wordmark:** the mark (a sheet crossed by the scan line, `mark()` in `macros.html`, shared with the homepage) and "LegalLens" in Bricolage capitals.
  - **Theme toggle:** a 44px icon button (moon or sun), labelled "Dark theme", with `aria-pressed` and a "Switch to … theme" tooltip.
  - **Links:** two nav links and the primary "Upload an agreement".
  - **Below 768px:** the links fold into a Menu button, and the primary button reads "Upload".
- **Buttons:**
  - **Primary:** a lens fill.
  - **Secondary:** a sheet fill with a `--rule-strong` border.
  - **Size:** both are at least 44px tall, Switzer 500.
  - **No arrows.**
  - **Pop press (from the user's PopButton component):** applies to buttons, filters and Menu.
    - **Rest:** a 3px bottom edge, a darker shade of the fill on primary buttons and `--rule-strong` on the rest.
    - **Press:** the edge thins to 1px and the button squashes to `scaleY(0.95)` from its base.
    - **Toggled filters:** they rest pressed in.
- **Tier badge:** an 8px square in the tier colour, then the severity name in Switzer 600 and the tier colour, optionally followed by a qualifier such as ", possible issue". There is no pill.
- **Score:**
  - "Estimated score", the number in Bricolage at `--step-6` with tabular figures, and "out of 100".
  - A 4px neutral meter (`--ink` on `--rule`, `aria-hidden`). It never takes a tier colour, so no colour stands without its word.
  - One number, never a KPI row, and no count-up.
- **Citation:** "DPDP Act s.6(4)", then ", also DPDP Rules r.3(c)(i)" in `--ink-2`. Sections use the law's own numbering.
- **Verified mark:** a 1.5px check and "Checked against the official text", or "Not yet checked against the official text" in `--ink-2`.
- **Suggested wording:**
  - A `details` disclosure: a 44px summary in `--lens` with a chevron.
  - The body has a 2px `--rule-strong` left rule, and the wording is set as policy text.
  - app.js reveals a small "Copy wording" button. Copying announces "Wording copied." through a status region; without clipboard access, the text is selected instead.
- **Missing clause:** a ruled row with the severity badge in a 6rem column, then:
  - the title (Switzer 500)
  - the citation and verified mark
  - what it means
  - a good-practice note in `--ink-2`, where the law sets a duty rather than wording
  - the suggested wording
- **Business-type and review-goal choices:** radio options as 44px bordered targets. The selected one takes a `--lens` border and `--lens-tint`.
- **Screens checklist:** ruled items in an auto-fit grid: title, citation, what to look for.
- **Annotated document (audit):**
  - **Text:** clause text in Switzer. A clause with a possible issue carries a 3px rule in the colour of its most severe issue, and evidence is underlined 2px in the tier colour.
  - **Margin note,** in order:
    1. For each possible issue: the badge with its verdict, the rule, its citation, and a "Why and how to fix" disclosure.
    2. "Meets", followed by the rules the clause satisfies.
    3. The clause reference and offsets.
- **Spotlight:** the current clause gets `--current`, a 3px lens rule and tinted evidence. Keys: `j`/`k` move between flags (ignored while typing), Esc clears.
- **Minimap rail:** one tick per row, as tall as the row and coloured by tier. A lens-outlined window shows the visible part. It is mouse-only (`aria-hidden`); the brief's links and Previous/Next are the keyboard path.
- **Print report:**
  - **Contents:** the score and status, the action plan, missing clauses with wording, possible issues by severity with the clause text, the screens checklist, and the disclaimer with the rulebook version.
  - **Style:** ink on white, headings in Bricolage.

## Imagery and icons

No photos and no illustration on the audit page. The homepage's imagery is in `docs/DIRECTION.md`.
Icons are inline SVG with a 1.5px stroke and `currentColor`. The favicon is the mark: a paper sheet
outline crossed by the beam-coloured scan line, on the homepage's ground.

**404:** unknown pages get `404.html` (the masthead, "This page isn't here" in Bricolage capitals, and
links to scan or go home). `/api/*` keeps its JSON errors.

## Accessibility rules

- **Contrast:** re-check it for any new colour pair. Tier colours always appear next to their word.
- **Targets:** at least 44×44px.
- **Focus:** `:focus-visible` is a 2px lens outline with a 2px offset, and it is never removed.
- **Keyboard:** tab order follows reading order. The lens is a focusable group with an arrow-key hint in its label, and its tag is `aria-live`. Flag moves are announced through a status region.
- **Hidden from screen readers:** decorative visuals (the fine-print sheet, the lens, the rail) are `aria-hidden`.
