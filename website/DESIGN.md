---
name: Gamma Website
description: The marketing surface for Gamma — a read-only research workspace that shows its work, documented as one plane of borderless tonal sheets in the app's B′ "Tonal compact" look, light and dark.
# Every colour exists twice, one per theme, under the same role name with a
# -dark or -light suffix; site.css swaps the -light values in when the OS asks
# for light (System is the default). Components below reference the -dark
# values; the light theme uses each token's -light twin.
colors:
  canvas-dark: "#0b0e12"
  panel-bg-dark: "#151a20"
  tint-dark: "#1b2129"
  button-bg-dark: "color-mix(in srgb, #edf1f6 8%, transparent)"
  surface-0-dark: "#181d24"
  panel-border-dark: "#232a33"
  panel-strong-dark: "#343d49"
  divider-dark: "#212830"
  text-0-dark: "#edf1f6"
  text-1-dark: "#b8c1cc"
  text-2-dark: "#8a95a3"
  accent-dark: "#7d9df2"
  accent-soft-dark: "color-mix(in srgb, #7d9df2 14%, transparent)"
  accent-2-dark: "#e0aa50"
  positive-dark: "#45c48b"
  positive-soft-dark: "color-mix(in srgb, #45c48b 14%, transparent)"
  negative-dark: "#f2806f"
  negative-muted-dark: "#dc7465"
  negative-soft-dark: "color-mix(in srgb, #dc7465 14%, transparent)"
  warning-dark: "#e0aa50"
  warning-soft-dark: "color-mix(in srgb, #e0aa50 14%, transparent)"
  hover-bg-dark: "color-mix(in srgb, #7d9df2 6%, transparent)"
  active-bg-dark: "color-mix(in srgb, #7d9df2 14%, transparent)"
  focus-ring-dark: "#7d9df2"
  scrim-dark: "rgba(0, 0, 0, 0.45)"
  canvas-light: "#eceff3"
  panel-bg-light: "#ffffff"
  tint-light: "#f4f6f9"
  button-bg-light: "color-mix(in srgb, #0f1720 8%, transparent)"
  surface-0-light: "#f8f9fb"
  panel-border-light: "#e3e7ec"
  panel-strong-light: "#cfd6df"
  divider-light: "#eef1f4"
  text-0-light: "#0f1720"
  text-1-light: "#3b4655"
  text-2-light: "#636e7f"
  accent-light: "#2952cc"
  accent-soft-light: "color-mix(in srgb, #2952cc 9%, transparent)"
  accent-2-light: "#8a5a00"
  positive-light: "#0c7049"
  positive-soft-light: "color-mix(in srgb, #0c7049 13%, transparent)"
  negative-light: "#b83329"
  negative-muted-light: "#b83329"
  negative-soft-light: "color-mix(in srgb, #b83329 13%, transparent)"
  warning-light: "#8a5a00"
  warning-soft-light: "color-mix(in srgb, #8a5a00 13%, transparent)"
  hover-bg-light: "color-mix(in srgb, #2952cc 4%, transparent)"
  active-bg-light: "color-mix(in srgb, #2952cc 9%, transparent)"
  focus-ring-light: "#2952cc"
  scrim-light: "rgba(18, 26, 38, 0.22)"
typography:
  display:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "clamp(2.35rem, 5.1vw, 4.25rem)"
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: "-0.02em"
    fontVariant: "tabular-nums"
  headline:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "clamp(1.6rem, 3vw, 2.4rem)"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.015em"
    fontVariant: "tabular-nums"
  title:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "clamp(1.05rem, 1.5vw, 1.25rem)"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "normal"
    fontVariant: "tabular-nums"
  body:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
    fontVariant: "tabular-nums"
  body-sm:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
    fontVariant: "tabular-nums"
  panel-title:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  label:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "normal"
  figures:
    fontFamily: "'Instrument Sans', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, 'Helvetica Neue', Roboto, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "normal"
    fontVariant: "tabular-nums"
  code:
    fontFamily: "'JetBrains Mono', 'Cascadia Mono', Consolas, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: "normal"
rounded:
  mark: "2px"
  control: "5px"
  panel: "6px"
  overlay: "12px"
  pill: "999px"
  round: "50%"
