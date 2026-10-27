# LegalLens design system (v3.2)

**Direction: "the fine print, under a lens".** People don't read terms because
the text is small and dense. LegalLens is the loupe:
- On the **homepage**, the real sample agreement is set as fine print, and you read it through a lens.
- On the **results page**, the agreement reads like a reviewed contract: the
document itself, with notes in the margin and a spotlight that moves from flag
to flag.

**Why this replaces v2 ("law library"):** v2's cream paper, navy accent, Caslon
display type, double rules and uppercase labels matched the look most
generated sites default to. Its results page split the work into identical
cards beside a side pane, which pushed the document aside. v3 makes the
document the interface.

**v3.2: palette from the taste skill.** The cobalt (v3) and pine/mint (v3.1)
accents still read as AI-made. Colour now follows the VectorLab taste skill's
**Notion** archetype, which it maps to content-first reading products: warm stone
paper, soft grey body text, and one muted accent, here olive. Elevation comes
from a background step and a border, not shadow.

Also in v3.2:
- **Theme toggle:** a manual light/dark switch, remembered between visits.
- **Landing backdrop:** the all-pages drifting backdrop is replaced by a
  landing-page scanner. The fine print drifts past a scan line in the hero, and
  risky phrases light up red or amber as they cross it.

**Not based on real sites:** UXKIN wasn't connected, so this direction comes
from the brief and the subject (fine print, proofreading, the loupe), not from
studying comparable sites.

Project rules for the UI/UX skills (aesthetic reference, accessibility target,
banned patterns, the two motion exceptions) are in `.ux-profile.md`. Tokens are CSS custom properties
in `webapp/static/app.css`. Pages use the names, never raw values.

## Color

- **Archetype:** Notion, from the taste skill. Stone paper, soft grey text, one muted accent.
- **How tokens are written:** each token holds both themes with CSS `light-dark()`.
  - **Default:** the page follows the system theme.
  - **Toggle:** the masthead toggle pins a theme by setting `data-theme` on `<html>`.
  - **Remembered:** the choice is saved in `localStorage` and applied before first paint.
  - **Print:** always light.
- **Accent:** muted olive (sage in dark), used only for actions, links, focus, the lens and the current flag.
- **Tiers:** Notion's muted red ("risk") and amber ("review"), plus grey. They are always shown next to their word.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--desk` | `#F7F6F3` | `#191919` | L0 page background, stone / charcoal (set on `html`) |
| `--sheet` | `#FFFFFF` | `#202020` | L1: the document, tables, inputs, upload zone |
| `--ink` | `#37352F` | `#E3E2E0` | Text |
| `--ink-2` | `#64635E` | `#9B9A97` | Secondary text, notes, headings between clauses |
| `--rule` | ink at 9% | white at 9.4% | Hairlines, the margin rule |
| `--rule-strong` | `#8C8B86` | `#6F6E6B` | Borders that identify a control |
| `--lens` / `--on-lens` | `#5E6B3A` / `#FFFFFF` | `#B5C08A` / `#191919` | The one accent: olive / sage |
| `--lens-tint` | `#EEF0E3` | `#2F3322` | Pressed filter, drag-over |
| `--current` | `#F7F8F0` | `#24261F` | Background of the clause in the spotlight |
| `--high` / `--high-tint` | `#B83A35` / `#FDEBEC` | `#FF8A80` / `#45282A` | High ("review closely"); risk red. Also errors and the scan line |
| `--medium` / `--medium-tint` | `#8A5A0F` / `#FBF3DB` | `#E8B85C` / `#45391F` | Medium ("worth knowing"); review amber. Also warnings |
| `--low` / `--low-tint` | `#64635E` / `#F1F1EF` | `#9B9A97` / `#2C2C2C` | Low ("for awareness"); grey |
| `--scan-ink` | ink at 11% | text at 10% | The faint drifting fine print on the landing page |

**Measured contrast** (WCAG 2.1, every pair the pages use):
- **Text:** at least 4.95:1 in light and 4.61:1 in dark, including each tier colour on the sheet, the desk and its own tint.
- **Controls and focus rings:** at least 3.16:1.

