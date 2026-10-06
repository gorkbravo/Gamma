---
name: Gamma Website
description: The marketing surface for Gamma — a read-only research terminal that shows its work, documented as one instrument plane on a ruled ground.
colors:
  bg-0: "#070809"
  bg-1: "#0b0d10"
  bg-2: "#0f1114"
  bg-3: "#131618"
  panel-border: "#2f3641"
  panel-strong: "#46505e"
  rule: "rgba(70, 80, 94, 0.30)"
  text-0: "#f0f2f5"
  text-1: "#c2c8d0"
  text-2: "#8a919a"
  text-3: "#626973"
  accent: "#7aa6c8"
  accent-hover: "#93b9d6"
  accent-ink: "#06171f"
  accent-2: "#c49a5a"
  positive: "#4bb474"
  negative: "#d97a70"
  warning: "#c49a5a"
  hover-bg: "rgba(122, 166, 200, 0.06)"
  active-bg: "rgba(122, 166, 200, 0.12)"
  focus-ring: "rgba(122, 166, 200, 0.55)"
typography:
  display:
    fontFamily: "Archivo, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
    fontSize: "clamp(2.35rem, 5.1vw, 4.35rem)"
    fontWeight: 600
    lineHeight: 0.98
    letterSpacing: "-0.042em"
  headline:
    fontFamily: "Archivo, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
    fontSize: "clamp(1.6rem, 3vw, 2.45rem)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.028em"
  title:
    fontFamily: "Archivo, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
    fontSize: "clamp(1.05rem, 1.5vw, 1.28rem)"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Archivo, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
    fontVariant: "tabular-nums"
  body-sm:
    fontFamily: "Archivo, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Archivo, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
    fontSize: "0.625rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.14em"
    textTransform: "uppercase"
  data:
    fontFamily: "'JetBrains Mono', 'Cascadia Mono', Consolas, ui-monospace, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
    fontVariant: "tabular-nums"
rounded:
  sm: "2px"
  md: "4px"
  round: "50%"
spacing:
  s2: "4px"
  s3: "6px"
  s4: "8px"
  s5: "12px"
  s6: "16px"
  s7: "24px"
  s8: "40px"
  s9: "64px"
  s10: "104px"
  gutter: "clamp(16px, 3.4vw, 44px)"
components:
  button:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.text-0}"
    rounded: "{rounded.md}"
    padding: "11px 20px"
    typography: "{typography.body-sm}"
  button-hover:
    backgroundColor: "{colors.bg-3}"
    textColor: "{colors.text-0}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.md}"
    padding: "11px 20px"
    typography: "{typography.body-sm}"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.accent-ink}"
  button-compact:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.text-0}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  badge:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.sm}"
    padding: "2px 6px"
    typography: "{typography.label}"
  badge-live:
    textColor: "{colors.positive}"
  badge-mock:
    textColor: "{colors.warning}"
  badge-accent:
    textColor: "{colors.accent}"
  badge-plan:
    textColor: "{colors.text-3}"
  nav-link:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
    typography: "{typography.body-sm}"
  nav-link-current:
    backgroundColor: "{colors.bg-2}"
    textColor: "{colors.text-0}"
  card:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.md}"
    padding: "24px"
  cell:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "0"
    padding: "16px"
    height: "176px"
  cell-hover:
    backgroundColor: "{colors.bg-1}"
  table-header:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.text-3}"
    padding: "12px 16px"
    typography: "{typography.label}"
  table-cell:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    padding: "12px 16px"
    typography: "{typography.data}"
  mark-point:
    backgroundColor: "rgba(7, 8, 9, 0.88)"
    textColor: "{colors.accent}"
    rounded: "{rounded.round}"
    size: "19px"
  code-block:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.text-1}"
    rounded: "{rounded.md}"
    padding: "16px"
    typography: "{typography.data}"
---

# Design System: Gamma Website

> Scope: the marketing site at `website/` only. Gamma's application frontend has its
> own doctrine at `docs/design_principles.md` and its own tokens at
> `frontend/src/lib/theme/tokens.css`. This file records what the static site
> actually implements, and where it deliberately diverges from its parent.

