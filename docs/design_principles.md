# Gamma — Frontend Design Principles

> **Canonical frontend doctrine.** Read this before designing, implementing, or reviewing Gamma UI. It defines the outcomes the interface must preserve. `frontend/src/lib/theme/tokens.css` is the numeric source of truth for implemented tokens; nearby production components are the source of truth for established behavior.

Gamma is a professional, read-only market research environment. It should feel like a research instrument: dense enough for comparison, quiet enough for sustained attention, and precise enough that the user can trust what changed, where it came from, and what to do next.

The visual lineage is Bloomberg Terminal's information density with Linear's spatial discipline. Gamma is not a terminal imitation, a generic SaaS dashboard, or a data-visualization showcase. Its identity comes from one ruled plane, restrained chrome, deliberate typography, and data that carries most of the visual energy.

## 1. How To Use This Guide

When sources disagree, use this order:

1. **Product boundary:** `roadmap.md` defines what Gamma is allowed to become. Gamma supports research, analysis, comparison, and hypothesis formation—not execution.
2. **Design principles:** this document defines the frontend experience and durable visual rules.
3. **Tokens:** `frontend/src/lib/theme/tokens.css` owns current reusable values. Do not copy values from this document back into CSS if a token already exists.
4. **Pattern implementations:** use the mature surface closest to the task. Do not treat one tab as a universal template.
5. **Local composition:** a view may solve its own information problem as long as it preserves the product boundary and system rules above.

If a component needs a value the token system does not express, first try the nearest existing step. Add a token only when the value represents a reusable role, not a one-off preference. Update this guide when a durable principle changes; update `tokens.css` when an implemented value changes.

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

**The One-Plane Rule.** The workspace reads as one instrument panel divided by seams. Regions do not float as independent objects.

**The Earned-Density Rule.** Density means more useful relationships per viewport, not smaller text or indiscriminate compression. Remove repetition before reducing legibility.

**The Quiet-Chrome Rule.** Controls become visually prominent only when they are active, focused, dangerous, or carrying time-sensitive state. Data supplies the color and contrast at rest.

### What Good Feels Like

- The primary research question is obvious within a few seconds.
- Related values can be compared without excessive scrolling or pointer travel.
- Visual hierarchy remains clear even when color is removed.
- Loading, empty, stale, partial, and error states preserve the final layout's geometry.
- Provenance is easy to reach but does not turn the main surface into a schema browser.
- Each tab has a distinct research purpose while still reading as Gamma.

## 3. Foundations And Tokens

All reusable styling uses tokens from `frontend/src/lib/theme/tokens.css`. Raw CSS values are acceptable only when no semantic token exists and the value is genuinely local, such as a chart-library integration detail. Do not create local color palettes or type scales.

### Color Roles

| Role | Tokens | Intent |
|---|---|---|
| Canvas | `--bg-0` | Root visual field |
| Recessed chrome / inputs | `--bg-1`, `--bg-2`, `--bg-3` | Functional layer distinction, used sparingly |
| Panels | `--panel-bg` | Root-matching solid surface; preserves the plane while masking the canvas texture |
| Purposeful inset surface | `--surface-0`, `--surface-soft` | Overlays, code, callouts, or a meaningful local subsection—not generic card fill |
| Borders | `--panel-border`, `--panel-strong`, `--divider` | Region, emphasis, and internal structure |
| Text | `--text-0`, `--text-1`, `--text-2` | Primary, supporting, and metadata hierarchy |
| Interaction | `--accent`, `--hover-bg`, `--active-bg`, `--focus-ring` | Focus, selection, active navigation, and primary chart series |
| Data semantics | `--positive`, `--negative`, `--warning`, `--data-*` | Direction, status, intensity, and thresholds in analytical content |
| Charts | `--chart-primary`, `--chart-secondary`, `--chart-negative` | Deliberate series hierarchy |

`--accent-2` is not a second chrome accent. Treat it as an analytical comparison/warning color consistent with the chart and semantic palette.

### Typography Roles

Gamma uses two type voices:

- `--app-font`: monospace for data, tickers, dates, prices, quantities, tables, formulas, code, and dense body copy where alignment matters.
- `--display-font`: system sans for navigation, buttons, headings, panel titles, eyebrows, and table headers.

**The Two-Type Rule.** Sans explains the instrument; mono carries the research. Do not use sans for numeric data, and do not force navigation chrome into mono merely because the application is terminal-like.

Every font size resolves to the type scale:

