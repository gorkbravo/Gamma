# Gamma — Frontend Design Principles

> **Canonical frontend doctrine.** Read this before designing, implementing, or reviewing Gamma UI. It defines the outcomes the interface must preserve. `frontend/src/lib/theme/tokens.css` is the numeric source of truth for implemented tokens, `frontend/src/lib/theme/primitives.css` implements the shared component contracts, and nearby production components are the source of truth for established behavior.

Gamma is a professional, read-only market research environment. It should feel like a research instrument: dense enough for comparison, quiet enough for sustained attention, and precise enough that the user can trust what changed, where it came from, and what to do next.

The visual lineage is the scientific instrument and the well-set statistical table: calm tonal surfaces, figures that line up in their columns, and controls that stay out of the way until they are needed. Gamma is not a terminal imitation, a generic SaaS dashboard, or a data-visualization showcase. Its identity comes from one plane of tonal sheets, restrained chrome, one interface typeface with tabular figures, and data that carries most of the visual energy, in a light and a dark theme.

## 1. How To Use This Guide

When sources disagree, use this order:

1. **Product boundary:** `roadmap.md` defines what Gamma is allowed to become. Gamma supports research, analysis, comparison, and hypothesis formation—not execution.
2. **Design principles:** this document defines the frontend experience and durable visual rules.
3. **Tokens:** `frontend/src/lib/theme/tokens.css` owns current reusable values for both themes. This document names tokens, not values; do not copy a value from here into CSS when a token exists.
4. **Shared primitives:** `frontend/src/lib/theme/primitives.css` implements the §8 contracts (panel, panel title, view header, mode bar, KPI blocks, data table, tag, button, form control, inline stat). Opt into a primitive before writing a scoped copy; a view that genuinely differs overrides one declaration in its own scoped block.
5. **Pattern implementations:** use the mature surface closest to the task. Do not treat one tab as a universal template.
6. **Local composition:** a view may solve its own information problem as long as it preserves the product boundary and system rules above.

If a component needs a value the token system does not express, first try the nearest existing step. Add a token only when the value represents a reusable role, not a one-off preference. Update this guide when a durable principle changes; update `tokens.css` when an implemented value changes.

Two tests keep the tokens honest: `frontend/src/lib/theme/contrast.test.ts` checks WCAG AA for both theme blocks, and `frontend/src/lib/theme/raw-colors.test.ts` fails on raw colour literals in `.svelte` files and `primitives.css` outside its exception list. `frontend/e2e/visual.spec.ts` keeps pixel baselines of fixture-driven harness pages in both themes, so a token or primitive change that moves them fails until the baselines are regenerated on purpose. `docs/visual_refresh_plan.md` records the decisions behind the current look, the kept exceptions and their reasons.

Sections 1–13 explain the reasoning. **Section 14 (Common Mistakes) is the fast check to run after every edit**, and Section 15 is the one-screen summary.

### Reference Surfaces

| Need | Best current reference |
|---|---|
| Cross-domain context, mode switching, comparison density | Macro / Cross-Asset |
| Deep entity work and editable local scenarios | Fundamentals |
| Provider warnings, curves, fundamentals, and handoffs | Commodities |
| Compact quantitative diagnostics | Risk |
| Global chrome, navigation, search, drawers | Shell and shared navigation components |

Copy a reference's reasoning, not its markup. A new workflow should inherit Gamma's grammar without becoming a visual clone of an unrelated tab.

## 2. The Design Thesis: The Research Instrument

Gamma operates in **Operate** mode: the user is here to inspect, compare, filter, test, and decide what deserves deeper research. Expression serves operation.

**The Data-First Rule.** The research object, its state, and its most useful comparison appear before explanation, provenance internals, or decorative chrome.

**The One-Plane Rule.** The workspace reads as one plane of tonal sheets separated by consistent seams; regions never float. Only transient overlays leave the plane.

**The Earned-Density Rule.** Density means more useful relationships per viewport, not smaller text or indiscriminate compression. Remove repetition before reducing legibility.

**The Quiet-Chrome Rule.** Controls become visually prominent only when they are active, focused, dangerous, or carrying time-sensitive state. Data supplies the color and contrast at rest.

### What Good Feels Like

- The primary research question is obvious within a few seconds.
- Related values can be compared without excessive scrolling or pointer travel.
- Visual hierarchy remains clear even when color is removed, and in either theme.
- Loading, empty, stale, partial, and error states preserve the final layout's geometry.
- Provenance is easy to reach but does not turn the main surface into a schema browser.
- Each tab has a distinct research purpose while still reading as Gamma.

## 3. Foundations And Tokens

All reusable styling uses tokens from `frontend/src/lib/theme/tokens.css`. Raw CSS values are acceptable only when no semantic token exists and the value is genuinely local, such as a chart-library integration detail. Do not create local color palettes or type scales. A translucent version of a token is `color-mix(in srgb, var(--token) N%, transparent)`; a colour built in script goes through `mixToken()` or `resolveChartColor()` in `frontend/src/lib/chart-colors.ts`.

### Color Roles