"No flags" means no watched phrase was found. It never means "safe".

## Typography

Self-hosted, OFL-licensed, with no third-party requests. Weights are 400, 500
and 600 only. Hierarchy comes from size, not weight.

| Token | Size / line height | Face | Use |
|---|---|---|---|
| `--step-6` | 2.986rem / 1.1 | Libre Caslon Text | Homepage headline (`--step-5` below 768px) |
| `--step-5` | 2.488rem / 1.1 | Libre Caslon Text | Results title (file name) |
| `--step-3` | 1.728rem / 1.2 | Libre Caslon Text | Section titles |
| `--step-2` / `--step-1` | 1.44rem / 1.2 · 1.2rem / 1.25 | Libre Caslon Text | Sub-heads, step titles, wordmark |
| `--text-body` | 1rem / 1.55 | Source Sans 3 | Interface copy and controls |
| document | 1rem / 1.7 | Libre Caslon Text | Clause text: open leading for legal reading |
| `--text-secondary` | 0.875rem / 1.4–1.5 | Source Sans 3 | Margin notes, hints, filters |
| `--text-meta` | 0.75rem / 1.4–1.45 | either | Offsets, `kbd`, the homepage fine print. This is the floor |

- **Clause references:** "§ 2.1". An unnumbered clause is "Clause 7", by its position.
- **Case:** sentence case everywhere. No uppercase labels.
- **Numbers:** counts and offsets use tabular figures.

## Spacing and layout

- **Scale:** `--space-1` 4, `-2` 8, `-3` 12, `-4` 16, `-6` 24, `-8` 32, `-12` 48, `-16` 64, `-24` 96 (px).
- **Breakpoints:** narrow below 768px, wide from 768px up. `main` is capped at 1280px; the chrome is not.
- **Gutter:** 16px narrow, 32px wide.
- **Homepage** (route type Home/landing):
  1. **Hero:** the copy beside a stage holding the sheet with its lens and margin tag.
  2. **How it works:** one real clause in three states.
  3. **What it flags:** a framed table.
  4. **Upload.**
  5. **Notes.**
- **Results** (Pattern 2, Detail/Record):
  1. **Header:** file name, a status sentence, actions.
  2. **"What you're agreeing to":** one line per flagged category, linking to its clauses.
  3. **"How to read these results".**
  4. **Toolbar:** sticky from 768px; filters, fold toggle, flag navigation.
  5. **Reader:** the minimap rail and the sheet.
     - **Sheet:** each clause is a grid row of text plus a 15rem margin note, and a margin rule runs down the sheet.
     - **Below 768px:** notes drop under their clause, the rail is hidden, and flag navigation is pinned to the bottom.

## Shape and depth

- **Radius:** 2px for the sheet, tables and badges; 6px for controls; the lens is round.
- **Elevation:** a 1px border first, then one shadow: `--shadow-sheet` (alpha ≤ 0.06) in light, and an inset top highlight in dark.

## Motion

Tokens: 100 / 150 / 200 / 300ms. Ease-out on entry, ease-in on exit. Only
transform and opacity animate (colour and border changes take ≤150ms).

| Where | What moves |
|---|---|
| Homepage lens | **Pointer:** follows it, one frame per pointer move, writing transforms only. **Keyboard:** arrow keys move it 24px. **Previous/Next flag and touch taps:** a 300ms glide. **On load:** one 900ms pass, the first exception (see `.ux-profile.md`) |
| Margin tag | Slides level with the clause under the lens (200ms) |
| Spotlight | The other rows fade to 45% (200ms) |
| Buttons, filters, upload zone | Border and background colour (150ms) |
| Pop press | `scaleY(0.95)` from the base, 100ms ease-out. The bottom edge snaps from 3px to 1px (layout is not animated) |
| Loading | Shown after 100ms. The skeleton pulses (the only functional loop) |
| Landing scanner | The fine print drifts up one screen every 90s (Web Animations, on the compositor). Each risky phrase takes its highlight (150ms fade) as it crosses the hero's scan line. Pauses when the tab is hidden. The second documented exception. Measured: 144 fps, worst frame 7.6ms |

