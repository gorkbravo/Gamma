# Gamma — Design Principles

> **This document is the canonical style guide for the Gamma platform.** It is written for AI agents, contributors, and any future pass working on UI/UX. If you are building or modifying a component, a view, or a layout — read this first, follow it precisely, and do not improvise away from it. Every tab is architecturally distinct, but all tabs must be legible as part of the same system. These principles govern that coherence.

---

## 1. Philosophy

Gamma is a professional-grade quantitative research platform. Its users are researchers and analysts who need to process a lot of information quickly and without friction. The interface should feel like a precision instrument — not a consumer app, not a SaaS dashboard, not a data visualization showcase.

The primary references are **Bloomberg Terminal** and **linear.app**: the information density and seriousness of the former, the cleanliness and spatial control of the latter. The result is dense but not cluttered, dark but not gloomy, structured but not rigid.

**The interface serves the data. Never the reverse.**

### Provenance In The UI

Gamma should preserve provenance aggressively in the data model, but **must surface it selectively in the UI**.

The core rule is:

- primary analytical surfaces should show the research object first,
- provenance should appear when it materially helps interpretation, trust, or debugging,
- provenance should not dominate the main reading path of a chart, KPI strip, or statement table.

In practice this means:

- show provenance in dedicated provenance panels, filing chronology, drilldowns, tooltips, notes, or explicit source areas,
- do **not** default to rendering adapter names, internal origins, concept ids, or transformation labels as secondary text inside every cell or row,
- if provenance text reads like developer text rather than research text, keep it available in the payload but hide it from the primary surface.

Gamma is a research environment, not a schema browser.

### What "Good" Looks Like
The **Macro → Cross-Asset** mode is the current gold standard. It is dense text, numbers, signal badges, and thin borders on a single flat surface. Content is the structure. There are no filled card backgrounds, no decorative spacing, no visual chrome competing with the data. All tabs should converge toward this level of flatness and density.

---

## 2. Design Tokens

All styling must use the token system defined in `frontend/src/lib/theme/tokens.css`. Never use raw hex or rgba values for colors that have a token equivalent. This enables future theming and ensures consistency.

### Background Scale (neutral-cool, near-black)
| Token | Value | Usage |
|---|---|---|
| `--bg-0` | `#070809` | Root canvas. The base of everything. |
| `--bg-1` | `#0b0d10` | One step up. Inputs, chrome surfaces. |
| `--bg-2` | `#0f1114` | Two steps up. Rare — only for deep nesting distinction. |
| `--bg-3` | `#131618` | Three steps up. Hover states on elevated surfaces. |

### Surface Tokens
| Token | Value | Usage |
|---|---|---|
| `--panel-bg` | `transparent` | **All panel/card backgrounds.** Panels inherit root. |
| `--surface-0` | `#0a0c0f` | Solid sub-section backgrounds within panels. |
| `--surface-1` | `#0b0d10` | Chrome surfaces (topbar fallback). |
| `--surface-2` | `#141719` | Rarely used. |
| `--surface-soft` | `rgba(10, 12, 14, 0.62)` | Subtle section tints within panels (e.g. code blocks, callouts). |

### Borders & Dividers
| Token | Value | Usage |
|---|---|---|
| `--panel-border` | `#1e2228` | Standard panel/card border. |
| `--panel-strong` | `#2e353e` | Emphasized borders (topbar actions, active states). |
| `--divider` | `rgba(50, 56, 64, 0.55)` | Thin internal dividers, table borders, chart shells. |

### Text
| Token | Value | Usage |
|---|---|---|
| `--text-0` | `#f0f2f5` | Primary text. Data values, headings, body. |
| `--text-1` | `#c2c8d0` | Secondary text. Descriptions, less-critical info. |
| `--text-2` | `#8a919a` | Tertiary text. Labels, captions, metadata, timestamps. |

### Accent & Semantic Colors
| Token | Value | Usage |
|---|---|---|
| `--accent` | `#7aa6c8` | **The accent.** Active states, interactive borders, highlights, primary chart series. |
| `--positive` | `#4bb474` | Positive signals in data contexts only (P&L up, bullish). |
| `--negative` | `#c66b61` | Negative signals in data contexts only (P&L down, bearish). |
| `--warning` | `#c49a5a` | Warnings, amber signals. Data contexts only. |