spacing:
  s1: "2px"
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
    backgroundColor: "{colors.button-bg-dark}"
    textColor: "{colors.text-0-dark}"
    rounded: "{rounded.control}"
    padding: "6px 16px"
    height: "36px"
    typography: "{typography.body-sm}"
  button-ghost:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.control}"
    padding: "6px 16px"
    height: "36px"
  button-primary:
    backgroundColor: "{colors.accent-soft-dark}"
    textColor: "{colors.accent-dark}"
    rounded: "{rounded.control}"
    padding: "6px 16px"
    height: "36px"
    typography: "{typography.body-sm}"
  button-compact:
    backgroundColor: "{colors.button-bg-dark}"
    textColor: "{colors.text-0-dark}"
    rounded: "{rounded.control}"
    padding: "4px 8px"
    height: "28px"
  tag:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.pill}"
    padding: "0 6px"
    height: "17px"
    typography: "{typography.label}"
  tag-live:
    backgroundColor: "{colors.positive-soft-dark}"
    textColor: "{colors.positive-dark}"
  tag-mock:
    backgroundColor: "{colors.warning-soft-dark}"
    textColor: "{colors.warning-dark}"
  tag-delayed:
    backgroundColor: "{colors.warning-soft-dark}"
    textColor: "{colors.warning-dark}"
  tag-accent:
    backgroundColor: "{colors.accent-soft-dark}"
    textColor: "{colors.accent-dark}"
  tag-plan:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-2-dark}"
  nav-link:
    backgroundColor: "transparent"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.control}"
    padding: "4px 12px"
    typography: "{typography.body-sm}"
  nav-link-hover:
    backgroundColor: "{colors.hover-bg-dark}"
    textColor: "{colors.text-0-dark}"
  nav-link-current:
    backgroundColor: "{colors.active-bg-dark}"
    textColor: "{colors.text-0-dark}"
  nav-cta:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.control}"
    padding: "4px 12px"
  sheet:
    backgroundColor: "{colors.panel-bg-dark}"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.panel}"
    padding: "24px"
  block:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.panel}"
    padding: "8px 12px"
  cell:
    backgroundColor: "{colors.panel-bg-dark}"
    textColor: "{colors.text-1-dark}"
    rounded: "{rounded.panel}"
    padding: "16px"
    height: "176px"
  table-header:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-2-dark}"
    padding: "6px 10px"
    typography: "{typography.label}"
  table-cell:
    backgroundColor: "transparent"
    textColor: "{colors.text-1-dark}"
    padding: "8px 10px"
    typography: "{typography.figures}"
  segmented-track:
    backgroundColor: "{colors.tint-dark}"
    rounded: "{rounded.panel}"
    padding: "2px"
  segmented-selected:
    backgroundColor: "{colors.panel-bg-dark}"
    textColor: "{colors.text-0-dark}"
    rounded: "{rounded.control}"
    padding: "3px 12px"
  mark-point:
    backgroundColor: "{colors.panel-bg-dark}"
    textColor: "{colors.accent-dark}"
    rounded: "{rounded.round}"
    size: "19px"
  code-block:
    backgroundColor: "{colors.panel-bg-dark}"
    textColor: "{colors.text-0-dark}"
    rounded: "{rounded.panel}"
    padding: "12px"
    typography: "{typography.code}"
  code-head:
    backgroundColor: "{colors.tint-dark}"
    textColor: "{colors.text-2-dark}"
    padding: "2px 6px 2px 12px"
    height: "32px"
    typography: "{typography.label}"
---

# Design System: Gamma Website

> Scope: the marketing site at `website/` only. Gamma's application frontend has its
> own doctrine at `docs/design_principles.md` and its own tokens at
> `frontend/src/lib/theme/tokens.css`. This file records what the static site
> actually implements, and where it deliberately differs from its parent.

## Overview

**Creative North Star: "The Desk Session"**

The site is a morning of research laid across one plane: a cool, flat canvas with
borderless tonal sheets on it, exactly as the application builds a workspace. The
canvas carries the page's headings and the hero; everything that holds evidence — the
live board, each moment of the session, the surface cells, the boundary, every table,
key card, code block and FAQ list, and the footer — is a sheet one tonal step above
it, separated by 8px seams or by canvas space between sections. A sheet's edge is its
change of tone, never a line. A time rail on the left carries the session's
timestamps like the scale on an instrument; it activates only while the session is
in view, because a rail that tracked the whole document would be a minimap.

