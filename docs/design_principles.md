# Gamma — Design Principles

> This document defines the design philosophy for the Gamma platform. It is the canonical reference for any agent, contributor, or future pass working on UI/UX. Every tab is architecturally distinct, but all tabs must be legible as part of the same system. These principles govern that coherence.

---

## 1. Philosophy

Gamma is a professional-grade quantitative research platform. Its users are researchers and analysts who need to process a lot of information quickly and without friction. The interface should feel like a precision instrument — not a consumer app, not a SaaS dashboard, not a data visualization showcase.

The primary references are **Bloomberg Terminal** and **linear.app**: the information density and seriousness of the former, the cleanliness and spatial control of the latter. The result is dense but not cluttered, dark but not gloomy, structured but not rigid.

**The interface serves the data. Never the reverse.**

---

## 2. Color

### Base Palette
- **Background**: Near-black. The root canvas of every surface.
- **Primary accent**: Blue. Used for active states, highlights, interactive affordances, and key data signals.
- **Secondary surfaces**: Slightly elevated grays — but elevation should be expressed through *contrast and border*, not through shadow or glow.

### Rules
- Do not use multiple accent colors without deliberate justification. Blue is the accent.
- Status/signal colors (red for negative, green for positive, amber for neutral/warning) are permitted in data contexts (P&L, change indicators, alerts) but should not bleed into UI chrome.
- No gradients on UI surfaces. Gradients are acceptable only in data visualizations (e.g. heatmaps, color scales).
- Avoid opacity-based layering that creates "glowing" or soft blending effects. Surfaces should be defined by solid colors and crisp borders.

### On Themes (Future Consideration)
User-selectable themes (e.g. a lighter mode, an alternative accent color) are a valid future feature. If implemented, every design decision made now should be expressed as a CSS variable or equivalent token so that themes can be applied at the token level without rewriting components.

---
 
## 3. Elevation and Depth
 
**This is one of the most important principles for Gamma.**
 
Gamma uses a **plane model**, not an **object model**.
 
In an object model (the wrong approach), cards are raised boxes sitting on top of a darker background. The background shows through as strips of negative space between cards, reinforcing the sense that each card is a separate floating element. This is how most SaaS dashboards work. It is not how Gamma should work.
 
In a plane model (the right approach), the entire interface is one flat surface. Regions within that surface are defined by borders and lines — not by color contrast between a card and the background behind it. A card's background color is the same as the root background. What makes a card a card is its border, not its elevation. The separation between two panels is a `1px` line, not a gap of darker background showing through. The result reads like a spreadsheet or a terminal — one coherent plane with internal geometry — rather than a stack of panels floating in space.
 
**Bloomberg Terminal is a plane. Most SaaS dashboards are object stacks. Gamma is a plane.**
 
### Rules
- Card and panel backgrounds must match the root background color. Do not use a lighter or different-toned surface color to distinguish a card from its surroundings.
- Borders define regions. Every card or panel boundary should be expressed as a `1px solid` border at low-to-mid opacity. That border is the only thing that needs to exist.
- No `box-shadow` on cards or panels. None. A shadow implies the element is lifted above the surface — this contradicts the plane model entirely.
- No visible background-color gaps between adjacent panels. If two panels sit next to each other, they share a border or a divider line — not a strip of root background between them.
- No `border-radius` greater than `4px` on data containers. Slight rounding is acceptable on buttons and small interactive elements only.
- Cards within cards are not permitted. If content can be separated by a line — a card was not necessary in the first place.
 

---

## 4. Typography

### Size
Current state: fonts and interactive elements are too large and waste space. The principle is **compact but readable**.

- Body / data text: `12–13px`. This is terminal-appropriate. Users of this platform expect density.
- Labels / secondary info: `11px`.
- Section headers within a tab: `13–14px`, medium weight.
- Tab-level titles or major section identifiers: `15–16px` max.
- Do not use large typographic display elements inside tabs. This is not a marketing page.

### Weight and Style
- Use weight to establish hierarchy, not size alone. A `500` weight label next to `400` weight data is sufficient.
- Avoid italic in data contexts. Reserve it for footnotes, tooltips, or explicitly editorial text.
- No text shadows, glow effects, or gradient text fills.

### Spacing
- Line height for dense data: `1.4–1.5`.
- Padding around text inside buttons, inputs, and cells: reduce from current state. Text should feel close to its container without being cramped. Target `4–6px` vertical padding, `8–10px` horizontal, as a baseline.

---

## 5. Layout and Information Density

Gamma sits closer to Bloomberg than to Koyfin in density preference. The layout should make full use of available screen space without feeling accidental or overwhelming.