### Chart Colors
| Token | Value | Usage |
|---|---|---|
| `--chart-primary` | `#7aa6c8` | Primary series. Matches accent. |
| `--chart-secondary` | `#c49a5a` | Secondary/comparison series. |
| `--chart-negative` | `#b65d54` | Negative/short series. |

Chart themes (`amber`, `green`) can override `--chart-primary` via `data-chart-theme` on the root element. Components should always reference the token, never hardcode.

---

## 3. Color Rules

- **Blue is the accent. Do not introduce other accent colors into UI chrome.** Signal colors (red, green, amber) are permitted in data contexts only — P&L indicators, status badges, heatmap scales. They must not appear on buttons, borders, or backgrounds of UI elements.
- **No gradients on UI surfaces.** No `linear-gradient`, no `radial-gradient` on panels, cards, the root canvas, or any structural element. Gradients are permitted only in: data visualizations (heatmaps, color scales), accent-colored interactive elements (progress bars, loading indicators).
- **All surfaces share the same color temperature.** Every background derives from the neutral-cool base (`--bg-0` through `--bg-3`). Never mix warm-tinted darks (brown-blacks like `rgba(18, 17, 12, ...)`) with the cool base. A warm panel on a cool root reads as a separate object even when luminance is identical.
- **No opacity-based background layering on panels.** Backgrounds at fractional opacity (`0.6`, `0.82`, `0.98`) create ambiguous depth — the brain reads translucent sheets as stacked. Use `transparent` or a solid token. Exception: navigation chrome (sidebar, tab bar) and transient overlays (modals, drawers) may use translucent backgrounds where the translucency is functional.

### On Themes (Future)
User-selectable themes (lighter mode, alternative accent) are a valid future feature. Every color must be expressed as a CSS variable so themes can be applied at the token level without rewriting components. Never hardcode a hex color that has a token equivalent.

---

## 4. Elevation and Depth — The Plane Model

**This is the most important principle for Gamma.**

Gamma uses a **plane model**, not an **object model**.

In an object model (the wrong approach), cards are raised boxes sitting on top of a darker background. The background shows through as strips of negative space, reinforcing the sense that each card is a separate floating element. This is how most SaaS dashboards work. **It is not how Gamma works.**

In a plane model (the right approach), the entire interface is one flat surface. Regions are defined by borders and lines — not by color contrast between a card and its background. A panel's background is the same as the root. What makes a panel a panel is its border, not its fill. The result reads like a spreadsheet or terminal — one coherent plane with internal geometry.

**Bloomberg Terminal is a plane. Most SaaS dashboards are object stacks. Gamma is a plane.**

### Rules
- **Panel backgrounds: `var(--panel-bg)` (transparent).** The panel's background is the root's background. What makes a panel a panel is its `1px solid var(--panel-border)` border. Never its fill.
- **Chart containers: `var(--bg-0)`.** Charts match root exactly.
- **No `box-shadow` on cards or panels.** None. Shadows imply elevation, which contradicts the plane model.
- **No `border-radius` > `4px` on data containers.** Panels and cards use `0px`. Buttons may use `2px`. Nothing uses large radii (no pills, no rounded cards).
- **No nested cards.** If content can be separated by a divider line, a card was not necessary.
- **Gaps between panels: `0.5rem` (8px).** This is tight enough that the gap reads as a seam, not as empty space between objects. Larger gaps (>10px) between adjacent panels are not permitted — they create visible "channels" of background that undermine the plane model.

### Token Usage Summary
| Surface | Background | Border |
|---|---|---|
| Panel / card | `var(--panel-bg)` | `1px solid var(--panel-border)` |
| Chart shell | `var(--bg-0)` | `1px solid var(--divider)` |
| Sub-section within panel | `var(--surface-soft)` | none or `var(--divider)` |
| Input / select | `var(--bg-1)` | `1px solid var(--panel-strong)` |
| Navigation chrome (sidebar, tab bar) | `rgba(8, 13, 18, 0.98)` | contextual |
| Topbar | `var(--bg-0)` | `border-bottom: 1px solid var(--panel-border)` |

---

## 5. Typography