| Role | Tokens | Intent |
|---|---|---|
| Canvas | `--canvas` | The page behind the sheets; it shows only in seams and unused space |
| Sheet | `--panel-bg` (`--bg-0`) | The solid surface every panel paints on the canvas, one tonal step above it |
| Tint | `--tint` (`--bg-1`) | The quiet fill inside a sheet: fields, the table header band, KPI blocks, cards, ghost buttons, the mode-bar track |
| Button fill | `--button-bg` | One tonal step above the tint, so a button reads as a button without an edge |
| Further steps | `--bg-2`, `--bg-3`, `--surface-0`, `--surface-1`, `--surface-2`, `--surface-soft` | Rule and line steps, overlay and inset fills; used sparingly, never as generic card fill |
| Lines | `--panel-border`, `--panel-strong`, `--divider` | Overlay and control edges; the strong line (hover edges, the chart baseline); the rule between rows and inner sections |
| Text | `--text-0`, `--text-1`, `--text-2`, `--heat-text` | Primary, supporting, and metadata hierarchy; neutral text on a heat-map fill |
| Interaction | `--accent`, `--accent-soft`, `--hover-bg`, `--active-bg`, `--focus-ring` | Focus, selection, active navigation, the one primary action, and the primary chart series |
| Data semantics | `--positive`, `--negative`, `--warning`, `--negative-muted`, `--data-*`, `--cat-*` | Direction, status, intensity, and categorical identity in analytical content |
| Soft fills | `--accent-soft`, `--positive-soft`, `--negative-soft`, `--warning-soft` | Tag and chip fills, stale and conflict cells; a heat map that encodes magnitude mixes the base token at graded strengths |
| Charts | `--chart-primary`, `--chart-secondary`, `--chart-negative` | The primary series, the comparison series, a falling series |
| Overlay | `--scrim`, `--overlay-shadow` | Dims the workspace behind a modal overlay; the only shadow in the interface |

`--accent-2` is the context gold and equals `--warning`. It marks context tags that say where a reading sits (`.tag.is-tinted.context`). It is not a second chrome accent and not a series colour; comparison series use `--chart-secondary`.

**Themes.** Gamma has a light and a dark theme from one set of token names. Settings offers System (the default), Light, and Dark; `frontend/src/lib/stores/appearance.ts` writes the resolved theme to `data-theme` on `<html>`, and the `:root[data-theme="light"]` block in `tokens.css` restates the bases while derived tokens follow them. Every token pair must pass `contrast.test.ts` in both blocks (4.5:1 for text, 3:1 for graphics and focus), and anything drawn on canvas re-reads its tokens when `resolvedTheme` changes. A surface is not done until it has been seen in both themes.

### Typography Roles

Gamma uses one family, Instrument Sans (self-hosted under `frontend/public/fonts/`, declared in `frontend/src/lib/theme/fonts.css`), for the interface and the data, and a monospace for code. Every `font-family` names one of four roles:

- `--font-ui`: navigation, buttons, headings, panel titles, and prose; the document default.
- `--font-label`: the small labels above data: eyebrows, column headers, stat, KPI, and field labels.
- `--font-num`: data figures that must align: table cells, stat and KPI values, `.num`, and figures in cards and charts. Identifiers (tickers, contract codes, option symbols) and ISO dates use it too; there is no separate identifier role.
- `--font-code`: code, raw JSON, model output, and the Script editor; the only monospace.

The body turns on tabular figures (`tabular-nums` and `"tnum" 1`) for the whole document, so a figure holds its width as it ticks, in a table or in chrome. The Settings "Data figures" choice overrides `--font-num` only, which is why data surfaces name `--font-num` explicitly: with a monospace chosen, every figure turns monospace while labels, titles, and prose stay in the interface font. `--app-font` and `--display-font` are aliases kept for old rules; new code names the roles.

**The Two-Type Rule.** Sans explains the instrument; tabular figures carry the research; mono is for code. The two types are proportional interface text and tabular data figures, both Instrument Sans. Do not set data in proportional figures, and do not set chrome or data in a monospace merely because the application handles numbers.

**Labels.** Labels are sentence case, `--text-xs`, weight 500, no letter-spacing, in `--text-2`. `--label-case` is `none`, so the copy carries its own capitals. Panel titles are `--text-title` at weight 600 and view titles `--text-md` at weight 600. Upper case is reserved for content that is itself a code (§11).

Every font size resolves to the type scale:

| Token | Size | Typical role |
|---|---:|---|
| `--text-2xs` | 10px | Second lines under an identifier (`.meta`), small notes, compact marks |
| `--text-xs` | 11px | Labels, column headers, tags, metadata, timestamps |
| `--text-sm` | 12px | Table cells, compact controls, and dense supporting data |
| `--text-title` | 12.5px | Panel titles |
| `--text-base` | 13.5px | Body text and reading-table cells |
| `--text-kpi` | 14px | KPI and inline stat values |
| `--text-md` | 15px | View titles and section headings |
| `--text-lg` | 16px | Headline figures (`.stat.is-large`) and dialog headings |
| `--text-xl` | 18px | Hero identifiers inside research tabs |

Use `--leading-tight` for single-line labels and values, `--leading-snug` for dense lists, and `--leading-normal` for prose. Build hierarchy with placement, weight, and contrast before increasing size. Research-tab text normally does not exceed `--text-xl`; the welcome surface is the intentional exception.

### Space, Shape, And Motion