| Token | Size | Typical role |
|---|---:|---|
| `--text-2xs` | 10px | Eyebrows, compact category labels, table headers |
| `--text-xs` | 11px | Metadata, timestamps, secondary labels |
| `--text-sm` | 12px | Compact controls and dense supporting data |
| `--text-base` | 13.5px | Body and primary data text |
| `--text-md` | 15px | Section and panel titles |
| `--text-lg` | 16px | Tab-level titles |
| `--text-xl` | 18px | Hero identifiers inside research tabs |

Use `--leading-tight` for single-line labels and values, `--leading-snug` for dense lists, and `--leading-normal` for prose. Build hierarchy with placement, weight, and contrast before increasing size. Research-tab text normally does not exceed `--text-xl`; the welcome surface is the intentional exception.

### Space, Shape, And Motion

| Scale | Values | Contract |
|---|---|---|
| Space | `--space-1` through `--space-7` (2, 4, 6, 8, 12, 16, 24px) | Snap gaps, padding, and margins to the ramp whenever possible |
| Radius | `--radius-sm` (2px), `--radius-md` (4px) | Small controls and top-level surfaces only; nested geometry is square |
| Motion | `--motion-fast` (120ms), `--motion-base` (180ms), `--ease` | Functional state change, never spectacle |

The default seam is `--space-4` (8px). Panel padding is usually `--space-5` or `--space-6`. `--space-7` is a real group break, not the default rhythm.

## 4. Color, Texture, And Emphasis

**The Color-Has-A-Job Rule.** Blue communicates interaction or the primary analytical series. Green, red, and amber communicate data meaning. Neutral values carry structure. Color never exists only to give a tab personality.

- Use `--accent` for active navigation, focus, selection, interactive emphasis, and the primary chart series.
- Use semantic colors for directional or categorical data only. Pair color with a sign, label, icon, position, or pattern so meaning survives color-vision differences.
- Use chart colors in a clear order; do not give every series equal saturation.
- Keep structural surfaces in the same neutral-cool temperature.
- Never use warm darks, arbitrary tab palettes, glow text, or gradient text.

### Gradients And Texture

Structural panels, cards, tables, and navigation surfaces are flat. Gradients are allowed only when they encode data, express progress/loading, or implement the established root canvas texture.

The dim 24px dot grid in `tokens.css` is Gamma's only ambient texture. Root-matching solid panels mask it, so it appears in seams and unused canvas rather than underneath data. Do not add new decorative textures or repeat the dot grid inside panels.

## 5. Elevation And The Plane Model

Gamma uses a plane model, not an object model. Most SaaS dashboards create hierarchy with filled cards, large gutters, radius, and shadow. Gamma creates hierarchy with reading order, alignment, thin borders, shared baselines, and controlled tonal changes.

### Surface Contracts

| Surface | Background | Boundary | Shape |
|---|---|---|---|
| Top-level panel / self-contained card | `var(--panel-bg)` | `1px solid var(--panel-border)` | `var(--radius-md)` on the outer edge |
| Chart shell nested in a panel | `var(--bg-0)` | `1px solid var(--divider)` | Square |
| Table that owns a panel | `var(--panel-bg)` | The panel border is the table container | Square internally |
| Input / select | `var(--bg-1)` | `1px solid var(--panel-strong)` | `var(--radius-sm)` |
| Local inset / callout | `var(--surface-soft)` when distinction is meaningful | Optional divider | Square when nested |
| Drawer / modal / transient overlay | Solid or functional translucency | Strong boundary | May use shadow to separate transient layers |

- Do not put `box-shadow` on panels, cards, tables, or chart shells.
- Do not nest bordered cards when a divider, row, or shared grid can express the relationship.
- Do not use opacity-layered panel fills to simulate glass.
- Keep adjacent surface gaps at `--space-4` unless a real hierarchy break warrants more.
- Pills are reserved for compact, non-container tags or status chips. Controls, mode buttons, panels, and data containers use the radius scale.

**Audit test:** blur your eyes. The screen should read as a single structured field, not a collection of floating tiles.

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

The familiar `primary-column + support-column` layout is a useful default, not a mandatory template. A wide table, curve explorer, matrix, or comparison canvas may legitimately own the full width.

**The Primary-Path Rule.** At every supported width, the main analysis appears before support content in visual and DOM order.

### Density

- Prefer columns, aligned rows, shared axes, and dividers over independent cards.
- Remove repeated headings, helper prose, redundant units, and decorative whitespace before shrinking controls or type.
- Let charts use their allocation; avoid padded chart islands.
- Use local section scrolling when it preserves context better than an extremely long page.
- Keep a stable alignment system. Numeric columns are right-aligned or decimal-aligned; labels are left-aligned; units and precision remain consistent within a comparison.