### Font
The app uses a monospace stack: `"JetBrains Mono", "Cascadia Mono", "IBM Plex Mono", "Consolas", monospace`. This is set globally and inherited by all elements. Do not override it.

### Size Hierarchy
The base font size is `13.5px` on the body. All sizes below are actual computed values currently in use or targets for convergence.

| Role | Size | Weight | Color | Notes |
|---|---|---|---|---|
| Category label (e.g. `PORTFOLIO MONITOR`, `MACRO`) | `10–11px` | `400–600` | `--text-2` | Uppercase, wide letter-spacing (`0.08–0.1em`) |
| Sidebar title (`NAVIGATION`) | `~11px` | `600` | `--text-2` | Uppercase |
| Body / data text | `13–13.5px` | `400` | `--text-0` or `--text-1` | Default inherited size |
| Section headers (H3) within a tab | `~14–16px` | `700` | `--text-0` | These are panel titles like "Participant Summary", "Book Diagnostics" |
| Tab-level hero titles (H2) | `~16–20px` | `700` | `--text-0` | Major identifiers like the asset name or market question. Keep concise. |
| App branding (H1 `GAMMA`) | `~12px` | `600` | `--text-0` | Small, uppercase, wide tracking. Not a display heading. |

### Rules
- **Hierarchy by weight first, size second.** A `600` weight label next to `400` weight data creates hierarchy without changing size. Use size jumps sparingly.
- **No text larger than ~20px inside tab content.** Gamma is not a marketing page. If a heading needs to be bigger than the data around it, `700` weight at `15–16px` is sufficient.
- **No italic in data contexts.** Reserve italic for footnotes, tooltips, or explicitly editorial text.
- **No text shadows, glow effects, or gradient text fills.**
- Letter-spacing: `0.01em` on body text (set globally). Category labels use wider spacing (`0.08–0.1em`) for small-caps effect.

### Spacing
- Line height for dense data: `1.4–1.5`. The global default is `normal` (browser ~1.2 for monospace); dense data lists may override.
- Padding inside buttons, inputs, and cells: see Component specifications below.

---

## 6. Layout and Information Density

Gamma sits closer to Bloomberg than to Koyfin in density preference. The layout should make full use of available screen space without feeling accidental or overwhelming.

### Grid Structure
Every view follows a consistent layout pattern:

```
┌────────────────────────────────────────────────┐
│ Topbar (fixed, full width)                     │
├──────┬─────────────────────────────────────────┤
│ Side │  Workspace Shell                         │
│ bar  │  ┌─────────────────────┬──────────────┐ │
│      │  │ primary-column      │ support-col  │ │
│      │  │  ┌─────────────┐   │ ┌──────────┐ │ │
│      │  │  │ panel       │   │ │ panel    │ │ │
│      │  │  ├─────────────┤   │ ├──────────┤ │ │
│      │  │  │ panel       │   │ │ panel    │ │ │
│      │  │  └─────────────┘   │ └──────────┘ │ │
│      │  └─────────────────────┴──────────────┘ │
└──────┴─────────────────────────────────────────┘
```

- **Workspace shell gap**: `0.5rem` (8px) — the space between the sidebar/tab-bar and the view content.
- **View-level gap**: `0.5rem` (8px) — between all adjacent panels, both vertically and in the `workspace-grid` columns.
- **Panel internal padding**: `~0.85–1.05rem` (13–17px). Compact. Content should feel close to its border.
- **Panel internal gap** (between elements within a panel): `0.5rem` (8px) for sections, tighter for rows.

### Rules
- **No gratuitous whitespace.** Padding separates logical groups, not decorates. Space is earned by what it separates.
- **Columns over cards.** Where data can be arranged in a grid or column layout with dividers, prefer that over wrapping in card containers.
- **Visual grouping through proximity and line, not box.** Related items should be spatially close. A `1px var(--divider)` rule is a perfectly sufficient separator.
- Charts should fill their allocated space — no excessive internal padding within a chart's bounding box.
- Scrolling within a section (not the whole page) is acceptable and preferred over hiding or collapsing data.

### Responsive Behavior
Views use CSS grid with `minmax()` columns. At narrow widths (~980–1320px depending on tab), `workspace-grid` collapses to single column. The primary column always comes first.

