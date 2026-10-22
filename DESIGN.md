# LegalLens design system

**Direction: "law library".** LegalLens should look like something a careful
legal reader would trust:
- bond-paper ivory with navy-black ink;
- Caslon type, the face of legal and parliamentary printing;
- a seal mark;
- double rules like a legal document header;
- the document pane set like pleading paper, with ruled lines and a double margin rule.

One navy accent carries action and focus. Three tier colours (oxblood, amber,
slate) carry risk, always alongside a text label.

**Why this replaces v1:** the first direction (warm editorial, oxblood accent)
read as a magazine, not a legal tool. Navy, Caslon, seals and ruled paper are
the visual language of courts, firms and statute books.

**Not based on real sites:** the UXKIN reference library failed to connect, so
this direction comes from the brief and established legal print conventions,
not from studying comparable sites.

The tokens below are implemented as CSS custom properties in
`webapp/static/app.css`. Pages use the names, never raw values.

## Color

The two themes are designed separately:
- **Light, "bond paper":** ivory and navy-black ink.
- **Dark, "chambers at night":** deep navy-charcoal with parchment text. The accent and tier colours are lighter here, so they keep their contrast.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--paper` | `#F7F5EF` | `#0E1420` | Page background |
| `--surface` | `#FDFCF9` | `#151C2B` | Cards, panels, upload zone |
| `--sunk` | `#EFECE3` | `#1B2333` | Inset areas: document pane, textarea |
| `--ink` | `#141B2D` | `#ECE7DC` | Body text, headings, primary button fill |
| `--ink-2` | `#4D5566` | `#A9B0BE` | Secondary text: metadata, hints, offsets |
| `--on-ink` | `#FDFCF9` | `#0E1420` | Text on `--ink` fills |
| `--rule` | `#D9D4C7` | `#2A3345` | Hairlines, double rules, pleading lines (decorative) |
| `--rule-strong` | `#7F8696` | `#6B7488` | Borders that identify a control |
| `--accent` | `#1F3B66` | `#A9C1EA` | The one accent, legal navy: links, focus, selection, seal, primary hover |
| `--on-accent` | `#FDFCF9` | `#0E1420` | Text on `--accent` fills |
| `--accent-tint` | `#DCE4F0` | `#263A5C` | Selected clause's highlight, drag-over fill |
| `--span-a` / `--span-b` | `#ECE8DD` / `#E4DFD2` | `#1F2838` / `#252F41` | Unflagged clause highlights, alternating |
| `--high` / `--high-tint` | `#8C1D18` / `#F6DFDB` | `#F0A49A` / `#4A2226` | Tier High ("Review closely"): badge text and border / fill, document highlight |
| `--medium` / `--medium-tint` | `#7A5300` / `#F6EACB` | `#E5C07A` / `#3F3218` | Tier Medium ("Worth knowing"); also per-document warnings |
| `--low` / `--low-tint` | `#4A5568` / `#E4E8EF` | `#B9C2D0` / `#2A3344` | Tier Low ("For awareness") |
| `--error-bg` / `--error-rule` | `#F8E1DA` / `#B4432C` | `#3E241E` / `#D0705A` | Upload errors |
| `--lift-border` | = `--rule-strong` | `#8A93A6` | Border of lifted things. Brighter in dark, where shadows barely show |
| `--shimmer` | `rgb(255 255 255 / .6)` | `rgb(255 255 255 / .06)` | Skeleton shimmer (decorative) |

**Tier colours carry meaning only with words.** Every tier colour appears next
to its text label ("High · Review closely"), and the document pane has a legend.
"No flags" means no watched terms were found. It never means "safe".

**Measured contrast (WCAG 2.1, 43 pairs per theme):**
- **Text:** 5.62:1 or higher in light and 5.74:1 or higher in dark (minimum 4.5:1). This includes each tier colour on paper, on the card surface and on its own tint.
- **Controls, focus rings and tier bars:** 3.09:1 or higher (minimum 3:1).

## Typography

All fonts are self-hosted from `webapp/static/fonts/` and OFL-licensed. No
third-party font requests are made.