### Responsive Behavior

Responsive design is prioritization, not uniform shrinking.

- Use intrinsic layouts (`minmax()`, flexible tracks, content-aware wrapping) before breakpoint-specific patchwork.
- Collapse support content below the primary path when two columns no longer preserve legibility.
- Keep mode switching, the active context, and primary actions visible.
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

Mode bars are visible, compact segmented controls—not hidden navigation or pill groups. Preserve relevant lens state across modes, deep links, keyboard navigation, and overview-to-detail handoffs. A new analytical state should also update Copilot grounding where useful.

## 8. Component Contracts

### Panels And Section Headers

Use panels for distinct analytical regions, not every conceptual group. A panel usually uses `var(--panel-bg)`, a 1px panel border, `--space-5` or `--space-6` padding, and `--space-4` internal gap.

Use a compact panel title or category label when it improves navigation. Do not stack an eyebrow, title, subtitle, and helper sentence by habit. If the surrounding mode and table headers already identify a region, omit the panel header.

### KPI Strips

- Use one shared grid with `gap: 0` and internal dividers.
- Keep labels muted and values visually strong.
- Use signal color only when the metric has directional or status meaning.
- When relevant history is already available, add compact trend context instead of treating a lone number as complete analysis.
- Never turn each KPI into its own floating card.

### Tables

Tables are the default for structured, multi-column comparison.

- Keep headers compact and use the display font; keep data cells mono with tabular numerals.
- Use row heights around 28–32px and minimal vertical padding in dense contexts.
- Align quantities consistently and make units/precision explicit.
- Use subtle dividers, restrained striping, and a quiet interactive-row hover.
- Keep selection, sort, stale, missing, and exceptional states legible without relying on color alone.

**The Table-Owns-The-Panel Rule.** When a table is a panel's primary content, set panel padding to zero and let the panel border contain the table. Do not add a bordered `.table-wrap` inside it.

### Charts

- Prefer shared chart components such as `TimeSeriesChart` when the contract fits.
- Match the root background, use muted grid lines, and establish a clear primary series.
- Titles, legends, units, time ranges, and tooltip precision should make the comparison interpretable without nearby prose.
- Use gradients only when they encode scale or uncertainty.
- Do not imply continuity, precision, or freshness the source data does not support.
- Keep loading, unavailable, empty, and error messages inside the final chart geometry.

### Controls

- Chrome buttons are usually about 25px high; data-context inputs and buttons are usually 28–32px.
- Use compact text or icon buttons. Give icon-only controls an accessible name and, when the meaning is not obvious, a tooltip.
- Primary emphasis is relative: one action may be accent-tinted, while peers remain quiet.
- Destructive actions use semantic styling and explicit copy; Gamma's research flows should rarely need them.
- Disabled controls explain why when the reason is not obvious from the current state.

### Tags, Badges, And Status

Use a tag when compact grouping or status meaning is useful. Tags may use a fully rounded silhouette because they are inline annotations, not structural containers. Use semantic color only when the badge carries corresponding data meaning. Avoid badge clouds and never turn every metadata value into a chip.

### Cards

Cards are appropriate for genuinely self-contained repeated objects such as saved research items, watchlist entries, or generated research artifacts. They still follow the plane model: root-matching surface, thin border, no shadow, restrained outer radius, and no nested cards.

## 9. Data Presentation And Research Integrity

Visual polish must not imply certainty the data does not have.

### Numbers

- Use tabular numerals and stable alignment.
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
- Remove text that merely restates a heading, chart, or visible control.
- Keep caveats, units, freshness, and interpretation boundaries that the data cannot communicate alone.
- Put open-ended interpretation in Copilot or a dedicated research note, not as unqualified static copy beside a live metric.
- Empty and error states say what happened and the next useful action when one exists.

## 10. Interaction, State, And Accessibility

**The Stable-Geometry Rule.** Loading, empty, stale, partial, error, hover, selected, and focused states occupy the same layout contract as loaded content. State changes should not cause avoidable jumps.

- Use stable text such as `LOADING...`, `N/A`, `No data`, or `CHART UNAVAILABLE` in the final content position. Avoid shimmer and spinner overlays on analytical surfaces.
- Data appears without decorative entrance animation. Value flashes may briefly show update direction using `--flash-duration`.
- Use `--motion-fast` and `--motion-base` for state, drawer, collapse, and focus transitions. Respect `prefers-reduced-motion` for nonessential motion.
- Every action is keyboard reachable and has a visible `:focus-visible` state.
- Prefer native elements and semantics; add ARIA only when native HTML cannot express the interaction.
- Maintain a logical focus order after mode changes, drawer operations, and conditional rendering.
- Do not use hover as the only way to reveal critical content or actions.
- Touch targets may be larger than their visible terminal-style control through padding or hit-area techniques, especially at narrow widths.