---

## 7. Tab Architecture and Modes

Every tab represents a **research domain**. Tabs are not single-purpose views — they are containers for multiple related modes of inquiry.

### Mode Pattern
Each tab should support **modes**: distinct but related views that share the tab's data context. Modes are accessed via a segmented control / mode bar at the top of the tab content.

**Current implementation — Macro tab:**
- Snapshot | Cross-Asset | Rates & Policy | Events / Regimes

Modes share state where it makes sense (selected region, timeframe, theme) and diverge in presentation. They are depth within a domain, not separate tabs.

**Mode bar styling:**
- Font: `~12.5px`, same family
- Padding: `~6px 14px`
- Height: `~27px`
- Active state: `rgba(--accent, 0.12)` background tint
- Inactive: transparent, text only
- No border-radius on individual buttons; the bar itself may have a subtle border

### Navigation
- The **sidebar** (hideable, left) is the primary tab navigation. Tabs are listed vertically, can be reordered via drag-and-drop, and pinned.
- **Keyboard bindings** for tab switching and common actions are first-class. Every meaningful navigation action should be bindable. A dedicated key-bindings window exists.
- The **Copilot shelf** (hideable, left overlay) provides AI-assisted context. It should never overlap or displace primary content when open — it slides over as a drawer.

### Tab Header Pattern
Each tab's first panel typically contains:
1. A **category label** (uppercase, small, muted — e.g. `PREDICTION MARKETS`, `RESEARCH WORKSPACE`)
2. A **title** (H2, bold — e.g. the active asset name, the market question)
3. **Context controls** (timeframe selector, view mode, benchmark input) aligned to the right or below
4. A **KPI strip** — a row of key metrics with values, inline, using the `kpi-grid` pattern (no gaps, metrics separated by vertical padding)

---

## 8. Components

### Panels (Articles)
The primary structural container. Every distinct content region in a view is a `<article class="panel">`.

```css
.panel {
  background: var(--panel-bg);        /* transparent */
  border: 1px solid var(--panel-border);
  padding: 0.85rem–1.05rem;           /* 13–17px */
  display: grid;
  gap: 0.5rem;                        /* 8px internal */
}
```

### KPI Strips
Horizontal row of key metrics. Used in tab headers and summary sections.

```css
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(...));
  gap: 0;  /* KPIs share borders, no gap */
}
.metric {
  padding: 0.2rem 1rem;
  border-right: 1px solid var(--divider);  /* or left, depending on position */
}
```

- Metric label: `--text-2`, small, uppercase or sentence case
- Metric value: `--text-0`, bold
- Sub-label: `--text-2`, smaller

### Buttons

**Topbar / chrome buttons** (Change View, Refresh, Settings):
- Font: `~12px`
- Padding: `~4.5px 9px`
- Height: `~25px`
- Border: `1px solid var(--panel-strong)`
- Background: transparent or `var(--bg-1)` for emphasis
- Border-radius: `0px`

**Sidebar tab buttons**:
- Font: `~13px`
- Padding: `~9px 11px`
- Height: `~35px`
- Border-radius: `2px`
- Active: `rgba(--accent, 0.08)` background, `1px solid rgba(--accent, 0.36)` border

**In-panel action buttons** (Run Analysis, Compute, etc.):
- Match input height of their context
- Background: `var(--bg-1)` or `rgba(--accent, 0.08)` for emphasis
- Border: `1px solid var(--panel-strong)` or `rgba(--accent, 0.24)`

**General rules:**
- No large buttons in data-dense areas. Icon buttons or compact text buttons preferred.
- Primary actions: filled or accent-tinted background.
- Secondary / ghost: border only, accent border on hover.
- Destructive: `--negative` border/text, no fill.

### Inputs and Controls

Current state across most tabs:
- Height: `48px` (this is on the tall side — `28–32px` is the target for dense contexts)
- Font: `13.5px`
- Padding: `~9px 12px`
- Background: `var(--bg-1)` (`#0b0d10`)
- Border: `1px solid var(--panel-strong)`
- Border-radius: `0px`

For dense data contexts (screeners, filter bars, parameter inputs), inputs should be more compact:
- Target height: `28–32px`
- Reduced padding: `4–6px vertical`, `8–10px horizontal`