The palette, the type and the shapes are the application's B′ "Tonal compact" tokens,
copied value for value into `site.css` (a static site cannot import the app's
stylesheets). There is no marketing-only colour. Both themes come from the same role
names and follow the operating system: the site is light when the OS is light and
dark when it is dark, which is the app's System default. Instrument Sans is the
interface, label and figure font, with tabular figures across the whole document;
a monospace appears only where the content is code.

Restraint is enforced by role, not by taste. Chrome is neutral; hue appears only where
a value has direction, a state has a name, or an action is the primary one. The
refusal the product is built on — Gamma cannot place an order — is given three full
sheets with semantic checkmarks and crosses rather than a footnote, and every sample
value on the page wears a `Mock` tag, because a marketing surface that quietly showed
synthetic numbers as live would contradict the product it is selling.

**Key Characteristics:**

- A flat cool canvas with borderless tonal sheets on it; no texture, no ruled ground
- Light and dark from one set of role names, following the OS (System by default), WCAG AA in both
- One accent, for interaction and the primary action only; data supplies the rest of the colour
- Instrument Sans everywhere, with tabular figures; JetBrains Mono for code only
- Sentence-case labels at 11px, weight 500, no letter-spacing
- Filled, edgeless controls; the primary action is an accent tint, never a solid fill
- Pill tags with a dot for state; sample data is always tagged
- Floating overlays (12px radius and the overlay shadow) are the only elevation
- Motion is functional — a pour-in on entry, a sweep that tracks reading position, one board that ticks
- Nothing is hidden by an `overflow-x` mask; wide content scrolls inside its own container

## Colors

A cool neutral plane — canvas, sheet, tint, button fill — with one blue accent and a
small semantic set that only data is allowed to wear, each defined once per theme.

### Primary

- **Interaction Blue** (`#7d9df2` dark / `#2952cc` light, `--accent`): the single
  chrome accent. It marks the primary action's tint and edge, the current page's
  selection fill in the top bar, the live tick and sweep on the time rail, the specimen markers on
  screenshots and their legend numbers, the parameter role in code, the open FAQ
  marker, links, and the focus ring. Its mixes are the only interactive fills: hover
  (`--hover-bg`, 6% dark / 4% light), selection (`--active-bg`, 14% / 9%), the soft
  fill (`--accent-soft`, 14% / 9%) and text selection (28%).

### Secondary

- **Context Gold** (`#e0aa50` dark / `#8a5a00` light, `--accent-2`): equals
  `--warning`. On the site it is the value role inside code blocks only. It is not a
  second brand colour and never appears on chrome, a heading or a button.

### Tertiary

- **Signal Green** (`#45c48b` dark / `#0c7049` light, `--positive`): a rising value, a
  live provider tag, the running dot on the live board, backwardation, the "what it
  does" checkmarks, and the copy button's confirmation.
- **Signal Red** (`#f2806f` dark / `#b83329` light, `--negative`): a falling value and
  the "what it refuses" crosses. Its soft fill mixes from `--negative-muted`
  (`#dc7465` dark / `#b83329` light), a shade quieter, so a filled cell does not shout.
- **Signal Amber** (`#e0aa50` dark / `#8a5a00` light, `--warning`): the `Mock`,
  `Sample` and `Delayed` tags, contango, and the lead of each "without it" note.

### Neutral

- **Canvas** (`#0b0e12` dark / `#eceff3` light, `--canvas`): the page behind the
  sheets. The hero, section headings and the sticky top bar sit on it.
- **Sheet** (`#151a20` dark / `#ffffff` light, `--panel-bg`): every surface that holds
  evidence, one tonal step above the canvas.
- **Tint** (`#1b2129` dark / `#f4f6f9` light, `--tint`): the quiet fill inside a sheet
  — table header bands, the code head, the board's segmented track, the provenance
  note, the handoff block, environment strings, inline code and neutral tags.
- **Button Fill** (`--button-bg`, the text colour at 8%): one step above the tint, so
  an action reads as a button without an edge, on the canvas or on a sheet.