| Scale | Values | Contract |
|---|---|---|
| Space | `--space-1` through `--space-7` (2, 4, 6, 8, 12, 16, 24px) | Snap gaps, padding, and margins to the ramp whenever possible |
| Radius | `--radius-control` (5px), `--panel-radius` (6px), `--overlay-radius` (12px), `--radius-pill` | Controls and mode segments; sheets, KPI blocks, cards, and the mode-bar track; floating overlays; tags, chips, and the provenance pill only. Nested geometry is square. `--radius-sm` and `--radius-md` remain for small inner marks such as bar ends, swatches, and heat cells |
| Motion | `--motion-fast` (120ms), `--motion-base` (180ms), `--ease` | Functional state change, never spectacle |

The default seam is `--space-4` (8px). Panel padding is usually `--space-5` or `--space-6`. `--space-7` is a real group break, not the default rhythm.

## 4. Color, Texture, And Emphasis

**The Color-Has-A-Job Rule.** Blue communicates interaction or the primary analytical series. Green, red, and amber communicate data meaning. Neutral values carry structure, including the grey comparison series. Color never exists only to give a tab personality.

- Use `--accent` for active navigation, focus, selection, interactive emphasis, and the primary chart series.
- Use semantic colors for directional or categorical data only. Pair color with a sign, label, icon, position, or pattern so meaning survives color-vision differences.
- Use chart colors in a clear order; do not give every series equal saturation.
- Keep structural surfaces in the same neutral-cool temperature in both themes: cool greys and white in light, blue-greys in dark.
- Never use warm darks, cream or beige lights, arbitrary tab palettes, glow text, or gradient text.

### Gradients And Texture

Structural panels, cards, tables, navigation surfaces, and the canvas are flat. Gamma has no ambient texture: do not add a dot grid, noise, or pattern anywhere. Gradients are allowed only when they encode data (a heat-map ramp, a colormap legend, a distribution) or express progress or loading.

Fills that encode data are allowed and flat. A chart's area fill is one flat strength of its series colour, and the band between two series is filled only when it encodes a difference: a curve against last week, a book against its benchmark, a distribution's range. A band for atmosphere is decoration.

A one-colour `linear-gradient(var(--positive-soft), var(--positive-soft))` layered over `var(--panel-bg)` is a flat fill, not a gradient: it paints a soft fill over the sheet so the text on it keeps its contrast inside a selected row (`.tag` does this). Gradient stops and animated colours keep literal values (`--flash-*`) or `rgba(var(--accent-rgb), α)`, because a `color-mix()` colour interpolates one level off.

## 5. Elevation And The Plane Model

Gamma uses a plane model, not an object model. Most SaaS dashboards create hierarchy with outlined cards, large gutters, radius, and shadow. Gamma creates hierarchy with reading order, alignment, shared baselines, and a few controlled tonal steps: canvas, sheet, tint, button fill. A sheet's edge is its change of tone, not a line.

### Surface Contracts

| Surface | Background | Boundary | Shape |
|---|---|---|---|
| Panel (sheet) / self-contained card on the canvas | `var(--panel-bg)` | None: `--panel-border-width` is 0 and the tonal step is the edge | `var(--panel-radius)` |
| Block inside a sheet: KPI block, card, message, focus card | `var(--tint)` | None | `var(--panel-radius)` |
| Chart shell nested in a panel | Transparent: the sheet shows through | None; the time axis is the baseline | Square |
| Table that owns a panel | The sheet, with a `var(--tint)` header band | None: the sheet's edge contains the table; rows are ruled with `--divider` | Square internally |
| Input / select | `var(--tint)` | Transparent edge; a `--panel-strong` line on hover; the focus ring | `var(--radius-control)` |
| Button | `var(--button-bg)`; ghost `var(--tint)`; primary `var(--accent-soft)` | Transparent edge with an accent line on hover; primary keeps an accent edge | `var(--radius-control)` |
| Mode bar / segmented control | Track `var(--tint)`; selected segment `var(--panel-bg)` | A 1px `--panel-border` outline on the selected segment only | Track `var(--panel-radius)`, segments `var(--radius-control)` |
| Local inset / callout | `var(--tint)` or `var(--surface-soft)` when distinction is meaningful | None, or a rule | Square when nested |
| Floating overlay: drawer, dialog, menu, tooltip, popover, Copilot shelf | Solid or near-solid (`--surface-0`, `--popover-bg`) | A 1px `--panel-border` line and `--overlay-shadow`; modal overlays dim the workspace with `--scrim` | `var(--overlay-radius)` |