Dropdowns and selects: same styling as text inputs. Compact, dark, minimal chrome.

### Tables
Preferred layout for structured multi-column data.

- Column headers: `~11px`, `--text-2`, uppercase optional, wide letter-spacing
- Row height: `28–32px` in dense mode
- Cell padding: `0.5rem` (8px) horizontal, minimal vertical
- Borders: `1px solid var(--divider)` between rows
- Alternating row backgrounds: `var(--table-stripe)` — nearly invisible (`rgba(122, 166, 200, 0.018)`)
- Sortable columns: small directional icon only
- Interactive rows (clickable): cursor pointer, hover background `rgba(--accent, 0.06)`

### Dividers
- `1px solid var(--divider)` — the primary tool for separating content groups
- Muted, low contrast. They guide the eye, not call attention to themselves.
- Prefer dividers over cards when the content doesn't need a full border box.

### Cards (Use Sparingly)
Only when content is genuinely self-contained (a watchlist item, a single-asset snapshot, a signal card).
- Background: `var(--panel-bg)` (transparent) — same as panels
- Border: `1px solid var(--panel-border)`
- No nested cards. Ever.
- No shadow. No fill.
- If it requires visual weight beyond a border to read as a card, reconsider the component choice.

---

## 9. Data Visualization

### Chart Containers
```css
.chart-shell {
  background: var(--bg-0);
  border: 1px solid var(--divider);
  overflow: hidden;
}
```

### Rules
- Chart backgrounds match root. Never white, never lighter.
- Axis labels: `~11px`, `--text-2`.
- Grid lines: very low opacity (`0.05–0.1`), hairline.
- Primary series: `var(--chart-primary)` (blue). Secondary: `var(--chart-secondary)`. Negative: `var(--chart-negative)`.
- Never use saturated random colors for multiple series. Stay within the token palette.
- Tooltips: compact, `var(--surface-0)` background, `1px solid var(--divider)`, sharp corners. No rounded, glassy, or drop-shadowed tooltips.
- Loading states: the text `LOADING...` or `CHART UNAVAILABLE` centered in the shell area. No spinners overlaying content. No shimmer animations.
- The TradingView watermark (TV logo) appears in chart shells — this is expected.

### Value Flash Animations
When data values update in real-time, a brief color flash indicates direction:
- Up: green flash (`rgba(75, 180, 116, 0.22)`)
- Down: red flash (`rgba(198, 107, 97, 0.22)`)
- Changed: amber flash (`rgba(196, 154, 90, 0.18)`)

Duration: `var(--flash-duration)` (800ms), ease-out. These are the only permitted "decorative" animations on data elements.

---

## 10. Motion and Interaction

Gamma is a research tool, not a marketing site. Animation should be functional, not decorative.

- **Transitions**: shelf show/hide, panel collapse/expand — `150–200ms`, `ease-out`.
- **No entrance animations on data.** Data appearing in a chart or table just appears. No fade-in, no slide-in.
- **Hover states**: subtle. `rgba(--accent, 0.06)` background tint or border color shift on interactive rows/buttons.
- **Loading indicators**: non-intrusive and positionally stable. Data loads into its space; it doesn't push other content around.
- **No skeleton loaders.** Use static placeholder text (`N/A`, `LOADING...`, `No data`) in the same layout the real data will occupy.

---

## 11. Copilot Integration

The Copilot is an AI-assisted research companion accessible from every tab.