## Overview

**Creative North Star: "The Desk Session"**

The site is not a page about a terminal; it is a plane of instrument surfaces with a
morning of research laid across it. The ground is a fixed ruled graticule — four
repeating-gradient layers under a radial mask — so the whole document reads as
something measured rather than something composed. Content sits on that ground in
seamed regions divided by hairline borders, never in floating cards. A fixed time
rail on the left carries the session's timestamps like the scale on an instrument;
it activates only while the session is in view, because a rail that tracked the whole
document would be a minimap, and a minimap is decoration.

The palette, the two typefaces and the semantic colors are inherited wholesale from
Gamma's implemented application tokens. Nothing here is a marketing-only color. The
one structural inversion is typographic: the application defaults to mono and opts
into sans for chrome, while the site defaults to the display sans and opts a named
list of data classes into mono — the same Two-Type Rule, entered from the other
side, because the site carries prose the app does not.

Restraint is enforced by role, not by taste. Chrome is grey on grey; hue appears only
where a value has direction or a state has a name. The only two shadows in the system
sit under the two objects that depict a screen. The refusal the product is built on —
Gamma cannot place an order — is given a full seamed region with semantic checkmarks
and crosses rather than a footnote, and every sample value on the page wears a
`MOCK` badge, because a marketing surface that quietly showed synthetic numbers as
live would contradict the product it is selling.

**Key Characteristics:**

- Ruled graticule ground, fixed behind everything, masked to fade downward
- One accent (`#7aa6c8`), used for state and action only; data supplies the rest of the color
- Hairline seams (1px) instead of gaps, cards, or radii above 4px
- Instrument caps: 10–11px uppercase labels at 0.10–0.16em tracking name every region
- Every number, ticker, timestamp, path and stamped label is monospace
- Sample data is always badged; planned things are always dashed
- Motion is functional — a pour-in on entry, a sweep that tracks reading position, one board that ticks
- Nothing is hidden by an `overflow-x` mask; wide content scrolls inside its own container

## Colors

A near-black instrument ground with four graded greys above it, one cool blue accent,
and a small semantic set that only data is allowed to wear.

### Primary

- **Instrument Blue** (`#7aa6c8`): The single chrome accent. It marks the primary
  action, the selected tab's underline, the live tick on the time rail, the specimen
  markers on screenshots, the handoff value, the focus ring, and links. Its tints
  (`rgba(122,166,200,0.06)` hover, `0.12` active, `0.28` selection) are the only
  interactive fills in the system. On a filled primary button the ink is a very dark
  blue-black (`#06171f`) rather than pure black, so the button reads as tinted metal.
- **Instrument Blue Bright** (`#93b9d6` on buttons, `#9dc0dc` on links): the hover
  step. Hover brightens the accent; it never changes its hue.

### Secondary

- **Brass** (`#c49a5a`): the analytical second color, doubling as `warning`. It marks
  environment-variable strings, values inside command blocks, the `MOCK` badge, the
  degradation note's left rule, and inline `code` in data tables. It is not a second
  brand color and never appears on chrome, a heading, or a button.

### Tertiary

- **Signal Green** (`#4bb474`): a positive value, an operating provider, a `LIVE`
  badge, the running dot on the live board, and the "what it does" column of the
  boundary region.
- **Signal Red** (`#d97a70`): a negative value and the "what it refuses" column of the
  boundary region. It is a muted terracotta, not an alarm red — a falling number is
  information, not an error.

### Neutral

- **Terminal Ground** (`#070809`): the page field, the live board's body, and the
  screenshot frame's backing. The topbar sits on it at 86% opacity with a 14px blur.
- **Recessed Grey** (`#0b0d10` / `#0f1114` / `#131618`): three functional steps used
  for, in order, panel and card fill, chrome fill (buttons at rest, badges' inline
  code, the environment string), and the button hover step. They are layer
  distinctions, not decoration; a surface that has no functional reason to recede
  stays on the ground.