### Rules
- **No gratuitous whitespace.** Padding should be intentional — used to separate logical groups, not to make the interface feel "airy." Space is earned by what it separates, not as a default margin.
- **Columns over cards.** Where data can be arranged in a structured grid or column layout with dividers, prefer that over wrapping everything in card containers.
- **Visual grouping through proximity and line, not box.** Related items should be spatially close. A `1px` rule is a perfectly sufficient separator.
- Charts and data visualizations should occupy as much of their allocated space as makes sense — no excessive internal padding within a chart's bounding box.
- Scrolling within a section (not the whole tab) is acceptable and preferred over hiding or collapsing data by default.

---

## 6. Tab Architecture and Modes

Every tab represents a **research domain**. Tabs are not single-purpose views — they are containers for multiple related modes of inquiry within that domain.

### Mode Pattern
Each tab should support **modes**: distinct but related avenues of research that share the tab's underlying data context. Modes are accessed via a mode selector (e.g. a compact tab-within-tab bar, or a segmented control) at the top of the tab's content area.

**Example — Research Tab:**
- Mode A: Market Overview (heatmap, sector flows)
- Mode B: Ticker / Portfolio Analysis (current functionality)

Modes share state where it makes sense (e.g. selected asset, time range) and diverge only in presentation layer. They are not separate tabs — they are depth within a domain.

### Navigation
- The **side shelf** (hideable) is the primary tab navigation surface. This pattern is established and should not change.
- **Keyboard bindings** for tab switching and common actions are a first-class feature. Every meaningful navigation action should be bindable.
- The **AI Copilot shelf** (hideable, right side) is established as a persistent but non-intrusive layer. It should never overlap or displace primary content.

---

## 7. Components

### Buttons
- Reduce padding. Current state has too much space around button labels.
- Primary action buttons: filled, blue background, dark text or white text.
- Secondary / ghost buttons: border only, no fill, blue border on hover.
- Destructive actions: red border/text, no fill by default.
- No large buttons in data-dense areas. Icon buttons or compact text buttons preferred.

### Inputs and Controls
- Inputs should match the density of their context. In a dense data panel, an input field should not be `40px` tall.
- Target `28–32px` height for inputs in data contexts.
- Dropdowns and selects: compact, dark, minimal chrome.

### Tables
- Preferred layout for structured multi-column data.
- Column headers: `11–12px`, muted color, uppercase optional but not required.
- Row height: `28–32px` in dense mode.
- Alternating row backgrounds: acceptable but very subtle (near-invisible contrast step).
- Sortable columns should indicate state with a small directional icon only — no large affordances.

### Cards
- Use only when the content is genuinely self-contained and benefits from a boundary (e.g. a summary widget, a watchlist item, a single-asset snapshot card).
- No nested cards. Ever.
- Card border: `1px solid` at low opacity — enough to define the edge, not enough to create visual noise.
- Card background: one step above root background at most. If it requires a visible shadow to read as a card, reconsider whether a card is the right component.

### Dividers
- `1px` horizontal or vertical rules are the primary tool for separating content groups.
- Color: muted, low contrast against background. They should guide the eye, not call attention to themselves.

---

## 8. Data Visualization

- Chart backgrounds should match the panel/surface they sit in — not white or light.
- Axis labels: `11px`, muted.
- Grid lines: very low opacity, preferably no fill — just a hairline.
- Color usage in charts: blue as primary series color; red/green for directional signals; muted tones for secondary series. Never use saturated random colors.
- Tooltips: compact, dark background, sharp border. No rounded, glassy, or drop-shadowed tooltips.
- Loading states: skeleton lines or a minimal spinner. No full-panel overlays unless strictly necessary.

---

## 9. Motion and Interaction

Gamma is a research tool, not a marketing site. Animation should be functional, not decorative.

- **Transitions**: tab switches, panel collapse/expand, shelf hide/show — these should animate, but quickly (`150–200ms`, ease-out).
- **No entrance animations on data.** Data appearing in a chart or table should not fade in or slide in. It just appears.
- **Hover states**: subtle. A slight background tint or border color shift on interactive rows/buttons is sufficient.
- **Loading indicators** should be non-intrusive and positionally stable — data loads into its space, it doesn't push other content around.

---

## 10. Principles Summary

| Principle | Direction |
|---|---|
| Color | Black base, blue accent, signal colors in data only |
| Depth | Flat. Borders define surfaces, not shadows |
| Typography | Small, dense, hierarchy by weight not size |
| Cards | Sparingly. Dividers first, cards only when justified |
| Nested cards | Never |
| Whitespace | Intentional, not decorative |
| Tab structure | Domain → Modes → shared state |
| Animation | Functional, fast, no decorative entrance effects |
| Buttons/inputs | Compact. Reduce padding from current state |
| Charts | Dark surfaces, muted grids, controlled color palette |