- Do not put `box-shadow` on panels, cards, tables, or chart shells. Floating overlays are the only shadowed surfaces, and they use `--overlay-shadow`.
- Do not draw a border around a sheet, card, KPI block, field, or button; the tonal step carries the boundary. Lines remain for row rules, overlay edges, the selected segment, hover, focus, and boxes that encode data (a band's range).
- Do not nest a tinted block inside a tinted block when a rule, row, or shared grid can express the relationship.
- Do not use opacity-layered panel fills to simulate glass.
- Never leave an action button transparent: without an edge, a transparent button reads as plain text. Navigation rows, menu items, list rows, and inline text links are not action buttons; they sit on their surface and show `--hover-bg` or `--active-bg`.
- Keep adjacent surface gaps at `--space-4` unless a real hierarchy break warrants more.
- Pills are reserved for compact, non-container tags, status chips, and the provenance pill. Controls, mode segments, panels, and data containers use the radius scale.

**Audit test:** blur your eyes. The screen should read as one plane of tonal sheets, not a collection of floating tiles; only overlays float.

## 6. Information Architecture And Layout

Start composition with the research question, not a card inventory.

1. Identify the primary object or comparison.
2. Put the most decision-relevant evidence in the first reading path.
3. Group supporting context by relationship, not by visual symmetry.
4. Keep controls close to the data they affect.
5. Move provenance detail, diagnostics, notes, and secondary rankings into support regions or progressive disclosure.

### Workspace Grammar

```text
Tab
  shared context / title / key metrics
  mode bar (when the domain has multiple research tasks)
  compact lens or filter controls
  workspace grid
    primary path
    support path
```

The familiar `primary-column + support-column` layout (`.workspace-grid` in `primitives.css`) is a useful default, not a mandatory template. A wide table, curve explorer, matrix, or comparison canvas may legitimately own the full width.

**The Primary-Path Rule.** At every supported width, the main analysis appears before support content in visual and DOM order.

### Density

- Prefer columns, aligned rows, shared axes, and rules over independent cards.
- Remove repeated headings, helper prose, redundant units, and decorative whitespace before shrinking controls or type.
- Let charts use their allocation; avoid padded chart islands.
- Use local section scrolling when it preserves context better than an extremely long page.
- Keep a stable alignment system. Numeric columns are right-aligned or decimal-aligned; labels are left-aligned; units and precision remain consistent within a comparison.

### Responsive Behavior

Responsive design is prioritization, not uniform shrinking.

- Use intrinsic layouts (`minmax()`, flexible tracks, content-aware wrapping) before breakpoint-specific patchwork.
- Collapse support content below the primary path when two columns no longer preserve legibility.
- Keep mode switching, the active context, and primary actions visible. A mode bar that no longer fits scrolls sideways within its width rather than widening the page or clipping its last modes.
- Allow deliberate horizontal scrolling for genuinely wide tables; preserve the row label and make overflow discoverable.
- Do not hide evidence merely to make a narrow screenshot look tidy. Summarize or progressively disclose support material instead.
- Test desktop and narrow widths plus a stressful intermediate width where labels and controls begin to wrap.

## 7. Tabs, Modes, Lenses, And Modules

Each top-level tab is a durable research domain.

- **Tab:** a research domain.
- **Mode:** a distinct task within that domain.
- **Lens:** shared state such as region, asset, venue, timeframe, benchmark, or comparison target.
- **Module:** a chart, table, KPI strip, ranking, or detail surface inside a mode.

Prefer a mode or lens over a new top-level tab when the work shares a domain and context. Mode labels answer “what kind of research am I doing?” Lens controls answer “which slice am I studying?”

Mode bars are visible, compact segmented controls—a tinted track with the selected segment on the sheet—not hidden navigation or pill groups. Role toggles outside a mode bar use the same track (`.segmented`). Preserve relevant lens state across modes, deep links, keyboard navigation, and overview-to-detail handoffs. A new analytical state should also update Copilot grounding where useful.

## 8. Component Contracts

### Panels And Section Headers

Use panels for distinct analytical regions, not every conceptual group. A panel (`.panel`) is a borderless sheet: `var(--panel-bg)`, `--panel-radius`, `--space-5` padding, and a `--space-4` internal gap. `.panel.is-flush` gives a table, map, or chart canvas the whole box.

Use a compact panel title or category label when it improves navigation. `.panel-title` is one 30px row: the title in `--text-title` at weight 600, sentence case, with counts or units opposite in `.header-meta` and no rule beneath; the table's header band or the chart starts the body. Do not stack an eyebrow, title, subtitle, and helper sentence by habit. If the surrounding mode and table headers already identify a region, omit the panel header.

A research tab opens with `.header-panel`: the view title and its current subject, then the mode bar with the tab's headline numbers opposite it.

### KPI Strips

- Headline numbers are tinted blocks on one row and one baseline (`.header-kpi`, `.kpi-block`): `var(--tint)`, `--panel-radius`, a `--space-3` gap, never bordered or shadowed. Values are `--text-kpi` at weight 600 in `--font-num`; labels follow the label rule.
- Inline stats in a row (`.stat`) are spaced without rules or fills, and the first sits flush.
- Keep labels muted and values visually strong.
- Use signal color only when the metric has directional or status meaning.
- Where the view's payload already carries a metric's history, add compact trend context: a sparkline and the week-over-week change (`Sparkline.svelte`, `weekOverWeekChange()`). Do not fetch history only to draw it, and show the number when there are too few points to be honest.
- Never turn each KPI into its own floating or outlined card.

### Tables

Tables are the default for structured, multi-column comparison. Opt in with `.data-table` and the modifiers for the families that genuinely differ (sticky, relaxed, compact, grid, figures, key/value).

- Column headers are labels: `--font-label`, `--text-xs` at weight 500, sentence case, `--text-2`, on a tinted header band without a rule. A sticky header keeps the band.
- Cells are data: `--font-num` with tabular figures at `--text-sm`; tables a view reads as its main surface use `--text-base` (`.is-body-text`).
- Rows are 28px in dense contexts: cells 10px apart, the outer columns 12px in from the sheet's edge, in line with the panel title.
- Rows are ruled with `--divider`; there is no zebra striping. Row hover is `--hover-bg` and the selected row `--active-bg`.
- Align quantities consistently (`.num` right-aligns) and make units/precision explicit.
- Keep selection, sort, stale, missing, and exceptional states legible without relying on color alone.

**The Table-Owns-The-Panel Rule.** When a table is a panel's primary content, the panel is flush (zero padding) and the sheet's edge contains the table. Do not add a bordered or tinted `.table-wrap` inside it; a wrapper may only scroll.

### Charts

- Prefer shared chart components such as `TimeSeriesChart` and `Sparkline` when the contract fits.
- The chart sits on the sheet: a transparent ground, no grid lines, and only the baseline (the time-axis edge in `--panel-strong`); axis labels in `--text-2` and `--font-num`.
- The primary series is a 2px line in `--chart-primary` with a flat area fill at 9% of its colour, never a fading gradient.
- A comparison series (a previous curve, a benchmark) is a solid line in `--chart-secondary`, a grey at 3:1 on the sheet. That grey is reserved for comparison: a lone series uses `--chart-primary` and categorical series use `--cat-*` (the first category may stay `--chart-primary`). Dashes are kept only for Macro's comparison region, which pairs each comparison with its primary by colour, for derived overlays such as moving averages, and for reference marks that are not series (§11).
- Fill the band between two series only when it encodes a difference (§4).
- Canvas charts cannot turn on tabular figures, so their axis labels use `--font-num` with proportional digits; that is acceptable while the crosshair label does not jitter.
- Titles, legends, units, time ranges, and tooltip precision should make the comparison interpretable without nearby prose.
- Use gradients only when they encode scale or uncertainty.
- Do not imply continuity, precision, or freshness the source data does not support.
- Keep loading, unavailable, empty, and error messages inside the final chart geometry.
- A chart drawn on canvas re-reads its colours when the theme changes.

### Controls

- Chrome buttons are usually about 25px high; data-context inputs and buttons are 28px (`.btn`, `.form-control`), with 24px (`.is-small`) for dense rows and 32px (`.is-large`) for form panels.
- Edgeless action controls are never transparent. A button (`.btn`) fills with `--button-bg`, one tonal step above the tint; a ghost button (`.btn.is-ghost`) for a secondary action fills with the tint and quieter text; a field (`.form-control`) takes the tint. Hover shows an accent line, keyboard focus the ring.
- Use compact text or icon buttons. Give icon-only controls an accessible name and, when the meaning is not obvious, a tooltip.
- Primary emphasis is relative: one action may be accent-tinted (`.btn.is-primary`: `--accent-soft` fill, accent text and edge), while peers remain quiet. Never a solid, green, or red fill: Gamma is a research tool, not an order ticket.
- Destructive actions use `.btn.is-danger` (red text and edge on the ordinary button fill) and explicit copy; Gamma's research flows should rarely need them.
- Disabled controls explain why when the reason is not obvious from the current state.

### Tags, Badges, And Status

Use a tag (`.tag`) when compact grouping or status meaning is useful. A tag is a pill with a small dot, `--text-xs` at weight 600 in sentence case, toned by one variable: `--tg` (neutral, positive, negative, warning, accent) colours the dot and text, and `--tg-fill` paints its soft fill over the sheet. A neutral tag fills from the tint. Tags may use the pill silhouette because they are inline annotations, not structural containers. Use semantic color only when the badge carries corresponding data meaning. Avoid badge clouds and never turn every metadata value into a chip.

Provenance appears through the shared `ProvenanceBadge`: a soft pill such as `● Sample · mock · 22:58 · 2 warnings`, with the full detail in its tooltip and a compact dot variant where space is tight. Extend it; do not build a per-view provenance chip.

### Cards

Cards are appropriate for genuinely self-contained repeated objects such as saved research items, watchlist entries, or generated research artifacts. They still follow the plane model: a tinted block on the sheet (or a sheet on the canvas), no border, no shadow, `--panel-radius`, and no card inside a card.

## 9. Data Presentation And Research Integrity

Visual polish must not imply certainty the data does not have.

### Numbers

- Use tabular figures and stable alignment.
- Keep precision intentional and consistent within a comparison.
- Show units at the column, axis, group, or value level—wherever ambiguity is lowest without repetition.
- Distinguish zero, missing, not applicable, stale, and unavailable. Do not collapse them all into `—` without context.
- Pair directional color with a sign, arrow, label, or position.

### Provenance

Preserve provenance aggressively in models and surface it selectively in UI.

**The Provenance-On-Demand Rule.** Show source, timestamp, methodology, and caveats where they materially affect trust or interpretation. Keep adapter names, concept IDs, transformation labels, and other developer-facing details in tooltips, drilldowns, provenance panels, or diagnostics unless the user is explicitly inspecting them.

### Writing

Interface copy is compact, factual, and operational.

- Prefer specific labels and verbs over explanatory paragraphs.
- Write labels, states, and messages in sentence case; the copy carries its own capitals. Tab names are title case because they are names. Status codes stay codes in logic and are formatted where shown.
- Remove text that merely restates a heading, chart, or visible control.
- Keep caveats, units, freshness, and interpretation boundaries that the data cannot communicate alone.
- Put open-ended interpretation in Copilot or a dedicated research note, not as unqualified static copy beside a live metric.
- Empty and error states say what happened and the next useful action when one exists.

## 10. Interaction, State, And Accessibility

**The Stable-Geometry Rule.** Loading, empty, stale, partial, error, hover, selected, and focused states occupy the same layout contract as loaded content. State changes should not cause avoidable jumps.

- Use stable sentence-case text such as `Loading…`, `N/A`, `No data`, or `Chart unavailable` in the final content position. Avoid shimmer and spinner overlays on analytical surfaces.
- Data appears without decorative entrance animation. Value flashes may briefly show update direction using `--flash-duration`.
- Use `--motion-fast` and `--motion-base` for state, drawer, collapse, and focus transitions. Respect `prefers-reduced-motion` for nonessential motion.
- Every action is keyboard reachable and has a visible `:focus-visible` state, drawn with `--focus-ring`.
- Prefer native elements and semantics; add ARIA only when native HTML cannot express the interaction.
- Maintain a logical focus order after mode changes, drawer operations, and conditional rendering.
- Do not use hover as the only way to reveal critical content or actions.
- Touch targets may be larger than their visible compact control through padding or hit-area techniques, especially at narrow widths.

Copilot is a transient research layer, not a competing dashboard. Its shelf is a floating overlay (§11). Generated research artifacts should inherit the density and component grammar of their owning tab.

## 11. Intentional Exceptions

- **Welcome / connection surface:** may use a centered gateway card and larger type because it is a doorway, not a research workspace.
- **Drawers, dialogs, tooltips, and menus:** floating overlays are the elevation exception. They take `--overlay-radius` corners, `--overlay-shadow`, and a 1px `--panel-border` line; modal ones (the navigation drawer, the Copilot shelf, the Setup dialog) dim the workspace with `--scrim`. The navigation drawer and the Copilot shelf float 8px in from the window edges; the drawer keeps its 248px width, pinning, and drag reordering. A near-solid fill (`--popover-bg`) is functional; glass is not.
- **Data visualization:** may use gradients, broader color ramps, or denser labels when they encode analytical meaning and remain accessible.
- **Status tags and the provenance pill:** may use pill geometry because their shape communicates a bounded inline annotation.
- **Identifier codes:** upper case only where the content is itself a code: token tickers on the Crypto treemap, the price and tenor headers of the Options payoff grid, tickers on the Risk correlation heat map, the Portfolio benchmark ticker field, and the Prediction Markets venue codes. Those rules set `uppercase`, and the slight tracking capitals need, themselves; every other label follows `--label-case` with no letter-spacing.
- **Dashed series:** Macro's comparison region and derived overlays such as moving averages (§8 Charts). Reference marks are not series and may be dashed: distribution markers, a start-value or zero line, the capital market line, at-the-money and guide lines, the hover line.
- **Lines that stay:** the accent edge of primary buttons (and of the top bar's Copilot trigger, a primary-style chrome action), the 1px line of floating overlays, boxes and marks that encode data (the Commodities band boxes and markers, colour-scale tracks, legend swatches, the Sealanes chokepoint ring), the full cell grid of Copilot rich tables (`.data-table.is-grid`), structural table rules (the Options chain's strike column, the Commodities sector column), the top bar's zone separator, checkbox edges, and the landing card's readout grid.
- **Map:** the Sealanes base map shows none of CARTO's own colours: it is recoloured from the `--map-*` tokens, which turn its roles over in the light theme (land the sheet, water a grey step, quiet borders) as a printed chart does. Map chrome that stays on the map (HUD, legend, controls) is tinted and edgeless; the shelf, detail drawer, replay panel, notices, and popups float as overlays. The lane legend keeps the glow the lanes are drawn with.
- **3D surface:** `Surface3D` keeps its reference planes, because they carry the depth cue a flat chart gets from its baseline.
- **Transparent controls that are not action buttons:** menu items, list and navigation rows, text links, the tooltip trigger, segments inside a tinted track, an icon inside a chip, the Commodities market cards, and dense per-row icon toggles such as the Sitrep follow-up pins. Every action button is filled (§8 Controls).
- **Full-width analytical tools:** may depart from the two-column workspace when the research object needs width.

An exception must have a functional reason. “It looks more modern” is not one.

## 12. Review Tests

Use these tests before handoff. They are outcome checks, not a substitute for visual inspection.

### Research Test

- What question does this surface answer?
- Is the main evidence in the first reading path?
- Can the user compare the important values without unnecessary scrolling or context switching?

### Plane Test

- Do panels merge into one plane of tonal sheets?
- Are shadows, borders, large gutters, or radius making analytical regions look like floating cards?
- Is a nested tint or an edge doing work a rule or alignment could do more quietly?

### Hierarchy Test

- Does the screen still make sense in grayscale, and in both themes?
- Are data figures tabular (`--font-num`), chrome in the interface font, and mono kept for code?
- Are the loudest elements the most important, current, or actionable ones?

### State Test

- Are loading, empty, error, stale, and partial data states covered?
- Does state change preserve geometry and focus?
- Is missing data distinguishable from zero and not applicable?

### Access Test

- Can the workflow be completed with a keyboard?
- Are focus, selection, and data semantics expressed without color alone?
- Do icon-only actions have accessible names?
- Does every text reach 4.5:1 (3:1 when large) over its rendered background, in both themes?
- Does the primary path survive narrow widths and text wrapping?

### Drift Scan

Look for:

- raw colors or off-scale type, spacing, or radius where a token exists (`raw-colors.test.ts` catches colour literals in `.svelte` files and `primitives.css`),
- a border around a sheet, card, KPI block, field, or button, or a tinted block nested in a tinted block,
- shadows, blur, or glass outside floating overlays, and overlays that skip `--overlay-radius`, `--overlay-shadow`, or the scrim,
- radius off the scale: anything but `--radius-control`, `--panel-radius`, `--overlay-radius`, a pill on a tag or chip, or square nested geometry,
- uppercase or letter-spaced labels outside the identifier exceptions, and copy written in capitals (`LOADING…`, `CHART UNAVAILABLE`),
- a monospace outside code, data figures that skip `--font-num`, or new rules on the `--app-font`/`--display-font` aliases,
- transparent action buttons, and solid, green, or red button fills,
- zebra striping, chart grid lines, fading area gradients, dashed comparison series beyond the two exceptions, `--chart-secondary` on anything but a comparison series, and bands that encode no difference,
- signal colors used as decorative chrome,
- duplicated headings, helper prose, or provenance internals in the primary path,
- card layouts for data that should be a table or shared grid,
- oversized controls, unstable loading states, or hidden keyboard focus,
- a surface checked in one theme only, or a canvas that keeps its colours after a theme switch.

## 13. New Surface Checklist

Before shipping a new tab, mode, or major module:

1. Name the research question and the primary evidence.
2. Confirm the scope fits `roadmap.md` and the read-only product boundary.
3. Choose the closest mature reference surface.
4. Define tab, mode, lens, and module responsibilities before composing panels.
5. Use existing tokens, the `primitives.css` primitives, and shared components; add reusable primitives only when the role recurs.
6. Place filters and actions near the data they affect.
7. Define loading, empty, stale, partial, error, selected, and focused states.
8. Preserve provenance in the model and choose its appropriate disclosure level.
9. Register navigation, keyboard actions, persistence/deep-link state, and Copilot context where relevant.
10. Validate desktop, intermediate, and narrow layouts in the light and the dark theme; inspect the result, not only the CSS.

---

## 14. Common Mistakes

The fast check after every edit. Left column is what shows up in review; right column is the correction.

### Surface And Depth

| Mistake | Why it is wrong | Correction |
|---|---|---|
| A hand-picked panel background such as a hex value or `transparent` | Breaks the plane. `--panel-bg` is the solid sheet, one tonal step above `--canvas` in both themes | `background: var(--panel-bg)` |
| `box-shadow` on a panel, card, table, or chart shell | Implies a floating object in a plane-model interface; only overlays float | Remove it; the tonal step carries the boundary |
| A border around a sheet, card, KPI block, field, or button | A second boundary on top of the tonal one; the plane turns back into outlined boxes | Remove it; lines are for row rules, overlays, hover, and focus |
| `linear-gradient` on a structural surface | Implies lighting and elevation | Flat token fill |
| Opacity-layered panel fills to fake glass | Ambiguous depth, unreadable stacking | Solid token, or `--tint` / `--surface-soft` when an inset is genuinely meaningful |
| A tinted block nested inside a tinted block | Two fills where a rule would do the same work more quietly | Rule, shared grid, or row |
| `.table-wrap` with its own border or fill inside a sheet | Defeats the edge-to-edge table contract | Remove it; the sheet's edge contains the table |
| Warm-tinted darks, or cream and beige lights | Temperature mismatch with the cool neutral system in either theme | The theme's `--canvas`, `--bg-*`, and `--surface-*` tokens |
| Radius off the scale (`8px`, `--radius-md` on a panel), or radius on a nested container | Breaks the shape system; nested geometry is square by contract | `--radius-control` controls, `--panel-radius` sheets and blocks, `--overlay-radius` overlays, `0` nested |
| Pill geometry on a button, mode control, or data container | Pills are reserved for inline tags, status chips, and the provenance pill | Radius scale |
| A transparent ghost button | With no edge and no fill it reads as plain text | `.btn.is-ghost` on `--tint`; other buttons on `--button-bg` |

### Density And Layout

| Mistake | Why it is wrong | Correction |
|---|---|---|
| Panel padding around a table that owns its panel | Burns margin and reads as card-inside-card | `.panel.is-flush`; the table fills edge to edge |
| Eyebrow + title + subtitle stacked above a table | ~40–55px of chrome before the first data row | One 30px `.panel-title` row, or none when column headers suffice |
| Gaps above `--space-4` between adjacent panels | Opens channels; regions stop reading as one plane | `--space-4` (8px) unless a real hierarchy break earns more |
| `height: 48px` inputs and buttons | Consumer sizing in a research-density surface | 28px data controls (24px or 32px with a modifier), ~25px chrome buttons |
| Each KPI as an outlined or shadowed card on its own baseline | Fragments a comparison that should share one baseline | Tinted KPI blocks on one row and baseline, or rule-less `.stat` cells |
| Card list for structured multi-column data | Less scannable and less dense than the alternative | `<table class="data-table">` |
| Shrinking type or controls to buy space | Trades legibility for room that repetition was wasting | Remove repeated headings, helper prose, and redundant units first |
| Hiding evidence to make a narrow layout look tidy | Responsive design is prioritization, not deletion | Collapse support below the primary path, or progressively disclose |

### Color And Type

| Mistake | Why it is wrong | Correction |
|---|---|---|
| A per-tab accent color for "identity" | Breaks system coherence; color stops meaning anything | `--accent` for interaction, semantic tokens for data |
| Signal color on a button, border, or chrome element | Green/red/amber are data vocabulary | Signal colors on values only |
| A solid, green, or red button fill | Reads as an execution control in a research tool | `.btn.is-primary` accent tint for the one primary action; quiet peers |
| `--accent-2` used as a second chrome accent or a series colour | It is the context gold for context tags | Context tags only; comparison series use `--chart-secondary` |
| `--chart-secondary` on a lone or categorical series | The grey reads as "the comparison" | `--chart-primary` for a lone series, `--cat-*` for categories |
| Directional color with no sign, arrow, or label | Meaning disappears under color-vision differences | Pair color with a non-color cue |
| Proportional figures on numeric data, or mono on chrome | Inverts the Two-Type Rule: columns stop aligning and chrome reads as code | `--font-num` for data, `--font-ui` for chrome, `--font-code` for code only |
| Uppercase or letter-spaced labels | Louder and wider than the sentence-case labels around them | `text-transform: var(--label-case)` and `letter-spacing: 0`; uppercase only for identifier codes |
| Type above `--text-xl` inside a research tab | Marketing-page feel | Build hierarchy with weight, placement, and contrast |
| Gradient text or glow text | Decoration with no analytical job | Weight or size |

### Data And State

| Mistake | Why it is wrong | Correction |
|---|---|---|
| Spinner, shimmer, or skeleton on an analytical surface | Motion where the user is trying to read | Stable text (`Loading…`, `N/A`, `No data`) in the final layout position |
| Copy written in capitals (`LOADING…`, `CHART UNAVAILABLE`) | Shouts in a sentence-case interface | Sentence case; codes stay codes |
| A state that changes the layout's geometry | Content jumps as data resolves | Loading, empty, error, and partial states occupy the loaded contract |
| Collapsing zero, missing, N/A, and stale into one `—` | Destroys the distinction the user needs to trust the number | Distinguish them explicitly |
| A prose paragraph interpreting live data | Static string against a moving value; it goes stale silently | Remove it, or generate it in Copilot against live data |
| Text that restates a heading, chart, or visible control | Occupies space that could hold evidence | Cut it |
| Provenance internals (adapter names, concept IDs) in the primary path | Turns a research surface into a schema browser | Tooltip, drilldown, or provenance panel |
| A lone number for a metric whose history the payload already carries | The lowest-information rendering available | Add a sparkline and the week-over-week change |
| A sparkline from too few points, or history fetched only to draw one | Implies a trend the data does not support | Show the number |
| Zebra striping, chart grid lines, or a fading area gradient | Texture with no analytical job | Ruled rows; the chart baseline only; a flat area fill |
| A band fill that encodes no difference | Decoration inside the plot | Fill a band only between a series and its comparison or range |
| Entrance animation on data | Spectacle where precision is the point | Data appears; value flashes may signal direction |
| Hover as the only route to critical content | Fails keyboard and touch | Give it a persistent or focusable path |

---

## 15. Quick Reference

| Axis | Direction |
|---|---|
| Plane | One plane of tonal sheets on the canvas. Tone, alignment, and seams define regions, never shadows or borders |
| Panel background | `var(--panel-bg)` — the solid sheet, one step above `--canvas` |
| Panel seam | `--space-4` (8px) |
| Radius | `--radius-control` controls, `--panel-radius` sheets and blocks, `--overlay-radius` overlays, pills for tags only, `0` nested |
| Elevation | Floating overlays only: `--overlay-radius`, `--overlay-shadow`, `--scrim` behind modal ones |
| Color | `--accent` for interaction; semantic tokens for data meaning; nothing for decoration |
| Themes | Light and dark from one token set, System by default; WCAG AA in both |
| Type | Instrument Sans: tabular figures (`--font-num`) for data, `--font-ui` for chrome, `--font-code` for code only; sentence-case labels; ceiling `--text-xl` in tab content |
| Density | Earned by removing repetition, not by shrinking legibility |
| Controls | ~25px chrome, 28px data-context; action buttons filled, never transparent: `--button-bg`, ghost `--tint`, primary an accent tint |
| Tables | Default for multi-column comparison; the table owns its panel; tinted header band, ruled rows, no zebra |
| Charts | Transparent ground on the sheet, no grid, baseline only; 2px primary in the accent with a flat area; solid grey comparison; bands only for a difference |
| Motion | `--motion-fast` / `--motion-base`, functional only |
| State | Stable geometry across loading, empty, stale, partial, and error |
| Copy | Compact, factual, operational, sentence case; no interpretation beside a live metric |

Browser-level surfaces — text selection, caret, focus rings, scrollbars, and tabular figures — are themed centrally in `tokens.css`. Inherit them; do not restyle them per view.

The final question is simple: **does this feel like one trustworthy research instrument, or like a set of components arranged on a background?**