Copilot is a transient research layer, not a competing dashboard. Its shelf may use functional translucency and shadow because it is an overlay. Generated research artifacts should inherit the density and component grammar of their owning tab.

## 11. Intentional Exceptions

- **Welcome / connection surface:** may use a centered gateway card and larger type because it is a doorway, not a research workspace.
- **Drawers, dialogs, tooltips, and menus:** may use functional elevation or translucency to separate a transient interaction layer.
- **Data visualization:** may use gradients, broader color ramps, or denser labels when they encode analytical meaning and remain accessible.
- **Status tags:** may use pill geometry because their shape communicates a bounded inline annotation.
- **Full-width analytical tools:** may depart from the two-column workspace when the research object needs width.

An exception must have a functional reason. “It looks more modern” is not one.

## 12. Review Tests

Use these tests before handoff. They are outcome checks, not a substitute for visual inspection.

### Research Test

- What question does this surface answer?
- Is the main evidence in the first reading path?
- Can the user compare the important values without unnecessary scrolling or context switching?

### Plane Test

- Do panels merge into one ruled field?
- Are shadows, fills, large gutters, or radius making analytical regions look like floating cards?
- Are nested borders doing work a divider could do more quietly?

### Hierarchy Test

- Does the screen still make sense in grayscale?
- Is sans used for chrome and mono for data?
- Are the loudest elements the most important, current, or actionable ones?

### State Test

- Are loading, empty, error, stale, and partial data states covered?
- Does state change preserve geometry and focus?
- Is missing data distinguishable from zero and not applicable?

### Access Test

- Can the workflow be completed with a keyboard?
- Are focus, selection, and data semantics expressed without color alone?
- Do icon-only actions have accessible names?
- Does the primary path survive narrow widths and text wrapping?

### Drift Scan

Look for:

- raw colors or off-scale type/spacing where a token exists,
- structural gradients, glass surfaces, or non-overlay shadows,
- panel backgrounds that do not use `--panel-bg`,
- container radius above `--radius-md` or pill-shaped controls,
- signal colors used as decorative chrome,
- duplicated headings, helper prose, or provenance internals in the primary path,
- card layouts for data that should be a table or shared grid,
- oversized controls, unstable loading states, or hidden keyboard focus.

## 13. New Surface Checklist

Before shipping a new tab, mode, or major module:

1. Name the research question and the primary evidence.
2. Confirm the scope fits `roadmap.md` and the read-only product boundary.
3. Choose the closest mature reference surface.
4. Define tab, mode, lens, and module responsibilities before composing panels.
5. Use existing tokens and shared components; add reusable primitives only when the role recurs.
6. Place filters and actions near the data they affect.
7. Define loading, empty, stale, partial, error, selected, and focused states.
8. Preserve provenance in the model and choose its appropriate disclosure level.
9. Register navigation, keyboard actions, persistence/deep-link state, and Copilot context where relevant.
10. Validate desktop, intermediate, and narrow layouts; inspect the result, not only the CSS.

---

## 14. Common Mistakes

The fast check after every edit. Left column is what shows up in review; right column is the correction.

### Surface And Depth

| Mistake | Why it is wrong | Correction |
|---|---|---|
| A hand-picked panel background such as `#0f1114` or `transparent` | Breaks the plane. `--panel-bg` resolves to `--bg-0`, a *solid* root-matching fill that masks the canvas dot grid without floating | `background: var(--panel-bg)` |
| `box-shadow` on a panel, card, table, or chart shell | Implies a floating object in a plane-model interface | Remove it; a 1px border carries the boundary |
| `linear-gradient` on a structural surface | Implies lighting and elevation | Flat token fill |
| Opacity-layered panel fills to fake glass | Ambiguous depth, unreadable stacking | Solid token, or `--surface-soft` when an inset is genuinely meaningful |
| A bordered card nested inside a bordered panel | Double borders where a divider would do the same work more quietly | Divider, shared grid, or row |
| `.table-wrap` with its own border inside an already-bordered panel | Defeats the edge-to-edge table contract | Remove the inner border; the panel border contains the table |
| Warm-tinted darks (`rgba(18, 17, 12, …)`) | Temperature mismatch with the cool neutral system | `--bg-*` scale |
| Radius above `--radius-md`, or radius on a nested container | Consumer-app silhouette; nested geometry is square by contract | `--radius-md` top-level, `--radius-sm` controls, `0` nested |
| Pill geometry on a button, mode control, or data container | Pills are reserved for inline tags and status chips | Radius scale |