- **Seam Grey** (`#2f3641`): the standard 1px border for every region, panel, card,
  table and frame.
- **Emphasis Seam** (`#46505e`): the hover/emphasis border, the dashed handoff chip,
  and the scrollbar thumb.
- **Hairline** (`rgba(70,80,94,0.30)`): the internal rule — between rows inside a
  panel, under a moment, along the rail. Internal division is always fainter than
  region division.
- **Text ramp** (`#f0f2f5` → `#c2c8d0` → `#8a919a` → `#626973`): headings and key
  values; body and data; supporting prose and secondary values; labels, captions,
  units and metadata. Four steps, no more.
- **Graticule ramp** (`--grid-major` `rgba(96,108,124,0.30)` → `--grid-row` `0.22` →
  `--grid-minor` `0.13` → `--grid-subrow` `0.09`): the four ruled divisions of the
  fixed measuring ground, coarse to fine. One hue, four alphas; the coarse divisions
  read first and the fine ones only reward looking. These are ground tokens, never
  borrowed for a border or a rule inside a panel — that is `--rule`'s job.

### Named Rules

**The Data-Owns-Color Rule.** Chrome is grey. Hue enters only where a value has a
direction (positive/negative), a state has a name (live/mock/planned), or an action is
primary. A section heading, a nav item at rest, a card border, and a body paragraph
are never colored.

**The One-Accent Rule.** `#7aa6c8` is the only chrome accent on the site. `#c49a5a`
is analytical — warnings, environment values, sample-data badges — and never a second
brand color. If a new element wants a third color, it wants a semantic role that
already exists.

**The Labeled-Absence Rule.** Anything sample, planned, or degraded says so in
color and in shape: sample data wears a brass `Mock` badge, planned things wear a
dashed grey `badge-plan`, and a degradation note carries a brass left rule. No
synthetic value on this site is ever presented unbadged.

## Typography

**Display Font:** Archivo (variable, self-hosted `archivo-var-latin.woff2`, weights
400–700; falls back to Segoe UI Variable Text / Segoe UI / system-ui)
**Body Font:** Archivo — the site's document default
**Label/Mono Font:** JetBrains Mono (variable, self-hosted
`jetbrainsmono-var-latin.woff2`, weights 400–700; falls back to Cascadia Mono /
Consolas / ui-monospace)

Both faces are preloaded and served with `font-display: swap` and a Latin subset
`unicode-range`, so the page never waits on a network font and never ships a face it
does not use.

**Character:** Archivo's condensed, high-x-height grotesque gives the chrome an
instrument-panel voice — tight, engineered, legible at 10px in caps. JetBrains Mono
gives every number a column to stand in. The pairing is a control panel and its
readout, and the boundary between them is the system's most load-bearing rule.

### Hierarchy

- **Display** (600, `clamp(2.35rem, 5.1vw, 4.35rem)`, line-height 0.98, tracking
  -0.042em, max 17ch): the page thesis, once per page, upper-left. Its 17ch measure
  forces the break, so the headline is set rather than wrapped.
- **Headline** (600, `clamp(1.6rem, 3vw, 2.45rem)`, line-height 1.08, tracking
  -0.028em): section heads and the closing call.
- **Title** (600, `clamp(1.05rem, 1.5vw, 1.28rem)`, line-height 1.25, tracking
  -0.02em, max 24ch): the question at the top of each moment, and each setup step.
- **Body** (400, 0.95rem, line-height 1.55, tabular numerals): the document default.
  The hero lede runs to 62ch at `clamp(0.95rem, 1.2vw, 1.06rem)` / 1.62; moment prose
  runs to 46ch; step prose to 72ch; FAQ answers to 70ch.
- **Body Small** (400, 0.8125rem, line-height 1.6–1.7): the working size for section
  subheads, card prose, table cells, and answers.
- **Label** (600, 0.625rem or 0.6875rem, uppercase, tracking 0.10–0.16em): every
  region name — section labels, table headers and captions, badges, the code block's
  head, the shot bar, the rail ticks, the pull-quote's cite, the footer's column
  heads. This size is a label, never prose.