### Shelf Behavior
- Opens as a left-side drawer overlay with translucent background (`rgba(8, 13, 18, 0.984)`)
- Box shadow is permitted on the drawer (it's a transient overlay, not a panel)
- Header shows the current tab context (e.g. `RESEARCH`, `CRYPTO`)
- Contains a chat-style input at the bottom with a tab-context dropdown and "Generate" button

### Styling
- Copilot message cards use `var(--surface-soft)` backgrounds with `1px solid rgba(--accent, 0.18)` borders
- The copilot is grounded in the active tab's data — it reads and references the current analysis state
- Generated content (research cards) should match the density and styling of the tab it will appear in

---

## 12. The Welcome / Landing Page

The landing page (connection screen) is the one exception to the plane model. It is a centered card on a dark background — an intentionally simple gateway before the user enters the workspace. It should remain minimal:

- Centered card with border, moderate padding
- Connection status, action buttons
- "Portfolio View" and "Research View" as entry points
- No complex layout, no data density — this is a doorway, not a workspace

---

## 13. Adding a New Tab — Checklist

When building a new tab, follow this exact checklist:

1. **Use the standard view structure**: `<section class="view">` > `<div class="workspace-grid">` > `primary-column` + `support-column`
2. **Panel backgrounds**: `var(--panel-bg)` (transparent). Borders: `1px solid var(--panel-border)`.
3. **Layout gaps**: `0.5rem` (8px) everywhere — between panels, between columns, within grids.
4. **Panel padding**: `0.85–1.05rem`. Internal gap: `0.5rem`.
5. **First panel**: category label (uppercase, small, muted) + H2/H3 title + optional KPI strip + controls.
6. **Charts**: use `TimeSeriesChart` component. Background `var(--bg-0)`, border `1px solid var(--divider)`.
7. **Colors**: only `--accent` for interactive elements. Signal colors only in data values.
8. **No gradients, no shadows, no opacity layering on panels.**
9. **Mode bar**: if the tab supports multiple modes, add a segmented control matching the Macro tab pattern.
10. **Copilot**: ensure the tab can provide grounding context to the Copilot via `copilot_context_helpers`.
11. **Keyboard bindings**: register tab-specific actions in the keybindings system.
12. **Responsive**: `workspace-grid` should collapse to single column at narrow widths.
13. **Test against the Macro Cross-Asset benchmark**: does your tab feel as flat and dense? If not, reduce spacing, remove fills, simplify chrome.

---

## 14. Common Mistakes to Avoid

| Mistake | Why it's wrong | What to do instead |
|---|---|---|
| Adding a `background` to a panel that isn't `var(--panel-bg)` | Creates depth, breaks plane model | Use `transparent` or `var(--panel-bg)` |
| Using `box-shadow` on any non-overlay element | Implies floating, breaks plane model | Remove it. Use a border. |
| Using warm-tinted colors (`rgba(18, 17, 12, ...)`) | Color temperature mismatch with cool root | Use tokens from `--bg-*` scale |
| Gaps > 10px between adjacent panels | Creates visible channels, feels like separate objects | Use `0.5rem` (8px) |
| Introducing a new accent color for a tab's "identity" | Breaks system coherence | Blue is the accent. Signal colors for data only. |
| `border-radius` > 4px on containers | Consumer-app aesthetic, not terminal | `0px` on panels, `2px` on buttons max |
| Large headings (>20px) inside tab content | Marketing-page feel | Keep titles `15–20px`, use weight for emphasis |
| Spinner or shimmer loading states | Over-engineered, distracting | Static placeholder text in final layout position |
| Opacity-based panel backgrounds | Ambiguous depth, glassy feel | Solid token or transparent |
| `linear-gradient` on panel background | Implies lighting/elevation | Flat solid only |
| Rendering provenance metadata in every table cell or KPI by default | Turns the UI into a developer/debug surface | Keep provenance in the model, but surface it only where the user is explicitly asking for source context |

---

## 15. Principles Summary

| Principle | Direction |
|---|---|
| Color | Near-black base, blue accent only, signal colors in data only, single color temperature |
| Depth | Plane model. Borders define surfaces. No shadows, no gradients, no opacity layering |
| Typography | Monospace, compact (13.5px base), hierarchy by weight then size, uppercase labels for categories |
| Layout gaps | `0.5rem` (8px) between all panels — tight seams, not channels |
| Panel backgrounds | `transparent`. Always. |
| Cards | Sparingly. Border-defined, same background as root. Dividers first. |
| Nested cards | Never |
| Whitespace | Intentional, minimal. Earned by what it separates. |
| Tab structure | Domain → Modes → shared state. Mode bar at top. |
| Animation | Functional only. 150–200ms transitions. No entrance effects on data. |
| Buttons/inputs | Compact. 25px chrome buttons, 28–32px target for data-context inputs. |
| Charts | Dark (`--bg-0`), muted grids, token palette, no white backgrounds |
| New tabs | Follow the checklist. Benchmark against Macro Cross-Asset. |