**Under `prefers-reduced-motion: reduce`:** every state still changes, instantly.
The lens starts parked on a flag and only moves when asked. The skeleton is
static. The scanner doesn't drift: phrases above the scan line show as flagged,
and scrolling still moves the line.

## Components

- **Masthead:**
  - **Wordmark:** a lens mark (a ring with a § and a handle) and "LegalLens".
  - **Theme toggle:** a 44px icon button (moon or sun), labelled "Dark theme", with `aria-pressed` and a "Switch to … theme" tooltip.
  - **Links:** two nav links and the primary "Upload an agreement".
  - **Below 768px:** the links fold into a Menu button, and the primary button reads "Upload".
- **Buttons:**
  - **Primary:** a lens fill.
  - **Secondary:** a sheet fill with a `--rule-strong` border.
  - **Size:** both are at least 44px tall, Source Sans 500.
  - **No arrows.**
  - **Pop press (from the user's PopButton component):** applies to buttons, filters and Menu.
    - **Rest:** a 3px bottom edge, a darker olive on primary buttons and `--rule-strong` on the rest.
    - **Press:** the edge thins to 1px and the button squashes to `scaleY(0.95)` from its base.
    - **Toggled filters:** they rest pressed in.
- **Tier badge:** an 8px square in the tier colour, then the tier name in Source Sans 600 and the tier colour, optionally followed by ", review closely". There is no pill.
- **Fine print and lens (homepage):**
  - **Base sheet:** the sample rendered twice. The base sheet hides evidence.
  - **Lens copy:** the copy inside the lens (scale 2, clipped to a circle with `border-radius` and `overflow: hidden`) shows it with the tier tint.
  - **Without JS:** the base sheet shows the evidence.
- **Annotated document (results):**
  - **Text:** clause text in Caslon. Flagged clauses carry a 3px tier rule at the left, and evidence is underlined 2px in the tier colour.
  - **Margin note:** the tier badge; then each category's name, description and the phrases it matched; then the clause reference and offsets.
- **Spotlight:** the current clause gets `--current`, a 3px lens rule and tinted evidence. Keys: `j`/`k` move between flags (ignored while typing), Esc clears.
- **Minimap rail:** one tick per row, as tall as the row and coloured by tier. A lens-outlined window shows the visible part. It is mouse-only (`aria-hidden`); the brief's links and Previous/Next are the keyboard path.
- **Landing scanner** (homepage only):
  - **Scanfield:** a fixed, `aria-hidden` layer of the sample's fine print. It is 12px Caslon in `--scan-ink`, faded at the top and bottom edges.
  - **Phrases:** each risky phrase is a `mark.scan-hit`, red (`risk`) for High and amber (`review`) for Medium and Low.
  - **Scan line:** a 2px `--high` line across the hero at 58% of its height, with a 32px fading band and a "Scanning" label.
  - **The flagging rule:** a phrase is flagged exactly when it is above the line. It is purely positional, so the loop of two identical copies has no seam.
  - **Readability:** a feathered patch of desk colour behind the hero copy keeps it readable over the highlights.
  - **Print:** hidden.
- **Print summary:** unchanged in structure. Light tokens on white, headings in Source Sans 600.

## Imagery and icons

No photos and no illustration. The homepage's only visual is the real sample
agreement. Icons are inline SVG with a 1.5px stroke and `currentColor`. The
favicon is the lens mark on olive.

## Accessibility rules

- **Contrast:** re-check it for any new colour pair. Tier colours always appear next to their word.
- **Targets:** at least 44×44px.
- **Focus:** `:focus-visible` is a 2px lens outline with a 2px offset, and it is never removed.
- **Keyboard:** tab order follows reading order. The lens is a focusable group with an arrow-key hint in its label, and its tag is `aria-live`. Flag moves are announced through a status region.
- **Hidden from screen readers:** decorative visuals (the fine-print sheet, the lens, the rail) are `aria-hidden`.