### Named Rules

**The Two-Type Rule.** Sans explains the instrument; mono carries the research.
Inherited verbatim from `docs/design_principles.md`, but implemented from the
opposite default: `body` is Archivo, and mono is opt-in via one named selector list in
the stylesheet (tape and data tables, badges, moment timestamps, fact lists, the
handoff chip, key-card definition lists and env strings, the live board's bar and
provenance rows, the shot bar and legend numbers, specimen markers, rail ticks, the
surface index, cell mode strings, the pull cite, step numbers, code blocks, and
inline `code`). **Adding a data element means adding its class to that list**, not
setting `font-family` locally. Never set sans on a number; never force navigation
into mono because the product is terminal-like.

**The Instrument-Caps Rule.** Every structural label is 10–11px, weight 600,
uppercase, tracked 0.10–0.16em, in `--text-3`. A label names a container that is
present; it is never a floating eyebrow above a headline, and it never carries a
sentence.

**The Tracking-Inversion Rule.** Tracking runs negative as type grows and positive as
it shrinks: -0.042em at display, -0.028em at headline, -0.02em at title, normal at
body, +0.08em to +0.16em at label. A 10px cap set at normal tracking is a bug.

## Layout

**The page shell.** A `1400px` max-width container (`1560px` for the wide plane
regions) centered with a fluid gutter of `clamp(16px, 3.4vw, 44px)`. The topbar is
sticky at 46px, translucent (`rgba(7,8,9,0.86)`) with a 14px saturating blur, and
seamed underneath.

**The graticule.** A `position: fixed` full-viewport layer at `z-index: 0`, painted
from four `repeating-linear-gradient` layers — vertical rules at 10% (30% opacity) and
2% (13%), horizontal rules at 120px (22%) and 24px (9%) — under a radial ellipse mask
that holds the ground solid at the top and fades it to 25% at the bottom. A grain
layer at `z-index: 1` and 16% opacity sits above it; page content sits at `z-index: 2`.

**The time rail.** Fixed at the left, 92px wide, from the topbar to the viewport
bottom, at `z-index: 30`. Its ticks are generated from the session's `data-moment`
articles and placed on **even divisions** (10% + i × 80/(n-1)) rather than at document
offsets, because the rail is an instrument scale, not a scroll map. It is
`pointer-events: none` and `opacity: 0` until the session section occupies the reading
band, then fades in over 420ms and enables its ticks. It is `display: none` below
1180px; above it, `.has-rail .page` pays for it with `padding-left: calc(92px +
gutter)` so content never runs under the rail.

**Spacing rhythm.** A nine-step scale from 4px to 104px (`--s2`…`--s10`), with the
large steps carrying section rhythm: sections at 104px, tight sections and moments at
64px, region padding at 24px, cell padding at 16px, and row padding at 8–12px.
Vertical rhythm is expressed as padding on seamed regions, not as margins between
floating blocks.

**Grids.** The hero pairs content with a 300px sidebar. Moments run
`minmax(280px, 380px) minmax(0, 1fr)` with a sticky meta column, collapsing to a
single column at 1000px. The surfaces plane and the boundary region are
`auto-fill` / `auto-fit` grids that draw their own seams: the container takes
`border-top` and `border-left`, each cell takes `border-right` and `border-bottom`, so
no seam ever doubles and the region reads as one ruled field regardless of how the
tracks reflow.

**Breakpoints as used:** 620px (drop the brand subtitle), 640px (surface index goes
two-up), 760px (screenshot frames become pannable; section subheads left-align),
820px (live board stacks), 860px (nav becomes a scroll strip), 1000px (moments
stack), 1080px (hero stacks), 1100px (surface index goes five-up), 1180px (time rail
appears).

### Named Rules

**The Fluid-Minimum Rule.** Every auto-placed grid track is written
`minmax(min(Npx, 100%), 1fr)`. The `min()` guarantees the declared minimum never
exceeds the viewport, so no grid can push the page wider than the screen at any width.