| Token | Size / line height | Face | Use |
|---|---|---|---|
| `--text-display` | 3.5rem / 1.05 | Libre Caslon Display | Homepage title |
| `--text-h1` | 2.25rem / 1.1 | Libre Caslon Display | Results title (file name) |
| `--text-h2` | 1.5rem / 1.25 | Libre Caslon Text 400 | Section and pane titles, wordmark. Display's hairlines break up below ~40px |
| `--text-h3` | 1.125rem / 1.35 | Libre Caslon Text 700 | Card titles, step titles |
| `--text-lead` | 1.25rem / 1.55 | Libre Caslon Text 400 | Intro paragraph |
| `--text-body` | 1.0625rem (17px) / 1.6 | Source Sans 3 400/600 | Interface copy, controls |
| `--text-doc` | 1rem / 2rem | Libre Caslon Text 400 | Document text on pleading lines (fixed 2rem line pitch) |
| `--text-small` | 0.9375rem / 1.5 | Source Sans 3 | Metadata, hints |
| `--text-label` | 0.8125rem / 1.4 | Source Sans 3 600, uppercase, tracking 0.08em | Eyebrows, tier badges, "small caps" labels |

- **Clause numbers** are set with a section mark: "§ 2.1". Unnumbered clauses
  show "§ —" plus an italic "no number".
- **Numbers:** offsets and counts use tabular figures.
- **Prose:** capped at 68ch, and headings use `text-wrap: balance`.

## Spacing and layout

- **Scale (4px base):** `--space-1` 4, `-2` 8, `-3` 12, `-4` 16, `-5` 24, `-6` 32, `-7` 48,
  `-8` 64, `-9` 96 (px).
- **Widths:** `--measure-wide` 88rem for results, 72rem for the homepage.
- **Page gutter:** 16px on phones, 32px from 720px up.
- **Homepage:** a two-column hero (copy and actions on the left, the animated
  review illustration on the right) from 960px up, stacked below that. Then come:
  - **How it works:** a three-step § sequence joined by a rule.
  - **What LegalLens flags:** a ledger table of categories grouped by tier.
  - **Upload form:** anchored at `#analyze`.
  - **Privacy and scope notes.**
- **Results page:**
  - The header shows the file name with a seal and the actions.
  - Next comes the risk summary: tier counts, a stacked tier bar, filters and category tallies.
  - Then the warnings and the limits note.
  - Then two panes: clause cards (2fr) and the pleading-paper document (3fr).

## Shape and depth

- **Radius:** `--radius-sm` 2px (badges, highlights, inputs), `--radius-md` 4px
  (cards, buttons), `--radius-lg` 8px (upload zone). These are tighter than v1:
  legal print is square-cornered.
- **Rules:** the masthead and section heads use a double rule (3px apart).
- **Shadow:** `--shadow-lift` is the only one. It's used for hover lift and the selected card.

## Motion

Motion shows review happening: a page being read, marks being made, findings
being tallied. It never loops for its own sake, except the homepage
illustration, which is the product demo.

| Token | Value | Use |
|---|---|---|
| `--dur-fast` | 120ms | Colour, border, focus |
| `--dur-base` | 220ms | Lift, expand/collapse, filters |
| `--dur-enter` | 420ms | Cards, sections and highlights entering |
| `--ease-out` | `cubic-bezier(.2, .7, .2, 1)` | Arrivals, openings |
| `--ease-in-out` | `cubic-bezier(.6, 0, .3, 1)` | Collapses, loops |
| `--stagger` | 35ms, capped at the 12th item | Lists |

| Where | What moves |
|---|---|
| Seal mark | The double ring draws itself once on load (stroke-dashoffset) |
| Homepage hero | A mini document is "reviewed" on an 8s loop: a reading line moves down the page, clause highlights sweep in like a marker pen, and tier tags stamp in |
| Homepage sections | Fade and rise 12px as they scroll into view (IntersectionObserver) |
| Upload zone | Lift on hover; marching dashed border on drag-over; the chosen file name slides in |
| Loading | Skeleton with shimmer; the seal turns slowly |
| Risk summary | Counts tick up from 0, and the tier bar segments grow in order |
| Clause cards | Staggered fade and rise; tier badges stamp in (scale 1.15 → 1); smooth expand/collapse; filtering fades cards out and in |
| Document pane | Each clause highlight sweeps left to right like a marker as it scrolls into view |

**`prefers-reduced-motion: reduce`:**
- **Off:** everything above. The hero shows its finished state, numbers appear at their final value, and highlights are already drawn.
- **Kept:** state changes (filtering, expansion, selection) still happen, instantly.