- **Lines** (`--panel-border` `#232a33` / `#e3e7ec`, `--panel-strong` `#343d49` /
  `#cfd6df`, `--divider` `#212830` / `#eef1f4`): the selected segment's outline and
  overlay edges; the strong line (the rail's baseline, leader dots, hover edges); the
  rule between rows and inner sections.
- **Text ramp** (`--text-0` `#edf1f6` / `#0f1720`, `--text-1` `#b8c1cc` / `#3b4655`,
  `--text-2` `#8a95a3` / `#636e7f`): headings, values and identifiers; body and prose;
  labels, captions, units and metadata. Three steps, the app's, AA-tuned.

### Named Rules

**The Data-Owns-Color Rule.** Chrome is neutral. Hue enters only where a value has a
direction (positive/negative), a state has a name (live/delayed/mock/planned), or an
action is primary. A section heading, a nav item at rest, a sheet and a body
paragraph are never coloured.

**The One-Accent Rule.** `--accent` is the only chrome accent on the site. The gold is
the warning and context role and never a second brand colour. If a new element wants
a third colour, it wants a semantic role that already exists.

**The Labeled-Absence Rule.** Anything sample, delayed, planned or degraded says so in
words and in tone: sample data wears an amber `Mock` or `Sample` tag, planned things a
neutral tag with a hollow dot, and a degradation note leads with an amber phrase. No
synthetic value on this site is ever presented untagged.

**The Same-Roles-Both-Themes Rule.** Every colour is a custom property in `site.css`,
defined once in the dark `:root` block and once in the `prefers-color-scheme: light`
block, with the app's literal values. A rule names a role, never a hex value, so the
second theme is never an afterthought. `--text-2` reaches 4.5:1 on the sheet and the
tint in both themes but not on the light canvas, so text on the canvas uses
`--text-1` or `--text-0`.

## Typography

**Display Font:** Instrument Sans (self-hosted static 400/500/600/700 cuts, latin and
latin-ext subsets, from `frontend/public/fonts/` with its `OFL.txt`; falls back to
Segoe UI Variable Text / Segoe UI / the system sans)
**Body Font:** Instrument Sans — the document default, with tabular figures
**Label/Mono Font:** Instrument Sans for labels; JetBrains Mono (variable, self-hosted
`jetbrainsmono-var-latin.woff2`; falls back to Cascadia Mono / Consolas / ui-monospace)
for code only

The latin regular and semibold cuts are preloaded; every face uses `font-display:
swap` and a `unicode-range`, so the page never waits on a font and downloads latin-ext
only when it renders such a character.

**Character:** one engineered grotesque for the instrument and its readout alike.
Instrument Sans sets the headings, the prose, the labels and the numbers; its tabular
figures (`font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1` on the
body) give every number a column to stand in without turning the page into a
terminal. The monospace is reserved for text that is code.

### Hierarchy

- **Display** (600, `clamp(2.35rem, 5.1vw, 4.25rem)`, line-height 1.02, -0.02em, max
  17ch): the page thesis, once per page, upper-left.
- **Headline** (600, `clamp(1.6rem, 3vw, 2.4rem)`, line-height 1.15, -0.015em):
  section heads and the closing call.
- **Title** (600, `clamp(1.05rem, 1.5vw, 1.25rem)`, line-height 1.25, max 24ch): the
  question at the top of each moment, and each setup step. FAQ questions run a step
  smaller, `clamp(0.95rem, 1.3vw, 1.06rem)`.
- **Body** (400, 15px, line-height 1.55): the document default. The hero lede runs to
  62ch at `clamp(0.95rem, 1.2vw, 1.06rem)` / 1.62.
- **Body Small** (400, 13.5px, line-height 1.6–1.7): the working size for section
  subheads, moment prose (46ch), step prose (72ch), FAQ answers (70ch), card prose and
  table cells.
- **Panel Title** (600, 12.5px, `--text-1`): the 30px title row of a sheet — the board's
  tape title, table captions, the surface index, the boundary columns.
- **Label** (500, 11px, no letter-spacing, sentence case, `--text-2`): column headers,
  definition terms, the shot bar, the code head, group names, footer column heads,
  rail ticks. A label names something present; it never carries a sentence.
- **Code** (400, 12px JetBrains Mono, line-height 1.7): code blocks, environment
  strings and inline `code` (at 0.86em).

### Named Rules

**The Two-Type Rule.** Sans explains the instrument; tabular figures carry the
research; mono is for code. The two types are proportional interface text and tabular
data figures, both Instrument Sans: the body turns tabular figures on for the whole
document, so a number in a table, a fact list, a tag or a sentence holds its width.
JetBrains Mono is applied by one short selector list in `site.css` (`code`, `.code
pre`, `.key .env`, `.pull cite`). Never set chrome or data in a monospace because the
product handles numbers; adding a code element means adding it to that list.

**The Sentence-Case Rule.** Labels, tags, buttons, tabs and headings are sentence
case; the copy carries its own capitals. There is no `text-transform: uppercase`
anywhere in the stylesheet. Upper case appears only where the content is itself a code
— environment variables, key names, tickers, tenors — and that content is written in
capitals in the markup.

**The No-Tracking Rule.** Labels and body text carry no letter-spacing. The only
tracking on the site is a slight optical tightening of large type: -0.02em on the
display headline and -0.015em on section headlines.

## Layout

**The page shell.** A `1400px` max-width container centred with a fluid gutter of
`clamp(16px, 3.4vw, 44px)`. The top bar is sticky at 46px on the canvas itself — an
opaque canvas fill, no edge, no blur.

**The plane.** Section headings and the hero sit on the canvas; the evidence sits on
sheets. Sheets that belong together are separated by 8px seams (the moments of the
session, the surface cells, the boundary columns, the key cards); unrelated regions
are separated by canvas space: 88px above a section, 64px above a tight section, 104px
around the closing call. The footer is the last sheet, painted on the page's content
column so its edges line up with every sheet above it.

**The time rail.** Fixed at the left, 92px wide, from the top bar to the viewport
bottom, at `z-index: 30`. Its ticks are generated from the session's `data-moment`
articles and placed on **even divisions** (10% + i × 80/(n-1)) rather than at document
offsets, because the rail is an instrument scale, not a scroll map. It is
`pointer-events: none` and `opacity: 0` until the session section occupies the
reading band, then fades in over 420ms and enables its ticks. It is `display: none`
below 1180px; above it, `.has-rail .page` pays for it with `padding-left: calc(92px +
gutter)` so content never runs under the rail.

**Spacing rhythm.** `--s1`…`--s7` (2–24px) equal the app's space ramp; `--s8`–`--s10`
(40, 64, 104px) carry the page's section rhythm. Sheet padding is 16–32px, row padding
6–8px, seams 8px.

**Grids.** The live board's body is 1.55fr / 1fr, stacking at 820px. Moments run
`minmax(280px, 380px) minmax(0, 1fr)` inside their sheet with a sticky meta column,
collapsing to one column (meta capped at 620px) at 1000px. The surface cells, the
boundary and the key cards are `auto-fill` / `auto-fit` grids of sheets with an 8px
gap.

**Breakpoints as used:** 620px (drop the brand subtitle; tighter footer), 640px
(surface index goes two- and three-up), 760px (screenshot frames become pannable;
section subheads left-align), 820px (live board stacks), 860px (nav becomes a
sideways-scrolling strip), 1000px (moments stack), 1100px (surface index goes
five-up), 1180px (time rail appears).

### Named Rules

**The Fluid-Minimum Rule.** Every auto-placed grid track is written
`minmax(min(Npx, 100%), 1fr)`. The `min()` guarantees the declared minimum never
exceeds the viewport, so no grid can push the page wider than the screen; the page
has no horizontal overflow at 390px.

**The No-Mask Rule.** There is no `overflow-x: hidden` anywhere in the system. Wide
content is given its own scroll container instead — the table sheet, the code block's
`pre`, the live board's tape and segmented track, the nav strip below 860px, and the
screenshot frame below 760px (where a 1920px capture becomes a 740px-wide pannable
viewport labelled "Drag to pan"). Hiding overflow hides a layout bug; scrolling it
admits one honestly.

**The One-Plane Rule.** Regions are separated by tone and space, not by borders. A
sheet sits on the canvas, a block sits on the tint inside a sheet, and rules
(`--divider`) divide rows inside them. A line around a region turns the plane back
into outlined boxes.

## Elevation & Depth

The system is flat by doctrine and reads as one plane. Depth is carried by tonal steps
— canvas, sheet, tint, button fill — and by nothing else. Sheets, cards, tables, the
live board, code blocks and screenshot plates cast no shadow at any state; hover shows
the accent line on a control or `--hover-bg` behind a row.

Floating overlays are the only elevated surfaces, as in the app. On the site the one
overlay is the skip link, which floats above the page when focused.

### Shadow Vocabulary

- **Overlay** (`box-shadow: 0 12px 40px color-mix(in srgb, var(--shadow-ink) 32%,
  transparent)`, `--overlay-shadow`): a floating overlay, with `--overlay-radius`
  and a 1px `--panel-border` line. `--shadow-ink` is black in dark and
  `rgba(15, 23, 32, 0.4)` in light.
- **Marker ring** (`box-shadow: 0 0 0 2px color-mix(in srgb, var(--panel-bg) 70%,
  transparent)`): a 2px ring in the sheet colour that keeps a specimen marker legible
  over any pixel of a screenshot. It is a ring, not elevation.

`--scrim` (`rgba(0, 0, 0, 0.45)` dark / `rgba(18, 26, 38, 0.22)` light) is defined for
a modal overlay; the site has none today.

### Named Rules

**The Overlays-Only Rule.** Only a floating overlay may cast a shadow. Everything else
conveys depth with a tonal step. A shadow, glow or blur on a sheet, button, tag, card
or table is out of system, and so is glass.

## Shapes

**Three radii and a pill.** Controls — buttons, nav links, the copy button, segments,
the step number, environment strings — take `--radius-control` (5px). Sheets and blocks
take `--panel-radius` (6px). Floating overlays take `--overlay-radius` (12px). Tags
are pills (`--radius-pill`). Inline code keeps a 2px mark radius. Nested geometry is
square: a screenshot inside a moment's sheet and the table inside its sheet have no
radius of their own.

**No borders around things.** No sheet, card, block, field, tag or button has a border.
Lines remain where they do work: rules between rows (`--divider`), the selected
segment's 1px outline, the accent edge of the primary action, the brand mark's
accent edge, a button's accent line on hover, the focus ring,
the rail's baseline, and the surface index's dotted leaders.

**Circles are reserved for points.** `border-radius: 50%` appears only on dots and
markers: the tag dot and the board's running dot (5px), the specimen marker on a
screenshot (19px), and its legend number (16px).

**A hollow dot means planned.** A planned provider or prototype wears a neutral tag
whose dot is a ring instead of a fill — the shape says "not yet" without a second
colour.

**Leader dots.** The surface index draws a dotted leader between a name and its mode
count with a flex-grown `::after` — a printed-index device, not a decorative divider.

## Components

Chrome is quiet at rest and states itself only on interaction. Every component is
built from the same materials: a tonal fill, one radius step, a sentence-case label,
and tabular figures.

### Buttons

- **Shape:** 5px radius, a transparent 1px edge, 36px high (`6px 16px`), inline-flex
  with an 8px gap for an optional 13px stroked SVG; 13.5px / 500.
- **Default:** `--button-bg` (the text colour at 8%) with `--text-0`. Never transparent:
  without an edge, a transparent button reads as text.
- **Primary:** an accent tint — `--accent-soft` fill, `--accent` text, an accent edge at
  45%. One per view. Never a solid, green or red fill: Gamma is a research tool, not
  an order ticket.
- **Hover / Focus:** hover draws the accent line on the edge (accent 35% into
  `--panel-strong`; 70% accent on the primary). Keyboard focus shows the 2px
  `--focus-ring`, offset 2px. Transitions are 120ms on `cubic-bezier(0.2, 0, 0, 1)`.
- **Compact:** inside a key card's action row, 28px high (`4px 8px`) at 12px.
- **Ghost:** `--tint` with `--text-1`, the accent line on hover — the repository link
  in the top bar (`.topnav a.ghost-cta`).

### Chips / Tags

- **Style:** the app's `.tag` — a pill 17px tall, `0 6px`, 11px / 600, sentence case, a
  5px dot before the text. One variable pair tones it: `--tg` colours the dot and the
  text, `--tg-fill` paints its soft fill over the sheet
  (`linear-gradient(var(--tg-fill), var(--tg-fill)), var(--panel-bg)`), so a toned tag
  keeps its contrast on the canvas, a sheet or a hovered row.
- **Tones:** `.badge-live` positive; `.badge-delayed`, `.badge-mock` (also worded
  `Sample`) warning; `.badge-accent` accent; `.badge-plan` neutral with a hollow dot;
  plain `.badge` neutral on the tint with `--text-1`. Inside the live board, `.badge.pos`
  and `.badge.warn` tone curve states.
- **State:** a tag is a statement about data, not a control. It has no hover. In a table
  cell it hangs from the top of the line box, so a row with a tag keeps the height of
  a row without one.

### Cards / Containers

- **Corner Style:** 6px.
- **Background:** `--panel-bg` on the canvas; inner blocks on `--tint`.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** none, at rest or on hover.
- **Internal Padding:** 24px on key cards and boundary columns, 16px on surface
  cells, `clamp(16px, 2.4vw, 32px)` on moments, with a 12px column gap between a key
  card's title row, prose, definition list, environment string, degradation note and
  bottom-anchored action row (`margin-top: auto`).

### Tables

Two table voices, both on the app's data-table pattern: a tinted header band without a
rule, sentence-case 11px / 500 column headers in `--text-2`, rows ruled with
`--divider`, no zebra, `--hover-bg` on row hover, cells 10px apart with the outer
columns 12px in from the sheet's edge. **Data tables** (`.data`) own their sheet,
which only scrolls: a 30px caption row as the sheet's title, 13.5px top-aligned cells
at 1.5 line-height, a bold first column in `--text-0`, and a 640px minimum width.
**Tape tables** (`.tape`) carry live values: right-aligned tabular figures except the
first column, `nowrap`, 30px rows, and a repriced cell that tints toward
`--flash-up` or `--flash-down` and fades over 800ms.

### Navigation

13.5px / 500 links in `--text-1`, `4px 12px`, 5px radius, on the canvas. Hover raises
the label to `--text-0` over `--hover-bg`. The current page shows the selection fill
(`--active-bg`) with `--text-0`. The GitHub link is a ghost button: the tint, `--text-1`,
and the accent line on hover. The brand is the
app's mark — an accent-tinted 22px tile with an accent edge and glyph — then "Gamma" at
15px / 600 and "Research Workspace" at 12px in `--text-1`. Below 860px the link strip
scrolls sideways with its scrollbar hidden, so every link stays reachable rather than
collapsing behind a menu.

### Code Blocks

A sheet whose head is a tinted band (32px, an 11px / 500 label naming the shell or
file, and a copy button). The copy button is a compact filled control: `--button-bg`,
`--text-1`, 22px, 5px radius, the accent line on hover; it reads "Copied" in
`--positive` for 1.6s, then reverts. The `pre` is JetBrains Mono 12px at 1.7
line-height in `--text-0` with a tab size of 2, marked by three syntax roles only:
comment (`--text-2`), value (`--accent-2`) and parameter (`--accent`). Inline `code`
is mono at 0.86em in `--text-0` on the tint.

### The Screenshot Plate

The site's signature component. A plate is a `figure` with three parts: a **shot bar**
(an 11px label naming the workspace and tab, with a `Mock` tag pushed right), the
**frame** holding the capture, and a **legend** row underneath. On the canvas the
plate is a sheet; inside a moment it shares the moment's sheet, so the bar and legend
align with the capture's edges.

Annotation is numbered, never floating. A `.mark-pt` — a 19px circle in the sheet
colour with a 1px accent edge and accent digits, ringed in the sheet colour — is
absolutely positioned by percentage over the point of interest and is
`pointer-events: none`. Its explanation lives as a numbered item in the legend below
the frame, its number on an accent-soft disc. **An annotation can therefore never cover
the thing it points at**, and the legend remains readable when the frame is scaled
down or panned.

### The Live Board

A running miniature of Gamma's own tape on its own sheet. A 32px title row carries the
green running dot, the board's name, and honest `Mock` / `Read-only` tags. Below it a
B′ segmented track (real `role="tablist"` buttons with arrow-key traversal) switches
between four boards: a tinted track, the selected segment on the sheet with a 1px
`--panel-border` outline at weight 600. The body is a 1.55fr / 1fr split: the tape on
the left, and on the right a provenance definition list — source, origin,
transformation, retrieval clock — above a tinted note explaining what is a Gamma
heuristic. Curve states and macro themes render as tags. One randomly chosen value
reprices every 1.5s with a directional flash; the clock restamps with it; the interval
is cleared while the tab is hidden and never starts under `prefers-reduced-motion`.

### The Time Rail

See Layout. Visually: a 92px column with a 1px `--panel-strong` baseline at its right
edge, a solid 1px accent sweep growing down that baseline as the session is read, and
11px / 500 tabular ticks in `--text-1` with an 8px leader. The tick nearest the reading
line turns accent at weight 600 and its leader grows to 12px in the accent.

### Steps

A two-column grid (34px / content) with a CSS counter rendering
`decimal-leading-zero` inside a 26px sheet-coloured block at 5px radius — the number is
a component, not a bullet.

### Disclosure (FAQ)

A sheet of native `details`/`summary` rows ruled with `--divider`. The summary is 600
at `clamp(0.95rem, 1.3vw, 1.06rem)`; hover paints `--hover-bg` across the row, and the
focus ring sits inside the sheet. The native marker is replaced by a 13px plus glyph
in `--text-2` that rotates 45° to an accent cross when open.

### Reveal & Motion

Motion tokens: 120ms for chrome state, 180ms for surface state, 620ms for the entry
pour, 800ms for a value flash, on `cubic-bezier(0.2, 0, 0, 1)` for state and
`cubic-bezier(0.16, 1, 0.3, 1)` for entry.

**The Visible-At-Rest Rule.** `.reveal` resolves to `opacity: 1`. The pour-in — a
620ms rise from 15px — is applied by adding a class on intersection, and only inside a
`prefers-reduced-motion: no-preference` block on a `.js` root. A failed observer, a
disabled script, or a reduced-motion preference costs the animation and never the
copy. Elements entering together are sorted by their top edge and staggered 55ms
apart via a `--d` custom property, so a group pours top-to-bottom rather than arriving
at once.

## Do's and Don'ts

### Do:

- **Do** copy colours from the app's `tokens.css` into the two token blocks in
  `site.css`, by role, for both themes. This site has no marketing-only colour, and
  adding one would break the claim that the screenshots and the page are the same world.
- **Do** check every change in the light and the dark theme, and keep text at 4.5:1
  (3:1 at 24px, or 18.66px bold) over its rendered background in both.
- **Do** put evidence on a sheet (`--panel-bg`, 6px, no edge) and inner blocks on the
  tint; separate related sheets with 8px seams.
- **Do** write labels in sentence case at 11px / 500 in `--text-2`, with no
  letter-spacing, and let the copy carry its own capitals.
- **Do** set every number in Instrument Sans with tabular figures, and keep JetBrains
  Mono for code by adding a code element to the mono selector list.
- **Do** fill every action: `--button-bg` for ordinary buttons, `--tint` for a ghost,
  the accent tint for the one primary action.
- **Do** write auto-placed grid tracks as `minmax(min(Npx, 100%), 1fr)`.
- **Do** give wide content its own scroll container, and label it when the gesture is
  not obvious (the screenshot frame's "Drag to pan" below 760px).
- **Do** tag every synthetic value `Mock` (or `Sample`) and every planned provider with
  the hollow-dot tag, on this site as in the app.
- **Do** annotate a screenshot with a numbered `.mark-pt` plus a legend row, and keep
  the marker `pointer-events: none`.
- **Do** keep `.reveal`'s resting state visible and animate only on entry.

### Don't:

- **Don't** draw a border around a sheet, card, block, field, tag or button; the tonal
  step is the edge. Lines are for row rules, the selected segment, hover, focus and
  the primary action's edge.
- **Don't** put a shadow, glow or blur on anything but a floating overlay.
- **Don't** add texture to the canvas — no grid, no grain, no ruled ground.
- **Don't** use a radius off the scale (5px controls, 6px sheets and blocks, 12px
  overlays, pills for tags only), or a circle for anything that is not a dot or a
  numbered marker.
- **Don't** colour chrome. A heading, a nav item at rest, a sheet or a body paragraph
  is neutral; hue belongs to values, states and the one primary action.
- **Don't** fill a button with a solid accent, green or red.
- **Don't** uppercase or track a label, or write copy in capitals; upper case is for
  content that is itself a code.
- **Don't** set chrome, labels or figures in a monospace, or set figures in
  proportional digits.
- **Don't** put `--text-2` on the light canvas; it is tuned for the sheet and the tint.
- **Don't** add `overflow-x: hidden` anywhere. If something overflows, either fix the
  track minimum or give it a scroll container.
- **Don't** float a callout over a screenshot. The marker points; the legend explains.
- **Don't** let the time rail track the whole document or appear below 1180px — it
  belongs to the session section and needs its own 92px column.
- **Don't** hide content behind a scroll-triggered animation. If the observer never
  fires, the page must still read completely.
- **Don't** show a number on this site that a real Gamma surface could not produce,
  and never show one without its provenance or its `Mock` tag.