**The No-Mask Rule.** There is no `overflow-x: hidden` anywhere in the system. Wide
content is given its own scroll container instead — the table wrapper, the code block's
`pre`, the live board's tab strip, the nav strip below 860px, and the screenshot frame
below 760px (where a 1920px capture becomes a 740px-wide pannable viewport labelled
"drag to pan"). Hiding overflow hides a layout bug; scrolling it admits one honestly.

**The Seam Rule.** Regions are separated by 1px borders, not by gaps or drop shadows.
Region seams use `--panel-border`; divisions inside a region use the fainter
`--rule` or a ~14% alpha hairline. A gap where a seam belongs makes the plane read as
loose cards.

## Elevation & Depth

The system is flat by doctrine. Depth is carried by four tonal steps
(`#070809` → `#0b0d10` → `#0f1114` → `#131618`) and by hairline borders. Chrome —
buttons, badges, nav, cards, cells, tables, code blocks — casts no shadow at any
state; hover moves a surface one tonal step or brightens its border instead.

Exactly two drop shadows exist, and both belong to objects that depict a screen: the
live board and the screenshot plate. Both are wide, very soft, heavily negative-spread
shadows that read as a plate lifted a few millimetres off the ground, not as a card.
Two further shadows are glows, not elevation: the rail sweep's accent bleed and the
specimen marker's halo, which also carries a 3px ground-colored ring so the marker
stays legible over any pixel of a screenshot.

### Shadow Vocabulary

- **Board lift** (`box-shadow: 0 24px 60px -30px var(--shadow-panel)`): the live
  demonstration board.
- **Plate lift** (`box-shadow: 0 30px 70px -40px var(--shadow-cast)`): a captured
  application screen.
- **Sweep glow** (`box-shadow: 0 0 8px rgba(122,166,200,0.5)`): the reading-position
  sweep on the time rail.
- **Marker halo** (`box-shadow: 0 0 0 3px var(--shadow-ring), 0 0 12px rgba(122,166,200,0.35)`):
  a specimen marker sitting on a screenshot.

Depth values are tokens (`--shadow-cast`, `--shadow-panel`, `--shadow-ring`, `--ink`),
not literals. A new shadow uses one of them or it is not in the system.

### Named Rules

**The Flat-Chrome Rule.** Only an object that depicts a screen may cast a shadow.
Everything else conveys depth with a tonal step and a hairline. A shadow on a button,
a badge, a card, or a table is out of system.

## Shapes

**Square, nested, hairline.** Two radii exist: 2px for small chrome (badges, inline
code, nav pills, the step index, the copy button, the focus ring) and 4px for
containers (buttons, cards, frames, tables, code blocks). Nothing in the system is
softer than 4px, and the grid regions — the surfaces plane, the boundary, the table
body — are square, with radius living only on the outer wrapper.

**Circles are reserved for markers.** `border-radius: 50%` appears only on status and
index tokens: the live dot (5px), the specimen marker on a screenshot (19px), and its
matching legend number (16px). A circle in this system means "this is a point being
pointed at."

**Dashed means provisional.** A dashed border marks something not yet fixed or not
yet live: the handoff chip that shows what one surface forwards to the next, and the
`badge-plan` for a provider that is planned but not integrated.

**A left rule means annotation.** A one-sided 1px border with left padding marks an
aside about the thing above it: accent for the live board's explanatory note, brass
for a degradation warning.

**Leader dots.** The surface index draws its own leader between name and mode count
with a flex-grown `::after` carrying a dotted bottom border — a printed-index device,
not a decorative divider.

## Components

Chrome is quiet at rest and states itself only on interaction. Every component is
built from the same four materials: a tonal fill, a hairline border, one radius step,
and instrument caps.

### Buttons

- **Shape:** softly squared (4px radius), 1px `--panel-border`, `11px 20px` padding,
  inline-flex with an 8px gap for an optional 13px stroked SVG.
- **Default:** recessed chrome fill (`--bg-2`) with primary text (`--text-0`) at
  0.8125rem / 600 in the display face.