### Density And Layout

| Mistake | Why it is wrong | Correction |
|---|---|---|
| Panel padding around a table that owns its panel | Burns margin and reads as card-inside-card | `padding: 0`; the table fills edge to edge |
| Eyebrow + title + subtitle stacked above a table | ~40–55px of chrome before the first data row | One compact header row (~26px), or none when column headers suffice |
| Gaps above `--space-4` between adjacent panels | Opens channels; regions stop reading as one instrument | `--space-4` (8px) unless a real hierarchy break earns more |
| `height: 48px` inputs and buttons | Consumer sizing in a research-density surface | 28–32px data controls, ~25px chrome buttons |
| Each KPI wrapped in its own card | Fragments a comparison that should share one baseline | One grid, `gap: 0`, internal dividers |
| Card list for structured multi-column data | Less scannable and less dense than the alternative | `<table>` |
| Shrinking type or controls to buy space | Trades legibility for room that repetition was wasting | Remove repeated headings, helper prose, and redundant units first |
| Hiding evidence to make a narrow layout look tidy | Responsive design is prioritization, not deletion | Collapse support below the primary path, or progressively disclose |

### Color And Type

| Mistake | Why it is wrong | Correction |
|---|---|---|
| A per-tab accent color for "identity" | Breaks system coherence; color stops meaning anything | `--accent` for interaction, semantic tokens for data |
| Signal color on a button, border, or chrome element | Green/red/amber are data vocabulary | Signal colors on values only |
| `--accent-2` used as a second chrome accent | It is an analytical comparison/warning color | Keep it in the data and chart palette |
| Directional color with no sign, arrow, or label | Meaning disappears under color-vision differences | Pair color with a non-color cue |
| Sans on numeric data, or mono forced onto navigation chrome | Inverts the Two-Type Rule | Mono carries the research; sans explains the instrument |
| Type above `--text-xl` inside a research tab | Marketing-page feel | Build hierarchy with weight, placement, and contrast |
| Gradient text or glow text | Decoration with no analytical job | Weight or size |

### Data And State

| Mistake | Why it is wrong | Correction |
|---|---|---|
| Spinner, shimmer, or skeleton on an analytical surface | Motion where the user is trying to read | Stable text (`LOADING...`, `N/A`, `No data`) in the final layout position |
| A state that changes the layout's geometry | Content jumps as data resolves | Loading, empty, error, and partial states occupy the loaded contract |
| Collapsing zero, missing, N/A, and stale into one `—` | Destroys the distinction the user needs to trust the number | Distinguish them explicitly |
| A prose paragraph interpreting live data | Static string against a moving value; it goes stale silently | Remove it, or generate it in Copilot against live data |
| Text that restates a heading, chart, or visible control | Occupies space that could hold evidence | Cut it |
| Provenance internals (adapter names, concept IDs) in the primary path | Turns a research surface into a schema browser | Tooltip, drilldown, or provenance panel |
| A lone number for a metric that has history | The lowest-information rendering available | Add compact trend context |
| Entrance animation on data | Spectacle where precision is the point | Data appears; value flashes may signal direction |
| Hover as the only route to critical content | Fails keyboard and touch | Give it a persistent or focusable path |

---

## 15. Quick Reference

| Axis | Direction |
|---|---|
| Plane | One ruled field. Borders and alignment define regions, never shadows or fills |
| Panel background | `var(--panel-bg)` — solid, root-matching |
| Panel seam | `--space-4` (8px) |
| Radius | `--radius-md` top-level, `--radius-sm` controls, `0` nested |
| Elevation | Overlays only (drawers, dialogs, tooltips, menus) |
| Color | `--accent` for interaction; semantic tokens for data meaning; nothing for decoration |
| Type | Mono for data, sans for chrome; ceiling `--text-xl` in tab content |
| Density | Earned by removing repetition, not by shrinking legibility |
| Controls | ~25px chrome, 28–32px data-context |
| Tables | Default for multi-column comparison; the table owns its panel |
| Charts | Transparent ground, muted grid, one clear primary series |
| Motion | `--motion-fast` / `--motion-base`, functional only |
| State | Stable geometry across loading, empty, stale, partial, and error |
| Copy | Compact, factual, operational; no interpretation beside a live metric |

Browser-level surfaces — text selection, caret, focus rings, scrollbars, and tabular numerals — are themed centrally in `tokens.css`. Inherit them; do not restyle them per view.

The final question is simple: **does this feel like one trustworthy research instrument, or like a set of components arranged on a dark background?**