## Components

- **Masthead:**
  - **Wordmark:** a seal (a double ring with a § glyph) and "LegalLens" in Caslon Text.
  - **Tagline:** in `--ink-2`.
  - **Rule:** a double hairline beneath.
- **Buttons:**
  - **Primary:** an `--ink` fill that becomes `--accent` on hover.
  - **Secondary:** a `--surface` fill with a `--rule-strong` border.
  - **Size:** all buttons are at least 44px tall, `--radius-md`, Source Sans 600.
  - **Arrow:** primary buttons that lead somewhere have an arrow that nudges 3px on hover.
- **Links:** `--accent`, underline 1px with a 0.2em offset, 2px on hover.
- **Focus:** 2px `--accent` outline with a 2px offset. Two exceptions:
  - **Card buttons:** the ring is inset by 3px.
  - **Upload zone:** shows the ring via `:has(input:focus-visible)` (keyboard focus only).
- **Tier badge:**
  - **Look:** `--text-label` uppercase, the tier colour as text and a 1px border, on the tier tint.
  - **Content:** "High", "Medium", "Low" or "No flags", followed by the qualifier in normal case.
  - **Shape:** square cornered, like a stamp.
- **Category chip:** a small Source Sans 600 label on `--surface` with a `--rule` border.
- **Evidence marks:** matched phrases in card text are underlined 2px in the
  clause's tier colour, and listed under "Why flagged".
- **Risk summary:**
  - **Counts:** four tier counts in Caslon Display numerals.
  - **Bar:** a stacked tier bar, 10px tall, `--radius-sm`, with segments in tier colours. Unflagged clauses are drawn in `--rule`.
  - **Filters:** buttons with `aria-pressed` (All, High, Medium, Low, No flags), and a live "Showing N of M" line.
  - **Tallies:** category counts.
- **Clause card:**
  - **Look:** `--surface`, a `--rule` border and a 4px left border in the tier colour (unflagged: `--rule`).
  - **Title:** the title button holds "§ number", the heading, the tier badge and a chevron.
  - **Body:** a four-line preview that expands to the full text.
  - **Expanded:** adds the category chips and "Why flagged".
  - **Offsets:** in `--ink-2` tabular numbers.
  - **"long" badge:** unchanged.
- **Document pane (pleading paper):**
  - **Paper:** `--sunk` background with ruled lines every 2rem (a `--rule` hairline) and a double vertical margin rule on the left.
  - **Highlights:** clause highlights use the tier tint (unflagged: alternating `--span-a`/`--span-b`).
  - **Selected clause:** `--accent-tint` with a 2px `--accent` underline.
  - **Legend:** a legend above the pane names each colour.
- **Print summary:** the reader-friendly export.
  - **Opening it:** the primary "Print summary" button in the results header calls the browser's print dialog, which also offers "Save as PDF". A hint says so.
  - **What prints:** everything else on the page is hidden. The summary shows a header (seal, file name, date, tier counts), then the flagged clauses grouped High → Medium → Low, then the number of unflagged clauses and the disclaimer.
  - **Clause entries:** each one shows its § number and heading, the categories with their matched phrases, and the full text, with a left rule in the tier colour.
  - **Colours:** print always uses the light tokens on white.
- **Research export:** a quiet "For research" section at the foot of the results
  page. It holds an "Export data (JSON)" link-style button (at least 44px tall) and one sentence on what the file contains.
- **Homepage illustration:** built in HTML and CSS (no image). It's hidden from screen readers, and the copy next to it says the same thing.
- **Alerts, limits note, skeleton, footer:** as in v1, re-tokened.

## Imagery and icons

- **No photos and no stock illustration.**
- **Icons:** inline SVGs with a 1.5px stroke that use `currentColor`. They are the seal, the upload glyph, the chevron and the arrow. No emoji.
- **Favicon:** the seal on `--accent`.

## Accessibility rules

- Re-check contrast for any new colour pair. Every tier colour has a text label beside it.
- Interactive targets are at least 44×44px.
- The visible focus ring is never removed.
- Keyboard order follows reading order.
- Filters use `aria-pressed` and announce the result count.
- Decorative motion and illustrations are `aria-hidden`.
- All motion respects `prefers-reduced-motion`.