- **Primary:** the accent as a solid fill with dark blue-black ink (`#06171f`). One
  per view; it is the only filled element on the page.
- **Hover / Active:** the default lifts one tonal step to `--bg-3` and brightens its
  border to `--panel-strong`; the primary brightens to `#93b9d6`. Both press down 1px
  on `:active`. Transitions are 120ms on `cubic-bezier(0.2, 0, 0, 1)`.
- **Compact:** inside a key card's action row, padding drops to `8px 14px` at
  0.6875rem.

### Chips / Badges

- **Style:** instrument caps at 0.625rem, `2px 6px`, 2px radius, transparent fill,
  1px border. The state lives in the text color and a matching 40%-alpha border:
  green for live, brass for mock, accent for a highlighted fact, and grey with a
  **dashed** border for planned.
- **State:** a badge is a statement about data, not an interactive control. It has no
  hover.

### Cards / Containers

- **Corner Style:** 4px.
- **Background:** `--bg-1` panel fill on the terminal ground.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px `--panel-border`, brightening to `--panel-strong` on hover over
  180ms — the only thing that changes.
- **Internal Padding:** 24px, with a 12px flex-column gap between the title row,
  prose, the definition list, the environment string, the degradation note, and a
  bottom-anchored action row (`margin-top: auto`).

### Tables

Two table voices. **Data tables** (`.data`) carry documentation: sticky sans caps
headers on `--bg-1`, 12/16px cells, left-aligned, top-aligned, 1.5 line-height, a row
hover tint, a bolded first column, and a 640px minimum inside a horizontally scrolling
wrapper. **Tape tables** (`.tape`) carry live values: fully monospace,
right-aligned except the first column, `nowrap`, tighter 8/16px rows, faint hairlines,
and a repriced cell flashing an accent wash that decays over 620ms.

### Navigation

Sans caps-less labels at 0.8125rem / 500 in `--text-2`, `6px 12px`, 2px radius,
transparent border. Hover raises the label to `--text-0` over the accent's 6% tint.
The current page keeps a `--bg-2` fill and a visible border. The GitHub link is a
ghost CTA: accent text on the same recessed fill, deepening to the 12% active tint on
hover. Below 860px the whole strip becomes a horizontal scroller with its scrollbar
hidden — the links stay reachable rather than collapsing behind a menu.

### Code Blocks

A 4px-radius `--bg-1` container with a seamed head carrying a sans caps shell label
and a copy button. The `pre` is monospace 0.8125rem at 1.7 line-height with a 2 tab
size, syntax marked by three spans only: comment (`--text-3`), value (brass), and
variable/parameter (accent). The copy button turns green with a green border and reads
"Copied" for 1.6s, then reverts.

### The Screenshot Plate

The site's signature component, and the reason it can show a dense terminal honestly.
A plate is a `figure` with three parts: a seamed **shot bar** (mono caps naming the
tab and workspace, with a `Mock` badge pushed right), the **frame** holding the
capture, and a **legend** strip underneath.

Annotation is numbered, never floating. A `.mark-pt` — a 19px accent-ringed circle on
a near-opaque ground disc, with a ground ring and a soft accent halo — is absolutely
positioned by percentage over the point of interest and is `pointer-events: none`. Its
explanation lives as a numbered item in the legend strip below the frame. **An
annotation can therefore never cover the thing it points at**, and the legend remains
readable when the frame is scaled down or panned.

### The Live Board

A running miniature of Gamma's own tape rather than a picture of one. A seamed bar
carries a glowing green dot, the board's name, and honest `Mock` / `Read-only`
badges. A tab strip below it (real `role="tablist"` buttons with arrow-key traversal)
switches between four boards; the selected tab drops to the ground color and takes a
2px accent underbar. The body is a 1.55fr / 1fr split: the tape on the left, and on the
right a provenance definition list — source, origin, transformation, retrieval clock —
above an accent-ruled note explaining what is a Gamma heuristic. One randomly chosen
value reprices every 1.5s with a flash; the clock restamps with it; the interval is
cleared while the tab is hidden and never starts under `prefers-reduced-motion`.

### The Time Rail

See Layout. Visually: a 92px column with a right hairline, a 44px-pitch repeating rule
track at 50% opacity, an accent sweep line growing down the right edge as the session
is read, and mono caps ticks in `--text-3` with a 12px leader dash. The tick nearest
the reading line turns accent and grows its leader to 18px.

### Steps

A two-column grid (34px / content) with a CSS counter rendering
`decimal-leading-zero` inside a 26px bordered square at 2px radius — the number is a
component, not a bullet.

### Disclosure (FAQ)

A borderless `details`/`summary` list separated by seams. The summary is display-face
at `clamp(0.95rem, 1.5vw, 1.1rem)` / 600, turning accent on hover; the native marker
is removed in favor of a 13px plus glyph that rotates 45° to a cross when open.

### Reveal & Motion

Motion tokens: 120ms for chrome state, 180ms for surface state, 620ms for the entry
pour, on `cubic-bezier(0.2, 0, 0, 1)` for state and `cubic-bezier(0.16, 1, 0.3, 1)`
for entry.

**The Visible-At-Rest Rule.** `.reveal` resolves to `opacity: 1`. The pour-in — a
620ms rise from 15px with a 3px blur clearing — is applied by adding a class on
intersection, and only inside a `prefers-reduced-motion: no-preference` block on a
`.js` root. A failed observer, a disabled script, or a reduced-motion preference
costs the animation and never the copy. Elements entering together are sorted by
their top edge and staggered 55ms apart via a `--d` custom property, so a group pours
top-to-bottom rather than arriving at once.

## Do's and Don'ts

### Do:

- **Do** inherit the palette from Gamma's application tokens. This site has no
  marketing-only color, and adding one would break the claim that the screenshots and
  the page are the same world.
- **Do** add a new data element's class to the mono selector list in `site.css`
  rather than setting `font-family` on it locally. That list is the Two-Type Rule's
  only implementation.
- **Do** name every region with instrument caps (10–11px, 600, uppercase,
  0.10–0.16em) in `--text-3`.
- **Do** separate regions with a 1px `--panel-border` seam and divide inside them with
  the fainter `--rule`.
- **Do** write auto-placed grid tracks as `minmax(min(Npx, 100%), 1fr)`.
- **Do** give wide content its own scroll container, and label it when the gesture is
  not obvious (the screenshot frame's "drag to pan" below 760px).
- **Do** badge every synthetic value `Mock` and every uncontracted provider
  `badge-plan` with its dashed border, on this site as in the app.
- **Do** annotate a screenshot with a numbered `.mark-pt` plus a legend row, and keep
  the marker `pointer-events: none`.
- **Do** keep `.reveal`'s resting state visible and animate only on entry.
- **Do** state a limit plainly and give it weight — the boundary region is a full
  seamed field, not a disclaimer.

### Don't:

- **Don't** put a shadow on chrome. Only the live board and the screenshot plate cast
  one; everything else uses a tonal step and a hairline.
- **Don't** introduce a radius above 4px, or use a circle for anything that is not a
  status dot or a numbered marker.
- **Don't** color chrome. A heading, a nav item at rest, a card border, or a body
  paragraph is grey; hue belongs to values, states, and the one primary action.
- **Don't** treat brass (`#c49a5a`) as a second brand accent. It is the analytical /
  warning role: env strings, code values, mock badges, degradation rules.
- **Don't** add `overflow-x: hidden` anywhere. If something overflows, either fix the
  track minimum or give it a scroll container.
- **Don't** float a callout over a screenshot. The marker points; the legend explains.
- **Don't** set a 10px uppercase label at normal tracking, or set display type without
  negative tracking.
- **Don't** let the time rail track the whole document or appear below 1180px — it
  belongs to the session section and needs its own 92px column.
- **Don't** hide content behind a scroll-triggered animation. If the observer never
  fires, the page must still read completely.
- **Don't** show a number on this site that a real Gamma surface could not produce,
  and never show one without its provenance or its `Mock` badge.
