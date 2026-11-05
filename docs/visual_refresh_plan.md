# Visual Refresh Implementation Plan (B′ · Tonal compact)

_Living implementation and handoff document._

- Decision approved: 2026-10-28. Target direction **B′ "Tonal compact"**; the current left navigation drawer stays as primary navigation.
- Last reviewed: 2026-11-05
- Implementation status: V1 complete and merged into main on 2026-10-28 (77d40e5 tables and tags, 7867445 controls and inline stats). V2 complete and merged into main on 2026-10-28 (9676017). V3 complete and merged into main on 2026-10-30 (a68ed3a). V4 complete and merged into main on 2026-11-03 (c3343b4). V5 complete and merged into main on 2026-11-04 (9192e29). V6 done on branch `claude/v6-hardening` (2026-11-05), not merged.
- Roadmap owner: Workstream 1, Cross-Cutting Platform Foundation, in [`../roadmap.md`](../roadmap.md). V1–V3 are shared-platform work; V4–V6 are the visual layer on top of it.
- Exploration and measurements: private artifact `https://claude.ai/artifact/GWx2nqyGg7WK2JhAaxeXXb` (version 2, 2026-10-28). It mocks Sitrep, Commodities › Curves & Spreads, Options › Overview, Risk › Overview and Copilot in every direction considered.
- Doctrine: [`design_principles.md`](./design_principles.md) describes B′ since V5; this plan records the decisions behind it, the kept exceptions and the drift-scan findings left for V6.

## Decision summary

Gamma moves away from the terminal look (dark only, monospace chrome, uppercase tracked labels, dot-grid canvas, phosphor chart themes) to a clean, product-grade look that stays a research instrument.

B′ keeps what made direction B attractive and holds it to today's working density:

- **Kept from B:** cool neutral palette in light and dark, Instrument Sans for everything with tabular figures for data, borderless tonal sheets, pill tags, soft provenance pill, floating overlays.
- **Pulled back to today's rhythm:** 8px seams, 30px panel-title rows, inline basis labels, 14px KPI values, 28px table rows.
- **Borrowed from direction C:** 20-session sparklines on curve and KPI stats where history exists, and band fills between two series when the band encodes a difference (curve versus last week, book versus benchmark).
- **Unchanged:** the read-only boundary, provenance on demand, stable geometry across states, the type and space scales, control heights and the left drawer.

### Measured basis

Data rows fully visible above a 780px fold at a 1280px window, with the drawer closed. That is roughly a maximised Gamma window on a 1080p laptop at 125% scaling. Measured on the exploration mocks with identical sample content.

| Direction | Sitrep | Commodities | Options | Risk | Total |
|---|---:|---:|---:|---:|---:|
| Today | 46 | 14 | 17 | 12 | 89 |
| B (first draft) | 43 | 12 | 13 | 10 | 78 |
| **B′ (target)** | 45 | 14 | 16 | 11 | **86** |

B′ costs three rows of 89. The guardrail for V4 is to stay within −5% of today on these four surfaces, measured in the real views.

With 12 tabs, a top tab bar fits only 8–9 tabs at 1280px and gains no vertical space, so navigation stays in the drawer.

## Target specification

### Typography

- **Interface, labels and prose:** Instrument Sans (SIL Open Font License), weights 400/500/600/700, self-hosted as `woff2` under `frontend/public/fonts/`. The packaged desktop app must not depend on a font CDN.
- **Data:** the same family through `--font-num` with `font-variant-numeric: tabular-nums` and `font-feature-settings: "tnum" 1`. Right-aligned numeric columns must stay aligned.
- **Code, raw JSON and the Script editor:** a monospace through `--font-code` (Cascadia Mono, JetBrains Mono, Consolas).
- **Labels:** sentence case, 11px, weight 500, no letter-spacing, replacing uppercase with 0.1em tracking.
- **Scale:** the 10–18px ramp is unchanged. View titles use `--text-md` (15px) and panel titles 12.5px.
- **Charts:** `lightweight-charts` draws on canvas, which cannot apply `tabular-nums`. Axis labels may use proportional figures. If the crosshair price label visibly jitters, those labels switch to `--font-code`.
- **Decided (V4 gate, 2026-11-03):** tickers and contract codes (`BZZ6`, `CLZ6`, option symbols) and ISO dates stay in Instrument Sans with tabular figures; there is no `--font-id`.

### Color

Values from the exploration; contrast is verified in V3.

| Token role | Light | Dark |
|---|---|---|
| Canvas | `#eceff3` | `#0b0e12` |
| Panel (sheet) | `#ffffff` | `#151a20` |
| Tint (header band, inputs, stat blocks) | `#f4f6f9` | `#1b2129` |
| Line (overlay and control edges) | `#e3e7ec` | `#232a33` |
| Line strong | `#cfd6df` | `#343d49` |
| Rule (row and inner dividers) | `#eef1f4` | `#212830` |
| Text 0 / 1 / 2 | `#0f1720` / `#3b4655` / `#697485` | `#edf1f6` / `#b8c1cc` / `#808b99` |
| Accent (interaction, primary series) | `#2952cc` | `#7d9df2` |
| Accent soft / hover | 9% / 4% of accent | 14% / 6% of accent |
| Positive / negative / warning | `#0f7b52` / `#c4372c` / `#986000` | `#45c48b` / `#f2806f` / `#e0aa50` |
| Chart secondary / grid | `#b7bfcb` / `#eef1f4` | `#4a5462` / `#1f252d` |
| Scrim (behind overlays) | `rgba(18, 26, 38, 0.22)` | `rgba(0, 0, 0, 0.45)` |

Semantic soft fills (tags, stale and conflict cells, heat maps) mix the semantic color into transparent at 13–14%. The dot-grid canvas texture is removed.

### Surfaces, shape and components

- **Panels:** solid sheet on the canvas, no border, no shadow, 6px radius, 8px seams (`--space-4`). A table that owns its panel keeps zero panel padding.
- **Tables:** 28px rows, 10–12px side padding, tinted header band, light row rules, no zebra, sticky header. Heat-map cells may separate with 2px gaps and a `--radius-sm` (2px) radius (V6 decision; the treemaps used a raw 3px).
- **KPI strips:** cells share one row and baseline as tinted blocks (6px radius, 6px gap), never bordered or shadowed. 14px values, plus a sparkline and week-over-week change where history exists.
- **Tags:** pill with a dot, toned by one variable (`--tg`: neutral, positive, negative, warning, accent).
- **Provenance badge:** soft pill reading `● Live · IBKR · 16:42 UTC · 2 warnings`. The full detail stays in the tooltip.
- **Mode bars and role toggles:** a segmented track on the tint, with the selected segment on the sheet, a 1px outline and weight 600.
- **Controls:** heights unchanged (about 25px chrome, 28–32px data). Inputs and selects are tinted without a border; focus shows the ring.
- **Overlays:** drawer, dialogs, menus, tooltips and the Copilot shelf float with a 12px radius, shadow and scrim. The drawer stays 248px wide with pinning and drag reordering.
- **Charts:** 2px rounded primary line in the accent, flat 9% area fill, baseline only, solid light-grey comparison series. Band fills are allowed only when they encode a difference.
- **Themes:** light and dark, with a Settings choice of System, Light or Dark (default System).
- **Settings migration:** the chart-theme setting (blue, amber and green phosphor) is retired. The font-family setting becomes a "Data figures" choice: Instrument Sans (default) or a monospace, which only changes `--font-num`.

## Checkpoints

| Checkpoint | Scope | Acceptance gate | Status |
|---|---|---|---|
| V1 — Shared primitives under the current look | Extend `frontend/src/lib/theme/primitives.css` (panel, header, mode bar, KPIs and eyebrow already exist) with the data table, tag, 26px panel title, inline stats, buttons, inputs and selects. Migrate the ~20 scoped `th, td` copies and 9 `.tag` copies. Keep genuine local exceptions as scoped overrides and list them. | No visual change except the deliberate convergences listed under [V1 convergences and kept exceptions](#v1-convergences-and-kept-exceptions), each reviewed on before/after screenshots of every view in mock mode (1440×900, DPR 1). `npm run typecheck`, `npm test` and `npm run build` pass without warnings from the changed files. | Done (2026-10-28), merged into main as 77d40e5 and 7867445 |
| V2 — Token completeness and font roles | Replace the 71 raw `rgba(122, 166, 200, …)` values and 92 hex literals (18 files). Fix the ~62 `font: inherit` that pull chrome back to mono. Split `--app-font`/`--display-font` into `--font-ui`, `--font-num`, `--font-code` and `--font-label`. Add tint, soft semantic, scrim, `--panel-radius`, `--panel-border-width` and label-case tokens. Move `chart-colors.ts` and the flash keyframes onto tokens. | Values unchanged, so screenshot parity still holds. A grep gate shows no raw accent colors or hex literals in `.svelte` files outside a documented exception list. | Done (2026-10-28), merged into main as 9676017; see [V2 token completeness and font roles](#v2-token-completeness-and-font-roles) |
| V3 — Theme infrastructure | `data-theme` on `<html>` (System/Light/Dark) with persistence and a Settings control, plus a theme store. `TimeSeriesChart`, `Surface3D`, `MaritimeMap` and the CodeMirror editor re-read tokens on change. Retire the chart-theme setting; turn the font setting into "Data figures". Add the light token block, with current dark values kept as the dark block. | Switching theme needs no reload and every chart and map recolors. Contrast meets WCAG AA (4.5:1 text, 3:1 graphics and focus), including warning text on its soft fill in light mode. | Done (2026-10-30), merged into main as a68ed3a; see [V3 theme infrastructure](#v3-theme-infrastructure) |
| V4 — B′ values and fonts | Self-host Instrument Sans and preload it. Set B′ token values and the structural rules: borderless sheets, radii, header band, pill tags, KPI blocks, segmented controls, floating drawer and chart styling. Resolve the identifier-font decision. | Visual review of all 13 views in light and dark at 1440, 1000 and 390px. Rows above a 780px fold on Sitrep, Commodities, Options and Risk stay within −5% of today. Fonts resolve in the packaged desktop build with no network. | Done (2026-11-03), merged into main as c3343b4; see [V4 B′ values and fonts](#v4-b-values-and-fonts) |
| V5 — Doctrine and skills | Rewrite `design_principles.md` in place (map below) and update the `tokens.css` comments. Update the `gamma-ui` and `gamma-charts` skills outside the repo, whose descriptions still ask for "more like a professional trading terminal". | §1–§15 numbering is unchanged and the skills' §14/§15 references still land on the right content. The drift scan reflects B′. | Done (2026-11-03), merged into main as 9192e29 on 2026-11-04; see [V5 doctrine and skills](#v5-doctrine-and-skills) |
| V6 — Hardening | Per-surface exceptions: Sitrep stream, Sealanes map style, `Surface3D`, the Script editor, the Copilot run inspector, website screenshots. Update the screenshot baselines and run a usability audit pass. | Usability audit with no new P0/P1 visual findings; website screenshots regenerated or explicitly deferred. | Done on branch `claude/v6-hardening` (2026-11-05), not merged: no new P0/P1 visual finding in the live audit, website screenshots regenerated; see [V6 hardening](#v6-hardening) |

Rough effort for one developer who knows the codebase: V1 6–8, V2 3–4, V3 2–3, V4 5–8, V5 1–2 and V6 2–3 dev-days, about **19–28 dev-days** in total. These are estimates from a static read, not commitments. V1 and V2 would be needed for any restyle and also pay off without one.

## V1 convergences and kept exceptions

V1 moves every data table onto `.data-table` in `primitives.css`. Where a family genuinely differs, it takes a modifier instead of a scoped copy:

| Modifier | Meaning | Used by |
|---|---|---|
| `is-nowrap` | every cell on one line; the panel scrolls sideways | Risk, Options, Portfolio, Prediction Markets, Equity Research, Strategy Lab, Copilot options and Strategy Lab analyses, parameter sweep, curve history, IV snapshot comparison |
| `is-top` | multi-line cells start at the top of the row | Macro Trade Partners and Country Compare, Sitrep markets, Crypto, Macro snapshot, Copilot transcript and rich text |
| `is-sticky` | the header stays in view on `--panel-bg` | Portfolio, Prediction Markets, Macro Rates and Snapshot, Crypto, Equity Research, Fundamentals, Strategy Lab |
| `is-open-end` | no rule under the last row | Crypto, Equity Research, Fundamentals, Strategy Lab, Macro snapshot |
| `is-relaxed` | 8px rows | Crypto, Equity Research, Strategy Lab, Macro Rates and Snapshot |
| `is-body-text` | 13.5px cells instead of the 12px data size | the same reading tables, plus Sitrep markets, Options and Prediction Markets |
| `is-compact` | 4px × 6px cells | Prediction Markets, Copilot risk and Strategy Lab analyses, Copilot transcript, Script tables, dataset picker |
| `is-grid` | full cell grid with a tinted header | Copilot transcript and rich-text tables |
| `is-figures` | first column a label, the rest right-aligned figures, 8px × 12px cells | curve history, IV snapshot comparison, scope analysis, run comparison |
| `is-keyvalue` | quiet label column on the left, value on the right | retained evidence |

The modifiers use `:where()`, so they keep the specificity of the base rules and a view's scoped cell class still wins.

Deliberate convergences, reviewed on before/after screenshots (2026-10-28):

- Cell line height 1.3 everywhere (was `normal`, 1.2 or 1.32). Rows grow 1–3px; two-line rows such as the Prediction Markets screener gain about 3px, so re-measure the V4 row-count guardrail on this state.
- Body cells in `--text-1` where they inherited `--text-0`, with row identifiers (`td strong`) in `--text-0` at weight 600.
- Column headers 10px at weight 600 that never wrap (some were 11px, weight 500 or the browser's bold).
- Sticky headers on `--panel-bg` (Portfolio, Prediction Markets and Macro used `--surface-0`).
- Row hover at `--hover-bg` and the selected row at `--active-bg` (the global hover was 4.5%; Crypto and Prediction Markets selected at 8%).
- Prediction Markets cells 6px from the column edge instead of 8px; Crypto and Macro Rates header rows 6px instead of 8px tall padding.
- Macro Rates and Snapshot rules on `--divider` instead of a fainter raw rgba.
- Mixed-case headers in the figure tables and the dataset picker become the shared uppercase label.
- Risk empty rows use `.empty-row` (11px instead of 12px).
- No visual change for the tags: the four gold copies (Cross-Asset and divergence agreement labels, the Rates region and window labels) become the shared `.tag.is-tinted.context`.

Kept exceptions:

- Not data tables, left out of `.data-table`: the Setup grid (`SetupWizard` `.grid`), the Sitrep status table and the Options payoff heat map.
- Per-table specifics that stay scoped on top of `.data-table`: Sitrep market column proportions and fixed layout; Options chain strike, ITM and ATM shading and the surface's sticky row headers; the Fundamentals DCF sheet grid; the Strategy Lab composer's compact inputs; 11px mono cells in the Script tables; content width and 2px rows for tables inside Copilot answers; Prediction Markets group, section and tick columns; the partner code under each Trade Partners name; Macro Rates' fainter stripe and the Macro snapshot row hover (raw rgba in V1, accent mixes since V2).
- Tags: the warning outline at 0.3 in MacroLinkedMarketRow and MacroSnapshot, `flex-shrink: 0` in three Macro rows, and MacroCoherencePanel's wrapping chips. MacroCoherencePanel is not imported anywhere; deleting or reviving it is a follow-up.

### Controls and inline stats

Buttons opt into `.btn`, fields into `.form-control` and inline stat cells into `.stat`, all in `primitives.css`:

| Primitive | Default | Modifiers | Used by |
|---|---|---|---|
| `.btn` | 28px, 4px × 8px, `--bg-1` on a `--panel-strong` edge | `is-small` (24px), `is-large` (32px), `is-ghost`, `is-primary`, `is-danger` | Equity Research, Strategy Lab, Options, Commodities, Crypto, Fundamentals, Risk, Portfolio, Prediction Markets, Macro, the curve, IV and run comparisons, Setup, the Script components, Diagnostics, the view error boundary, the Copilot run inspector |
| `.form-control` | the same surface, 28px | `is-small` (24px), `is-large` (32px) | the same views, plus the Macro FX pickers |
| `.stat` | label `span`, 15px value `strong`, note `small`, left rule, first cell flush | `is-large` (18px value), `is-compact` (13.5px value that truncates) | Equity Research and Strategy Lab; Fundamentals and Crypto (`is-large`); Prediction Markets (`is-compact`) |

States and modifiers sit in `:where()` so a view's scoped class (`.tick`, `.market-button`, `.row-select`) still wins. `:disabled` and `:focus-visible` are two classes deep, so a disabled ghost button still reads as disabled and the global focus ring never wins the tie. Stat values space themselves with padding, because views reset `strong { margin: 0 }` at the same specificity.

Deliberate convergences, reviewed on before/after screenshots (2026-10-28):

- Buttons are 28px with 4px × 8px padding. Before: Crypto 6 × 12, Setup 0 × 12, the Script panels 6 × 12 at 30px. The handoff and refresh buttons are `.is-small`.
- Fields have 4px × 8px padding. Before: Portfolio and Prediction Markets 2 × 6, Commodities 0 × 8; Setup and Script fields were 30px tall.
- One hover (the edge turns 35% accent) and one disabled state (`--text-2` on a `--panel-border` edge) replace opacity 0.45, 0.5 and 0.6, background tints and accent text.
- Secondary buttons are `.is-ghost` (transparent, `--text-1`). The load, run and next actions are `.is-primary` (accent text on a 10% tint).
- Focus is a 1px accent outline inset by 1px.
- Stat labels are 10px at 0.1em in every view (Crypto and Prediction Markets used 11px or 0.12em), and Prediction Markets' first stat cell sits flush.
- Tone and `.absent` classes on stat values now take effect: N/A values dim and signed returns are coloured. Before, each view's `.metric strong { color }` rule overrode them.

Kept exceptions:

- Navigation chrome: the top bar, drawer, mode bars and mode-bar style toggles. The Fundamentals statement toggles and the Portfolio and Prediction Markets segmented pickers take `.btn` but keep their contextual rules.
- Controls that are not buttons in the usual sense: Sitrep's tape controls (strip items, 20px reload buttons, pins, chips, the note editor), the landing view's choice cards, the Commodities market cards, the Crypto basket cards, the Risk row selectors and dependency zoom.
- Copilot chat chrome: the composer, role tabs, session and storage actions, the artifact list and the transcript confirmations. Converge it with the Copilot shelf in V4.
- Contextual sizes: the table and handoff action rows in Equity Research and Strategy Lab, the Fundamentals compact buttons, the Options payoff pickers.
- Stats that follow a different pattern: the Options and Portfolio KPI cells (right rule, padded on both sides), the `MacroMetricRow` component and the Macro snapshot metrics, and the Copilot and Script result strips.
- `font: inherit` stays wherever a view had it, with its explicit size; V2 resolved it (see below).

## V2 token completeness and font roles

V2 ran on branch `claude/v2-token-completeness` from local main 9412498, one commit per step: 2b3ee01 font roles, 5be065d new tokens, 600d961 raw colours, 1b5ed86 chart colours and flashes, 32362a3 `font: inherit`, bb26c40 the raw-colour gate; merged into main as 9676017 after the user reviewed the step 6 pairs. Steps 2–5 matched main on every mock-mode screen, the Setup dialog, the landing page and four e2e harnesses (1440×900, DPR 1) apart from the known noise; step 7 left the production build byte-identical. Step 6 is the one deliberate visual change.

### Inventory (2026-10-28, before V2)

V1 moved code, so the planning numbers above were recounted in `frontend/src`:

- 62 raw `rgba(122, 166, 200, …)`: 52 in 14 `.svelte` files, 10 in `tokens.css` and `primitives.css`.
- 188 `rgb()`/`rgba()` literals in all, 163 of them in 25 `.svelte` files. Besides the accent they mixed `--positive`, `--warning` and `--text-2`, plus colours no token carried: a pre-neutral navy `#2e3c4a` in Macro, Copilot and chart rules, `#273544` bar tracks, the muted red `#c66b61` of soft negative fills and heat maps, `#070b10` chart halos and black shadows.
- 136 hex literals: 92 in 3 `.svelte` files (83 in `MaritimeMap`, almost all stale `var()` fallbacks, several no longer matching their token; 5 in an Equity Research comment; 4 `Surface3D` fallbacks), 40 token definitions and 4 in the `chart-colors.ts` map.
- 63 `font: inherit` rules in 30 files; 44 `--app-font` and 42 `--display-font` usages.

### Font roles

| Token | Today | Used for |
|---|---|---|
| `--font-ui` | the sans (`Segoe UI Variable Text` stack) | chrome, headings, buttons, prose |
| `--font-label` | `var(--font-ui)` | eyebrows, column headers, stat, KPI and field labels |
| `--font-num` | the mono (`Cascadia Mono` stack) | data figures; the document default |
| `--font-code` | the same mono | code, raw JSON, model output, the Script editor |

`--app-font` and `--display-font` remain as aliases of `--font-num` and `--font-ui`. The Settings font choice now overrides `--font-num` and `--font-code`, which together cover what it changed before. V3 turns it into the "Data figures" choice that changes `--font-num` only.

### New tokens

| Token | Value today | Used by |
|---|---|---|
| `--tint` | `var(--bg-1)` | `.form-control`, the `.data-table.is-grid` header |
| `--accent-soft`, `--positive-soft`, `--negative-soft`, `--warning-soft` | the semantic colour at 6%, 6%, 8% and 8% (the tinted tag's fills) | `.tag.is-tinted` |
| `--negative-muted` | `#c66b61` | soft negative fills, outlines and heat maps (Macro, provenance badge, Risk correlation, Equity Research treemap) |
| `--scrim` | `--bg-0` at 45% | the navigation drawer's backdrop |
| `--panel-radius`, `--panel-border-width` | `var(--radius-md)`, `1px` | `.panel` |
| `--label-case` | `uppercase` | the chrome labels in `primitives.css` |
| `--rule-navy`, `--track`, `--chart-halo` | `#2e3c4a`, `#273544`, `#070b10` | legacy values views used without a token |
| `--shadow-ink` | `#000` | every shadow; `--shadow` mixes from it |
| `--canvas-dot`, `--flash-up`, `--flash-down`, `--flash-neutral` | the literal rgba values | the canvas dot grid and the value-flash keyframes |

`--table-stripe`, `--hover-bg`, `--active-bg` and `--focus-ring` are now mixed from `--accent`. Tokens that script reads (`--divider`, `--accent`, the chart, semantic, text and surface colours) stay literal, because `colorWithAlpha()` parses only hex and `rgb()`.

### How raw colours became tokens

- A literal whose colour is a token became that token mixed into transparent at the same strength: `rgba(122, 166, 200, 0.06)` is `color-mix(in srgb, var(--accent) 6%, transparent)`. A probe painted 165 cases (accent, navy, muted red, green and black at every strength used, on three backgrounds) with no pixel difference for fills, borders and blurred shadows.
- Gradients and animations are the exception. A mixed colour in a gradient stop or a keyframe, written inline or through a token, interpolates in floating point and moves pixels by one level (the canvas dot grid, the FanChart bands, the first frame of the green flash). Those keep literal values: as tokens (`--canvas-dot`, `--flash-*`) or as listed exceptions (the FanChart stops).
- Colours built in script use `mixToken()` from `chart-colors.ts` (Risk correlation and cluster fills, the Equity Research treemap) or read tokens at runtime (`Surface3D` and `MaritimeMap`, which also lost their stale fallbacks).
- `chart-colors.ts` lost its hex-to-token map; every series already names `var(--token)`.
- Views keep their own strengths as inline mixes (`color-mix(in srgb, var(--positive) 8%, transparent)`). V4 converges them onto the soft tokens when it changes the strengths anyway.

### Raw-colour gate and kept exceptions

`frontend/src/lib/theme/raw-colors.test.ts` runs with `npm test`. It fails on any hex or `rgb()`/`rgba()` literal with numeric channels in a `.svelte` file or in `primitives.css` that is not on its exception list, and on any listed exception that no longer exists. The list:

| File | Literal | Why it stays |
|---|---|---|
| `FanChart.svelte` | seven `rgba(122, 166, 200, …)` gradient stops | a mixed stop colour moves pixels by one level |
| `FanChart.svelte` | `rgba(42, 56, 70, 0.26)`, `rgba(244, 247, 251, 0.94)` and `0.12`, `rgba(106, 168, 255, 0.32)` | one-off grid, history line, halo and tooltip colours with no token |
| `StatusRail.svelte` | `rgba(8, 13, 18, 0.98)` | settings popover background, a one-off |
| `MaritimeMap.svelte` | `rgba(2, 6, 12, 0.7)` | vessel chevron outline drawn on canvas |
| `MacroCoherencePanel.svelte` | `rgba(255, 255, 255, 0.015)` | the component is not imported anywhere |
| `RiskView.svelte` | `rgb(87, 135, 176)` | eighth cluster colour, no token |
| `RiskView.svelte` | `rgb(253,231,37)` | end of the viridis colormap, which encodes data |

The gate cannot see colour channels kept as numbers in script: the viridis stops in `RiskView` and the `Surface3D` colormaps. They encode data rather than theme and stay as they are. FanChart, StatusRail and MaritimeMap are V3's to resolve when the light theme needs them.

### `font: inherit` (step 6, the deliberate change)

A scoped `font: inherit` beat the global `button { font-family }` rule and pulled chrome buttons back to mono. Each rule now sets the family after it:

- To `--font-ui`: action buttons in Equity Research, Strategy Lab, Options, Prediction Markets, Fundamentals, Crypto, Risk, the Macro handoffs, the Script workspace and dataset picker, Diagnostics, the Copilot run inspector and scope analysis; Copilot chat chrome (new chat, context picker and options, artifacts and storage triggers, role tabs, plan and send, session confirmations, storage actions); the Copilot drawer's role tabs, context picker, generate and close buttons; transcript confirmations and evidence toggles; Sitrep's follow-up pins and note buttons; Sealanes map controls and shelf actions; the Surface3D reset; icon buttons (☆ ▸ ✕ ◻ →).
- Unchanged, by the user's decision: every input, select and textarea keeps `font: inherit` and the font of its context. Most are mono; the ones inside headers and labels that already use `--font-ui` stay sans.
- Unchanged, because they show figures: the Crypto basket cards, the Equity Research treemap tiles, the Fundamentals scenario cards, and the Sealanes flow and event rows and replay picker set `--font-num` again where a new view rule would have reached them. Sitrep's tape rows, market strip and ticker chips, the Macro focus cards and rows, and the Copilot transcript chips keep `font: inherit`, which is mono there.
- Already sans before V2, untouched: the landing choices, the top bar, the drawer, the status rail, Risk row selectors and Copilot session actions. The tooltip trigger keeps `font: inherit` on purpose, so it takes the font of whatever it wraps.

Side effects reviewed on the before/after pairs: sans labels are narrower, so button rows and auto-margined groups shift a few pixels. Buttons without a fixed height take the sans line height and grow by 2–5px: the Prediction Markets venue picker (+5px), the Sealanes overlay list and MODES and 3D controls, and the Copilot drawer tabs and generate button. Every element whose family changed went from mono to sans and is a button or its content; no field or figure changed. A first attempt that also pinned fields to `--font-num` turned the top-bar tab search and several header pickers from sans to mono, so fields were left as they were.

### Not done in V2, for later checkpoints

- Field and view labels (`<label>` text, many scoped `.label` spans) are mono because the document defaults to `--font-num`. V4 switches the document default to `--font-ui` and marks data surfaces explicitly.
- 192 scoped `text-transform: uppercase` in 51 `.svelte` files do not use `--label-case` yet. V4 decides each one, because some are identifiers rather than labels.
- The Copilot card backdrop (black at 40%) and the Setup dialog backdrop (`--bg-0` at 78%) keep their own values; V4 converges them on `--scrim`.
- `--text-3` is referenced in `AuthenticatedResearchScriptImage.svelte` and the Script editor theme but defined nowhere, so those colours fall back to inheritance. Found during the inventory; not changed.

## V3 theme infrastructure

V3 ran on branch `claude/v3-theme-infrastructure` from main a1c74e2, one commit per step: 175e419 theme preference, 8dc3dbc light token block and contrast test, 3ec377c charts, 3D surface and map repaint on theme change, 7d5430d chart theme retired and Data Figures, 1d36bd0 theme colours for the last dark-only literals, 29e0b79 open windows kept in sync, 8948d0a WCAG AA on every rendered text; merged into main as a68ed3a after the user reviewed the light screenshots and the contrast pairs.

### Theme preference

- `frontend/src/lib/stores/appearance.ts` holds the preference (System, Light or Dark), persists it in `localStorage` (`gamma.theme`) and writes the resolved theme to `data-theme` on `<html>`. System follows the operating system, including changes while the app is open. `index.html` and `keybindings.html` apply the stored choice in an inline script before first paint.
- **Default: Dark until V4**, as the user decided on 2026-10-29: the light theme is a hybrid until V4 restyles the structure. The target default stays System.
- Settings has Theme (Dark, Light, System) and Data Figures (Default or one of five monospace fonts). Data Figures overrides `--font-num` only, so code keeps `--font-code`, and persists in `gamma.dataFigures`. The blue, amber and green chart themes are retired. Neither old setting was persisted, so nothing needed migrating.

### Light token block

`tokens.css` layers `:root[data-theme="light"]` over the dark block. Derived tokens (`--panel-bg`, `--tint`, the soft fills, `--table-stripe`) follow their bases. Tokens that script reads stay literal hex in both blocks.

| Role | B′ light | V3 light | Why it differs |
|---|---|---|---|
| Canvas | `#eceff3` | `--canvas` `#eceff3` | new token; equals `--bg-0` in dark |
| Sheet | `#ffffff` | `--bg-0`, `--panel-bg` `#ffffff` | |
| Tint | `#f4f6f9` | `--bg-1`, `--tint` `#f4f6f9` | |
| Line / line strong | `#e3e7ec` / `#cfd6df` | `--panel-border` `#dce1e8` / `--panel-strong` `#c3cbd6` | a shade stronger, because V3 keeps the panel and control borders B′ removes |
| Rule | `#eef1f4` | `--divider` `#e1e6ec` | same reason |
| Text 0 / 1 / 2 | `#0f1720` / `#3b4655` / `#697485` | `#0f1720` / `#3b4655` / `#636e7f` | `--text-2` reaches 4.5:1 on the tint |
| Accent | `#2952cc` | `#2952cc` | |
| Positive / negative / warning | `#0f7b52` / `#c4372c` / `#986000` | `#0c7049` / `#b83329` / `#8a5a00` | 4.5:1 on their 13% soft fills |
| Accent soft / hover | 9% / 4% | `--accent-soft`, `--active-bg` 9%; `--hover-bg` 4% | |
| Semantic soft fills | 13–14% | 13% | |
| Chart secondary | `#b7bfcb` grey | `#8a5a00` gold | the secondary series keeps its dark-theme role until V4 restyles charts; B′ grey is 1.8:1 on white |
| Scrim | `rgba(18, 26, 38, 0.22)` | the same | |
| Dot grid | removed | `--canvas-dot: transparent` | |

Categorical (`--cat-*`) and intensity (`--data-*`) colours, which B′ does not specify, are darkened to reach 3:1 on white.

### Contrast gate

`frontend/src/lib/theme/contrast.test.ts` resolves the tokens of both blocks (including `var()` and `color-mix()`), composites translucent colours over their background and checks WCAG AA: 4.5:1 for text on panels, tints and surfaces and for semantic text on its soft fill (warning on its fill included), and 3:1 for chart, categorical and intensity colours and the focus ring. Both themes pass. To pass in dark, `--focus-ring` went from 55% to 60% of the accent (it measured 2.99:1); it shows only on keyboard focus.

### Charts, the map and the editor

- `TimeSeriesChart` rebuilds on a theme change, as it already did for the retired chart theme.
- `Surface3D` re-reads its canvas colours and redraws.
- `MaritimeMap` re-reads its MapLibre colours and repaints the base map, lanes, ports, chokepoints, flows, replay and watchlist layers, and redraws the vessel chevrons. No light CARTO style is needed: Gamma already hides the base style's layers and recolours the background, water and borders from tokens. Repainting found a bug: the base-map recolour hid every layer that was not a base layer, including Gamma's own lanes and ports. It now touches only the base style's layers, recorded on first load.
- The SVG charts (FanChart, DistributionChart, BarRankChart) and the CodeMirror editor theme themselves with CSS variables and follow without code. The editor's syntax colours came to tokens later (see the closed gaps below).
- FanChart's gradient stops are `rgba(var(--accent-rgb), α)`: unlike a `color-mix()` stop, this paints exactly what the literal did. Its history line and the Settings popover gained tokens with a value per theme.

### Verification

- Dark parity: two dark captures of main as noise control, then the branch at 7d5430d, all 52 mock-mode screens at 1440×900, DPR 1, with computed styles. No style or geometry difference outside the known noisy screens (Crypto, Options and Sitrep data, timestamps, the Refresh button) apart from one antialiased corner pixel group. The Setup dialog, the landing page and four e2e harnesses are identical. A later dark run at 1d36bd0 started after midnight and differs from it only in date-driven data (Prediction Markets fresh/delayed chips, Macro FRED loads, Portfolio history); none of its style changes comes from a token.
- Live switch: Settings, dark → light → dark on Commodities and Sealanes without a reload and with no page errors. The chart and the map repaint; the second dark frame matches the first apart from rounded-corner antialiasing.
- Light review: all 52 screens, the Setup dialog, the landing page, the open Copilot drawer and the Sealanes shelf were captured in the light theme for review, with the V3 handover note. The e2e harness pages do not initialise the theme and stay dark; they are test fixtures.

### Gaps closed after the first review (2026-10-30)

- **Open windows stay in sync.** A theme or Data Figures change reaches the app's other open windows (the key bindings window, a second tab) through the `storage` event (`applyStoredChange()` in `appearance.ts`, unit-tested). In the desktop app the key bindings window is a Tauri `WebviewWindow` of the same origin, and WebView2 runs without incognito, so the preference persists and is shared (checked by reading the Tauri config and launcher; the packaged app was not run).
- **Live checks** (Playwright, mock mode): System follows the OS light → dark → light while the app is open; an open key bindings window follows Light, Data Figures and Dark from the main window; the 3D surface, the Script editor, FanChart, DistributionChart and BarRankChart repaint on a live switch and return to their exact dark frame. The 3D surface needed the backend paused for that comparison, because Options data moves on its own. FanChart and DistributionChart were mounted in a temporary probe page, since mock mode never renders them.
- **Rendered contrast audit.** A Playwright audit walked every view and mode in both themes, the Setup dialog, the landing page, Settings and the Copilot drawer, composited each visible text over its effective background, and compared it with 4.5:1 (3:1 for large text). Disabled controls are exempt, as WCAG allows. Before the fixes: 81 texts failed in light and 28 in dark, the dark ones already present on main. They fell into three groups:
  - Text on heat-map fills: Crypto treemap tiles, the Options payoff grid's at-the-money row, the IV surface table, and (by reading the code) the strategy payoff matrix. A tone or muted colour on a strong fill cannot reach 4.5:1. New token `--heat-text` (`var(--text-0)`): that text is neutral in both themes, because the fill carries the tone and the sign the direction. Tile symbols move from `--text-2` to `--text-1`, and fitted IV cells keep italics instead of a muted colour.
  - The Script editor's syntax colours: CodeMirror's default style is made for a light background and measured 2.6–3:1 on the dark one. A `HighlightStyle` built from the tokens (comments `--text-2`, strings `--positive`, keywords `--accent`, numbers `--warning`, definitions `--text-0`) replaces it in both themes. `@codemirror/language` and `@lezer/highlight`, until now transitive, become declared dependencies.
  - Decorative separators ("|" in the Commodities provenance footer, "·" in Macro events), which WCAG exempts as decoration. They are now `aria-hidden` so screen readers skip them too.
  - These fixes change the dark theme only in those elements; the user approved fixing dark as well (2026-10-30). Before/after pairs are with the V3 handover note.

### Kept exceptions and open items

- The raw-colour gate keeps: FanChart's grid line and tooltip edge, the MaritimeMap chevron outline (all read on both backgrounds), the unused MacroCoherencePanel, and the eighth Risk cluster colour and viridis end stop (data).
- V4: the light theme keeps the terminal structure (borders, mono, uppercase labels) until the B′ values land; the default moves to System then.
- V6: the Tauri splash screen and the marketing site stay dark-only.
- `--text-3` is still referenced in two places and defined nowhere.
- Not verified by running it: the packaged desktop app (persistence and cross-window sync were checked in its configuration and code).

## V4 B′ values and fonts

V4 ran on branch `claude/v4-bprime` from local main f878592, one commit per step: 9e8f58c fold-rows guardrail script, a2e478b Instrument Sans, c6116c6 B′ token values, d355b4c B′ structure, 8a88bdc sentence-case labels, 3d43f8b chart styling and a KPI sparkline, 5103fec grey comparison series, 85ecbc9 identifier font decision, 29bf046 System default, then the gate fixes 8a30beb mode bars scroll on narrow windows, 265cfb6 Copilot shelf cards and the Portfolio picker, 106a835 rendered contrast at AA, and 5b78de3 this section. The user reviewed the screenshots and merged the branch into main as c3343b4 on 2026-11-03.

### Fonts

- Instrument Sans 400/500/600/700, latin and latin-ext `woff2` subsets from `@fontsource/instrument-sans` 5.3.0 (SIL OFL 1.1), in `frontend/public/fonts/` with `OFL.txt`, declared in `src/lib/theme/fonts.css` with `font-display: swap` and `unicode-range`. `index.html` and `keybindings.html` preload the latin regular from `/fonts/`; the build copies the files to `dist/fonts/`, which Tauri embeds.
- The `tnum` feature was checked before wiring it: with `"tnum" 1` all ten digits advance 0.6em in every weight; the default figures are proportional (55–59px spread at 200px). The body keeps `tabular-nums` and adds `"tnum" 1`.
- Roles: `--font-ui`, `--font-label` and `--font-num` are Instrument Sans; `--font-code` stays monospace. The document default is `--font-ui`. Data surfaces name `--font-num`: table cells (`td`), stat and header-KPI values, `.num`, and the figure slots outside tables in fifteen components. With Data Figures set to a monospace every figure turns monospace and labels, titles and prose stay in the interface font; with the default only code is monospace.
- Data Figures offers "Instrument Sans (default)" plus the five monospaces; stored choices stay valid.
- **Identifier font (V4 gate, decided 2026-11-03): Instrument Sans.** Tickers, contract codes, option symbols and ISO dates were compared at 12px in Instrument Sans and Cascadia Mono on Commodities curve nodes and spreads, the Options chain, Sitrep and the Fundamentals DCF harness, in both themes. The user kept the sans; there is no `--font-id`.
- Canvas charts: lightweight-charts labels use `--font-num` with proportional figures. The crosshair price label does not jitter (its box spans the price axis and the text starts at a fixed x), so `--font-code` was not needed. The Surface3D canvas keeps its own monospace labels (V6).

### Token values

Both theme blocks follow the B′ table above; the dot grid and `--canvas-dot` are gone. Deviations:

| Role | Theme | B′ | V4 | Why |
|---|---|---|---|---|
| Text 2 | light | `#697485` | `#636e7f` | 4.5:1 on the tint (V3) |
| Text 2 | dark | `#808b99` | `#8a95a3` | 4.5:1 on the 14% selection fill (B′ measured 4.03:1) and the hover fill; found by the rendered audit |
| Positive / negative / warning | light | `#0f7b52` / `#c4372c` / `#986000` | `#0c7049` / `#b83329` / `#8a5a00` | 4.5:1 on their 13% fills (V3) |
| Chart secondary | light / dark | `#b7bfcb` / `#4a5462` | `#868f9c` / `#626c7b` | B′ greys measure 1.8:1 and 2.3:1 on the sheet; nearest greys at 3:1 (3.3:1), user decision 2026-11-03 |
| Semantic soft fills | dark | 13–14% | 14% | top of the B′ range |
| Selection (`--active-bg`) | both | = accent soft | 9% / 14% | equals accent soft |
| Focus ring | dark | — | solid accent | 3:1 on the sheet and the tint |
| `--negative-muted` | dark | — | `#dc7465` | kept role, a shade under `--negative` |
| Categorical and intensity | both | — | cat-1..4, hot, warm, cold follow accent, semantic and text-2 | not in B′ |

- JS-read tokens stay literal; gradient and animation colours stay literals or `rgba(var(--accent-rgb), α)`; `--accent-rgb` is `125, 157, 242` in dark.
- 58 inline soft mixes in views moved to `--hover-bg`, `--active-bg` and the `--*-soft` tokens (chips, badges, pills, highlighted and overridden cells). Graded heat-map strengths stay inline because they encode magnitude.
- The Copilot card and Setup backdrops use `--scrim`. The two `--text-3` uses point at `--text-2`; the token stays undefined on purpose.
- New shape tokens: `--radius-control` 5px, `--panel-radius` 6px, `--overlay-radius` 12px, `--radius-pill`, `--panel-border-width: 0px`, `--overlay-shadow`; two type steps between the ramp's: `--text-title` 12.5px and `--text-kpi` 14px.

### Structure

- Panels are borderless sheets; the top bar sits on the canvas with tinted controls (as in the exploration mock).
- Tables: 28px rows, cells 10px apart and 12px in at the outer columns, a tinted header band without a rule (sticky headers keep it), no zebra.
- KPI blocks: header KPIs and the Options, Portfolio, Commodities and Crypto strips are tinted blocks (6px radius, 6px gap, 14px values); inline stats lose their rules.
- Tags are pills with a dot toned by `--tg` and filled from the soft tokens (`--tg-fill`); the Crypto, Prediction Markets, Portfolio and Equity Research chips follow.
- The shared `ProvenanceBadge` is the soft pill: `● Sample · mock · 22:58 · 2 warnings`; the dot variant keeps the compact `!2`.
- Mode bars and a new `.segmented` track (Copilot roles in chat and shelf, Prediction Markets and Portfolio pickers): a tinted track, the selected segment on the sheet with a 1px outline at weight 600, same height as before.
- `.btn` and `.form-control` have no edge (accent line on hover, ring on focus). Fields take the tint; buttons take `--button-bg`, one tonal step above it (the text colour at 8%: 1.18:1 on the sheet in light, 1.23:1 in dark); ghost buttons, including the top bar's Change View and Settings, take the tint with quieter text; primary stays an accent tint, never a solid fill. Two tonal steps were the user's choice on 2026-11-03, after the first V4 merge left ghost buttons with neither fill nor edge (1:1, readable only as text); `contrast.test.ts` keeps both fills visible on the sheet and the canvas.
- Overlays float with 12px corners and the overlay shadow: the drawer (248px, pinning and drag reordering unchanged) and the Copilot shelf 8px from the window edges, tooltips, menus, the tab search, Settings, Setup, the landing card, the chart settings popover, the treemap tooltip. Modal overlays dim with `--scrim`.
- The Copilot chat chrome converges with the shelf (the V1 exception is closed): tinted controls, segmented roles, 12px composers, no header or composer rules.

### Labels

- `--label-case: none`. Labels are sentence case, 11px, weight 500, no letter-spacing; view titles `--text-md` at 600; panel titles 12.5px at 600 in a 30px row without a rule.
- 186 of the 192 scoped uppercase rules (51 files) moved to the token. Kept uppercase because they render identifiers or codes:

| File | Selector | Content |
|---|---|---|
| `CryptoTreemapBoard.svelte` | `.tile-symbol` | token tickers |
| `IvView.svelte` | `.payoff-heatmap th`, `.payoff-heatmap thead th` | price and tenor headers (7D … EXP) |
| `RiskView.svelte` | `.heatmap-label, .heatmap-corner` | tickers on the correlation heat map |
| `PortfolioView.svelte` | `.benchmark-field input` | benchmark ticker input |
| `PredictionMarketsView.svelte` | `.venue-label` | venue codes (PM, KL) |

- Copy written in capitals moved to sentence case: tab names (title case, they are names), provenance states, the Sitrep status line and freshness states, change-column labels, "Loading…", the Options eyebrow, Commodities statuses, the Portfolio mode label, Prediction Markets side, resolution and calibration labels, the Script bound state, the 3D fit key. Status codes stay codes in logic and are formatted where shown. Data values that arrive lower case (provider ids, curve states, categories) are data and stay as they are.

### Charts

- lightweight-charts: no grid, only the baseline (time-axis edge on `--panel-strong`); flat 9% areas; 2px primary lines. lightweight-charts has no line-cap option, so its caps are the library's.
- Comparison series in `--chart-secondary` are solid grey: the previous curve and the Crypto, Equity Research, Portfolio and Strategy Lab benchmarks. Kept dashed on purpose: Macro's comparison region (it pairs each comparison with its primary by colour) and moving averages (derived overlays).
- Options SVG charts: 2px rounded lines, flat 9% areas, the axis as the baseline. No new band fills: the existing ones (the FanChart distribution, the inventory seasonality range, the Options selected mass) encode a difference.
- Sparklines and week-over-week change: `Sparkline.svelte` and `weekOverWeekChange()` on the Commodities "Last" KPI, from the price history the workspace payload already carries. Left without, because the view's payload has no history for them: the Crypto headline KPIs (history only for the selected token), Portfolio net liquidity (local history, one point in mock), the Risk header (return points only after a compute), the curve stats (no history of the stat), and the Macro, Equity Research, Strategy Lab, Prediction Markets and Fundamentals strips. No backend change.

### Rows guardrail

Data rows fully visible above a 780px fold at 1280px, drawer closed, `frontend/scripts/measure-fold-rows.mjs` (mock mode, median of three fresh-context runs; Risk measured in the Portfolio view after Compute Core, because the Research view has no book in mock mode):

| View | Baseline (main f878592) | V4 dark | V4 light |
|---|---:|---:|---:|
| Sitrep | 23 | 25 | 25 |
| Commodities › Curves & Spreads | 6 | 6 | 6 |
| Options › Overview | 19 | 19 | 19 |
| Risk › Overview | 10 | 10 | 10 |
| **Total** | **58** | **60 (103%)** | **60 (103%)** |

The baseline is the same in both themes and was measured again on the gate day (58). Sitrep gains rows because Instrument Sans wraps market names less than the mono did; Options briefly lost three rows in the first structure pass (a stretched mode bar and a wrapping source cell in its header), fixed before the step 3 commit. The exploration mocks' 89 is not comparable: they used different sample content.

### Verification

- Every commit: `tsc --noEmit` clean, vitest green (82 files; 646 → 649 tests: Data Figures default, week-over-week change, System default and pre-paint scripts), `vite build` with only the four warnings main has (IvView svg a11y, CopilotTranscriptResult `.field p.emphasis`, two Surface3D exports). `raw-colors.test.ts` and `contrast.test.ts` pass; the contrast test also checks secondary text on the hover and selection fills and text on the canvas.
- Rendered contrast audit (`contrast-audit.cjs`, every view and mode, Setup, landing, Settings, the Copilot drawer): 0 failing texts in dark and in light after 106a835 (20 and 169 before it).
- Visual review: all 13 views in dark and light, every mode at 1440×900 and the default mode at 1000 and 390px, plus the Copilot drawer, the Sealanes shelf, the navigation drawer, Settings, Setup, the landing page and the e2e harnesses; contact sheets and before/after pairs against main f878592 captured the same day. At 1000px only Crypto scrolls sideways, as before (1027 → 1016px). At 390px V4 made Options' mode bar push the page to 556px (before, the bar clipped its last modes); 8a30beb lets mode bars scroll within their width.
- Narrow-width problems that predate V4 (not fixed here): at 390px Macro (629px before, 662 after) and Fundamentals (527 → 551) are wider than the window because their header rows and context bars do not wrap; Equity Research's control group overhangs by 4px; Commodities keeps its two columns at 390px, so the curve legend sits over the price axis and the market select covers the "Commodity Matrix" title; Fundamentals › Peers clips its "Save Basket" button at 1440. Crypto no longer overflows at 390px (400px before).
- Theme switch without reload (`theme-switch.cjs`, `live-checks.cjs`): Commodities' chart and the Sealanes map repaint dark → light → dark with no page error; System follows the OS light → dark → light; an open key bindings window follows Light, Data Figures and Dark; the Script editor repaints and returns. The 3D surface repaints and returns to its exact dark frame with the data frozen (API requests aborted after load: 0 channel values differ, 0 in a no-switch control, 33,534 in light). The Risk charts are not rendered in the Research view in mock mode, as in V3.
- Fonts offline: Playwright against `vite preview` with every non-local request aborted: Instrument Sans 400/500/600/700 loaded from `/fonts/` on the preview origin, no request to a font CDN; the only blocked request was the Bloomberg TV stream.
- Packaged desktop build: the release shell was built with `tauri build --no-bundle` (Rust 1.94; the frontend is embedded in `gamma-shell.exe`) and run with the repository backend (`GAMMA_REPO_ROOT`) in mock mode, a throwaway WebView2 profile and app-data folder, and WebView2 remote debugging. Over CDP the main window loaded Instrument Sans 400/500/600/700 from `http://tauri.localhost/fonts/` with no external request, and again after a reload with the network emulated offline (`Network.emulateNetworkConditions`). Not done: the PyInstaller backend and the NSIS installer were not built, nothing was installed, and the machine's network was not switched off.

### Kept exceptions and open items

- Raw-colour gate: unchanged since V3 (FanChart grid line and tooltip edge, the MaritimeMap chevron outline, the unused MacroCoherencePanel, the eighth Risk cluster colour and the viridis end stop).
- Uppercase: the six identifier rules in the table above.
- Dashed lines: Macro's comparison region and the hero chart's moving averages.
- Boxes kept on purpose: the accent edge of primary buttons, the 1px line of floating overlays, the Commodities band boxes (they encode a range), the MaritimeMap HUD, legend and controls (V6, map style), the Script editor frame (V6), the landing card's readout grid.
- Not themed (V6): the Tauri splash screen, the Sealanes map style, the marketing site. Surface3D canvas labels keep their monospace (V6).
- `--text-3` is gone from the code; the token was never defined and is not added.
- V5: `design_principles.md` and the gamma-ui and gamma-charts skills still describe the terminal look (closed by V5, below).

## V5 doctrine and skills

V5 ran on branch `claude/v5-doctrine` from local main ab6467c, one commit per step: 9f6f504 the doctrine rewrite, 0c29a3f token and primitive comments, 48211a3 `PRODUCT.md` and the docs index, then this section. The gamma-ui and gamma-charts skills live outside the repository and were rewritten in place after a backup (kept with the V5 handover note). The doctrine steps changed no app code; afterwards, at the user's request, one copy change renamed the brand subtitle in the top bar (`Shell.svelte`) and on the landing card (`LandingPage.svelte`) from "Research Terminal" to "Research Workspace", the wording the README already uses, and a second one did the same on the marketing site (below): 7b36ac3 and 694bb07. The user merged the branch into main as 9192e29 on 2026-11-04.

### What changed per section

`design_principles.md` was rewritten in place following the rewrite map below. Its 46 headings are identical line for line, and the ten named rules (Data-First, One-Plane, Earned-Density, Quiet-Chrome, Two-Type, Color-Has-A-Job, Primary-Path, Table-Owns-The-Panel, Provenance-On-Demand, Stable-Geometry) and the six review tests keep their names. Values are named by token, never by hex.

| § | Change |
|---|---|
| Opening | The lineage is the scientific instrument and the well-set statistical table instead of a trading terminal; identity is one plane of tonal sheets, one interface typeface with tabular figures, and two themes. "Not a terminal imitation, a generic SaaS dashboard, or a data-visualization showcase" stays. |
| §1 | `primitives.css` joins the source order as the implementation of §8; `contrast.test.ts` and `raw-colors.test.ts` are named as the token gates; this plan is named as the record of decisions. |
| §2 | One-Plane Rule: one plane of tonal sheets separated by consistent seams; regions never float; only transient overlays leave the plane. Hierarchy must hold in either theme. |
| §3 | Color roles rebuilt around canvas, sheet, tint, button fill, lines, soft fills, overlay, `--heat-text` and `--cat-*`; `--accent-2` is the context gold. A Themes paragraph (System default, AA in both blocks, canvas repaint on `resolvedTheme`). Four font roles; the Two-Type Rule now reads "sans explains the instrument; tabular figures carry the research; mono is for code"; a Labels paragraph; the type scale gains `--text-title` and `--text-kpi` and new roles; radius is controls 5px, sheets 6px, overlays 12px, pills for tags only. |
| §4 | Cool temperature in both themes; no ambient texture; flat area fills and difference bands as data encoding; the one-colour gradient that layers a soft fill over the sheet; literal gradient stops. |
| §5 | Hierarchy by tonal steps; the Surface Contracts table covers sheet, tinted block, transparent chart shell, table, input, button, mode bar, inset and floating overlay. No border around sheets, cards, KPI blocks, fields or buttons; no transparent action button. |
| §6 | `.workspace-grid` named; mode bars scroll sideways on narrow windows. |
| §7 | Mode bars are a tinted track with the selected segment on the sheet; role toggles use `.segmented`. |
| §8 | Panels: borderless `.panel`, `.is-flush`, the 30px `.panel-title`, `.header-panel`. KPI strips: tinted blocks on one baseline, rule-less `.stat`, sparklines only from payload history. Tables: label headers on a tinted band, `--font-num` cells, 28px rows, ruled, no zebra; the sheet's edge contains a flush table. Charts: transparent ground, no grid, baseline, 2px primary with a flat 9% area, the grey reserved for comparison, two dashed exceptions, difference bands, canvas figures, repaint on theme change. Controls: fills, accent-tint primary, red-edged danger, never solid, green or red. Tags: pill with a dot toned by `--tg`; the provenance pill. Cards: tinted, borderless. |
| §9 | Writing is sentence case; tab names are title case; status codes are formatted where shown. |
| §10 | `Loading…` and `Chart unavailable`; the focus ring token; the Copilot shelf is a floating overlay. |
| §11 | Floating overlays as the elevation exception (12px, shadow, line, scrim on the drawer, the Copilot shelf and Setup; drawer and shelf 8px in); the identifier codes; the dashed series; the lines that stay; surfaces not yet restyled. |
| §12 | Plane, Hierarchy and Access tests ask for tonal sheets, tabular figures and AA in both themes; the Drift Scan is rewritten for B′. |
| §13 | Primitives in item 5; both themes in item 10. |
| §14 | Rows rewritten for B′ and new rows (listed below). |
| §15 | Plane, Panel background, Radius, Elevation, Type, Controls, Tables, Charts and Copy rows updated; a Themes row added. |

Also updated: `tokens.css` and `primitives.css` comments (type-scale roles, the 6px step without "terminal-density", `--accent-2`, the value flash, the primitives header, the `.mono` column); `PRODUCT.md` (doctrine summary, no pre-V2 hex values) and the `docs/README.md` descriptions.

### Rules added from V4

- Labels are sentence case, 11px, weight 500, no letter-spacing. Upper case only for the six identifier rules of the V4 Labels table, which keep their own slight tracking.
- Identifiers and ISO dates use `--font-num` (Instrument Sans, tabular figures); there is no `--font-id`.
- Action buttons are never transparent: `.btn` on `--button-bg`, ghosts on `--tint`, primary an accent tint, never a solid, green or red fill. Navigation rows, menu items, list rows and text links are not action buttons.
- Comparison series are solid `--chart-secondary` (3:1), and that grey is reserved for comparison: a lone series takes `--chart-primary` and categorical series `--cat-*` (user decision, 2026-11-03). Dashes only for Macro's comparison region and derived overlays; the Risk benchmark's dash is drift (user decision, 2026-11-03).
- No zebra striping; the Macro Rates stripe kept in V1 is drift (user decision, 2026-11-03).
- Bands only when they encode a difference; sparklines only where the payload already carries the history.
- Floating overlays (12px, overlay shadow, scrim behind modal ones) are the only elevation; System is the default theme; AA in both themes.
- KPI strips are tinted blocks on one baseline, replacing "one grid with gap 0 and internal dividers".
- New §14 rows: a border around a sheet, card, block, field or button; a transparent ghost button; a solid, green or red button; `--accent-2` as a series colour; `--chart-secondary` on a lone or categorical series; uppercase or letter-spaced labels; copy written in capitals; a sparkline from too few points or from history fetched only to draw it; zebra striping, chart grid lines or a fading area gradient; a band that encodes no difference.

### Drift-scan findings for V6

The new §12 Drift Scan was run against the code as a review (a rule-level scan of every `.svelte` style block and `primitives.css`, then each hit read and classified). Nothing was fixed in V5. File and line references are in the V5 handover note.

1. Bordered cards and boxes: Macro Cross-Asset theme cards and divergence cards, the key bindings window cards, Diagnostics, the view load state, the Setup dialog's notice, mode and facts boxes, the Equity Research signed book, the Fundamentals decision gate, the view error boundary, the FanChart shell, the AllocationDonut empty state.
2. Bordered `.table-wrap` inside a sheet: Strategy Lab and the parameter sweep.
3. Copilot surfaces not converged: transcript blocks, chips and confirmations, the artifacts panel, chat session and storage controls, run states, the composer field, the shelf's context trigger, the run inspector, the Strategy Lab working analysis.
4. Script surfaces (with the Script editor): workspace status, output and candidate cards, parameter sweep boxes, analytical results.
5. Edged controls and chips outside the primitives: the hero chart settings button, the landing button, a scoped `.btn` override in the research scope analysis, Risk dependency controls, the Equity Research tooltip chip, the Commodities loading pill, the Fundamentals dirty pill, a bordered status tag in the Copilot options analysis; the Sitrep tape controls (a V1 exception).
6. KPI strips with internal dividers: the Crypto, Macro and Fundamentals headline strips, `MacroMetricRow`, the parameter sweep KPIs, the Sitrep tape strip, the Copilot working analyses.
7. Overlays off the overlay tokens: both Copilot context menus (own shadow, no 12px radius), the Commodities scatter tooltip, the Risk dependency and frontier tooltips, the AllocationDonut tooltip, the Portfolio confirm dialog.
8. Radius off the scale: raw `999px` and 2px badges in Macro, chat bubble radii, `--radius-sm` on controls (Copilot artifacts, transcript confirmations, drawer buttons, the compact context menu); the 3px heat tiles match this plan's "3px radius" for heat cells but have no token.
9. Copy in capitals: "CHART UNAVAILABLE" (hero chart default, Commodities), "NO CURVE NODES", "NO HISTORY", "LOADING COMMODITIES", "LOADING 3D SURFACE...", the Portfolio chart messages, Prediction Markets "LOADING...", the Sitrep equity tape state and Bloomberg TV states, Copilot "OPERATOR RUN/PLAN", "IMAGE ARTIFACT", the fingerprint "UNAVAILABLE". Sitrep's state codes are already formatted.
10. Zebra: Macro Rates.
11. Charts: grid lines in FanChart, the Commodities scatter and the Risk frontier; the dashed Risk benchmark; `--chart-secondary` on lone series (Risk Rolling Beta, Strategy Lab Rolling Corr, Macro FX pair 2, the Prediction Markets spread), in categorical palettes (Portfolio allocation, Prediction Markets comparison, Commodities inventory groups and scatter, Macro rate and inflation series) and as the Options selected-mass highlight; Macro FX pair 3 as a lone series in `--chart-negative`.
12. Fonts: seven `var(--font-num), monospace` stacks that restate the old intent; the key bindings window's body on `--font-num` instead of `--font-ui`.
13. Local copies of the panel primitives: `.table-panel { padding: 0 }` in ten files instead of `.panel.is-flush`; `.table-panel-header` at 26px with a rule in Macro Country Compare and Trade Partners instead of the 30px `.panel-title` without one.
14. Icon-only close buttons in the drawer and the Copilot shelf are transparent icons; acceptable as icons, worth a look.

Clean: no off-ramp font size, no solid, green or red button fill, uppercase only in the six identifier rules, blur only on the drawer scrim and an overlay, and the canvas components repaint on a theme change.

### Skills changed outside the repository

- `gamma-ui` (`~/.claude/skills/gamma-ui/SKILL.md`): the description drops "more like a professional trading terminal" and keeps the density, polish and audit triggers (adds light/dark checks and drift scans). The body teaches the B′ plane model, the radius scale, filled buttons, sentence-case labels, font roles, KPI blocks, the flush table panel with `.panel-title`, the provenance pill, the current file map, and §3, §5, §8, §11, §12, §14 and §15 by number.
- `gamma-charts` (`~/.claude/skills/gamma-charts/skill.md`): "Apply Gamma's terminal design philosophy" becomes "Apply Gamma's B′ chart doctrine"; the body teaches the transparent ground, no grid, the baseline, the flat 9% area, the reserved comparison grey, bands only for a difference, payload-only sparklines and both themes, and drops the retired chart themes and every hex value. It cites §3, §4, §8 (→ Charts), §9, §14 and §15.
- Both keep their scope split (gamma-ui: panels, tables, controls, text density; gamma-charts: chart internals). Every `§N (Name)` they cite lands on that heading, their YAML frontmatter parses, and every token and path they name exists.
- `gamma-usability-audit`: its hand-off to the two skills, "which own `docs/design_principles.md`", still holds. At the user's request it now calls Gamma a "research workspace", its report template asks for tight, technical prose, and the score row "Visual density & terminal feel" became "Visual density & design consistency", with a note to take the Δ from the old row.

### Verification

- Comment-only CSS: the comment-stripped sources are identical, and `vite build` before and after produced sha256-identical output (22 CSS files, all 72 dist files).
- Gate on the branch: `tsc --noEmit` clean, vitest 82 files / 651 tests, `vite build` with only the four known warnings; token and path checks pass for the doctrine and both skills; "Bloomberg" appears nowhere in the doctrine, the skills, `PRODUCT.md`, the docs index or the theme CSS, and "terminal" only in the "not a terminal imitation" line.
- Ten doctrine claims were checked against the code with file and line evidence (borderless panels, document-wide tabular figures, `--label-case`, the header band, the button fills, the chart grid and baseline, the flat area, KPI blocks, overlays and scrim, the System default); all hold.
- The doctrine steps changed no rendered pixel, which the identical build output proves. The later copy change was checked in the browser without a backend: the top bar reads "Gamma · Research Workspace" on one line at 1024px and at 375px with no sideways scroll, and the landing card shows the same subtitle; typecheck, tests and build were unchanged (82 files / 651 tests, the four known warnings).

### Left for V6

- The drift-scan findings above.
- `website/DESIGN.md` and `website/.impeccable/design.json` still inherit the old doctrine verbatim (the old Two-Type Rule, "Terminal Ground", uppercase tracked mono labels, the pre-V2 colours).
- The marketing site's wording was changed with the app's, at the user's request: "Research Workspace" under the wordmark of all four pages, "a read-only market research workspace" in the index title, meta description, Open Graph title and every page footer, and the same words in `website/DESIGN.md` (description) and `website/.impeccable/design.json` (the topbar sample). Below 860px the site's nav is a sideways-scrolling strip by design; the longer subtitle makes it start scrolling at 724px instead of 710px, and the subtitle still hides below 620px. Left for V6: the thirteen app screenshots in `website/assets/img/screens/` predate B′ and still show "Research Terminal" and the old look, and the rest of `DESIGN.md` and `design.json` (the "Terminal Ground" colour, the old Two-Type Rule, "not a page about a terminal").

## V6 hardening

V6 ran on branch `claude/v6-hardening` from main 4b60e16, one commit per step: 5bf2ffb V6a primitives, c134206 V6b copy and charts, 6d943d1 V6c special surfaces, fe13f68 V6d narrow widths, then the gate (5294bfa visual baselines and two contrast fixes, 87333e4 the last two narrow overflows), four fixes found in the live audit session (0697257, 499642c, e70d6e4, d296f6f), the website (369e51c) and this section. Step 0 re-ran the V5 drift scan: the same 310 lines, only a `primitives.css` line moved by V5's comments, so every V5 finding was still at its V5 line.

### Decisions before step 1 (2026-11-04)

| Question | Decision |
|---|---|
| Screenshot baselines | The website screenshots **and** a small Playwright visual baseline for fixture-driven e2e harness pages, both themes (`frontend/e2e/visual.spec.ts`) |
| Website scope | Move the site to B′: tokens for both themes following the OS, Instrument Sans, sentence-case labels, borderless sheets, screenshots in both themes |
| Sealanes base map | Keep recolouring the CARTO style from tokens, with per-theme map tokens; the light theme turns the land and water roles over (sheet C of the decision sheets); dark unchanged |
| 3px heat tiles | The user leaned to square or a very small radius and left it to the implementer: `--radius-sm` (2px), the existing inner-mark token |
| MacroCoherencePanel | Revive it, in the four Cross-Asset theme cards only (a follow-up answer after seeing it mounted) |

### Per drift-scan group

| # | Group | Outcome |
|---|---|---|
| 1 | Bordered cards and boxes | Fixed: tinted blocks on the sheet or sheets on the canvas, no border, `--panel-radius` (Macro theme and divergence cards, key bindings window, Diagnostics, view load and error states, Setup notice, modes and facts, Equity signed book, Fundamentals decision gate, FanChart shell, AllocationDonut empty state) |
| 2 | Bordered `.table-wrap` | Fixed (Strategy Lab, parameter sweep) |
| 3 | Copilot surfaces | Fixed: transcript blocks, notices, event rows and result states are tinted blocks (confirmations and degraded states on `--warning-soft`, no coloured edges), chips are pills, the confirm action is the accent tint; artifacts panel, run inspector, Strategy Lab working analysis, session rename, run tools, storage badge, actions and details, the composer and the session confirm dialog converge |
| 4 | Script surfaces | Fixed: the editor is a tinted inset (frame and CodeMirror ground on `--tint`, rule-only gutter, accent focus line); status chips are pills; state boxes, output and candidate cards, sweep evaluation and reference, the analytical book and the comparison table lose their edges |
| 5 | Edged controls and chips | Fixed: landing choices and the hero chart settings button take the button fills; the scoped `.btn` copy in the scope analysis is deleted; Risk dependency zoom is a tinted track; status pills in six views, the DCF dirty pill and the Copilot options status become `.tag`; the Equity treemap tooltip chip is a pill; Sitrep reload buttons, note editor and news chips converge |
| 6 | KPI strips with dividers | Fixed: Crypto, Macro and Fundamentals headline strips moved to `.header-kpis`/`.header-kpi` (values 14px, were 12px); `MacroMetricRow`, the sweep KPIs, the Copilot working analyses, the Fundamentals DCF terminal framing and the Sitrep tape strip lose their dividers |
| 7 | Overlays off the tokens | Fixed: both Copilot context menus, the Commodities scatter, Risk dependency and frontier and allocation tooltips, the Portfolio and Copilot confirm dialogs (`--scrim`), the Surface3D settings popover and the Sealanes shelf, drawer, replay panel, notice and popup |
| 8 | Radius off the scale | Fixed: Macro pills, chat bubbles on `--panel-radius` with a `--radius-sm` tail corner, `--radius-control` on controls; heat tiles `--radius-sm` (decision) |
| 9 | Copy in capitals | Fixed: every capitalised state and label (list in the V6 handover), and visible "..." became "…"; tests that asserted the old copy follow. Kept: Sitrep state codes, which are codes in logic and formatted where shown |
| 10 | Zebra | Fixed: Macro Rates stripe removed |
| 11 | Charts | Fixed: no grid in FanChart, the Commodities scatter or the Risk frontier; the Risk benchmark is solid; lone series on `--chart-primary` (Risk Rolling Beta, Equity Research price and rolling beta/corr, Macro FX pairs 2 and 3, the PM spread); categories on `--cat-*` (Strategy Lab Rolling Corr, Macro rate and inflation pairs, Commodities inventory series and metals, Portfolio allocation, PM comparison, Risk clusters); the Options selected mass a stronger primary fill; VaR and ES markers warning and negative in both distributions |
| 12 | Font stacks | Fixed: no `var(--font-num), monospace`; the key bindings body on `--font-ui`; Surface3D canvas labels on `--font-num` |
| 13 | Local panel copies | Fixed: 103 panel class attributes opt into `.panel.is-flush`; Equity Research, Strategy Lab and the Macro Country Compare and Trade Partners table titles are `.panel-title` (a new primitive rule lets an `<h2>`–`<h4>` keep the row's type). Kept: Fundamentals finds about 20 table panels by structure (`:has()`), because their headers carry an eyebrow, a title and controls; they get the flush geometry and the 30px rule-less header row |
| 14 | Transparent close buttons | Fixed: the drawer header and close buttons and the Copilot shelf close button sit on `--tint`; the top bar's Copilot trigger on `--accent-soft` |

The V6 row's surfaces: the Sitrep stream (Bloomberg TV states sentence case, tape controls, strip), the Sealanes map style and chrome, Surface3D labels and controls, the Script editor frame and cards, the Copilot run inspector and chrome, the drawer and shelf close buttons, and the Tauri splash, which now loads `tokens.css`, applies the stored theme before first paint and draws the accent Γ mark.

### Narrow widths (V6d)

| Problem (V4 list + step 0) | Cause | Fix |
|---|---|---|
| Macro 662px, Fundamentals 551px at 390 | `.header-panel` was a grid with an implicit `auto` column whose minimum came from the mode bar's min-content width (every mode on one line) | `.header-panel { grid-template-columns: minmax(0, 1fr) }` in primitives.css: the mode bar scrolls within the window, as 8a30beb intended |
| Equity Research 394px | the three overview pickers in one non-wrapping group | they share the row at ≤980px |
| Crypto › Deep Dive 417px (found in step 0) | `.detail-split.basket-empty` outranked the ≤1180px one-column rule | listed in that rule |
| Fundamentals › Peers 1449/1009px | the ticker field's 18rem minimum in a non-wrapping row | the field shrinks, the row wraps |
| Commodities two columns at 390 | `.overview-top` had no narrow rule, and `grid-column: 1 / span 4` added implicit columns at ≤1200px | `1 / -1`; one column at ≤720px with own heights for the chart and scatter; the pre-B′ narrow mode-bar grid and divider rules removed |

Side effect at 1000px: the Commodities span-2 panels take the full width as the ≤1200px rule intended (they had shared a row through the implicit columns).

### Kept exceptions

Everything the final drift scan still reports, and why (also in design_principles.md §11):

- Overlay lines: tooltips, menus, popovers, dialogs, the drawer, the Copilot shelf and the Sealanes shelf, drawer, replay panel, notice and popup keep the 1px `--panel-border` line of floating overlays.
- Boxes and marks that encode data: Commodities band boxes and markers, the gauge marker, the Surface3D and Risk colour-scale tracks, legend swatches, the Sealanes chokepoint ring and the lane swatch's glow (it mirrors how the lane is drawn), the Fundamentals range tick.
- Control glyphs: the checkbox edges in the Copilot context menus.
- The landing card (a gateway overlay), its brand tile and readout grid; the primary-style accent edge on the top bar's Copilot trigger.
- Table structure: the full grid of Copilot rich tables (`.is-grid`), the Commodities sector rule and the Options chain strike column rules; the top bar's zone separator.
- Transparent controls that are not action buttons: menu items, list rows, navigation rows, text links, the tooltip trigger, the asset chip's clear icon, the Commodities market cards (V1), segments inside the Risk dependency track, and the Sitrep follow-up pins (dense per-row icon toggles).
- Dashes: Macro's comparison region and the reference marks (distribution markers, FanChart start value, split and hover lines, Options ATM and guide lines, Risk CML and zero line, the hidden universe frontier) and negative dependency edges (data).
- `--chart-secondary` on comparison only: benchmarks, the previous curve, run comparison, realized vs predicted, the current book on the frontier.
- Surface3D keeps its reference planes (they carry the depth cue).
- Gradients that encode uncertainty (the FanChart bands); blur on the drawer scrim and the treemap tooltip.
- Raw-colour gate: two literals left, the MaritimeMap chevron outline (canvas, read on both maps) and the viridis end stop (data). Removed in V6: the FanChart grid line and tooltip edge, MacroCoherencePanel, the eighth Risk cluster colour.

### Verification

- Drift scan on the final branch: box-border 35, dashed 18, transparent-button 10, chart-secondary-use 11, font 8 (all `--font-code`), uppercase 7 and letter-spacing 5 (code labels: crypto tile symbols, venue codes, the payoff and correlation heat-map headers, the benchmark ticker field; the provenance dot's first letter), side-divider 4, svg-gradient 3 (the FanChart bands), radius-inner-token-on-container 2, blur 2, shadow 1 (the lane legend glow), radius 1 (the Fundamentals range tick) and caps-copy 3 (Sitrep state codes in logic). Every hit is one of the kept exceptions above.
- `tsc --noEmit` 0 errors; vitest 82 files, 654 tests; `vite build` with only the four known warnings (IvView a11y, an unused CopilotTranscriptResult selector, two unused Surface3D exports); `raw-colors.test.ts` and `contrast.test.ts` pass.
- Rendered contrast audit (every text over its real background): 0 failures in light and in dark, after two fixes in 5294bfa (the landing choices' secondary line, and the Macro score pills inside tinted cards, which now paint their soft fill over the sheet).
- Rows above the 780px fold (`measure-fold-rows.mjs`): 74 in each theme on the branch. Main, re-measured the same night with the same keyed backend, also has 74; the step-0 figure of 60 was taken without the FRED keys. The V4 guardrail is 58.
- Theme switch without reload, dark → light → dark: the Commodities chart, the Sealanes map, the 3D surface (with data frozen: 0 changed pixels against the dark control, 33,609 in light, 0 back in dark) and the Script editor repaint, with no page errors.
- Width: after 87333e4 every view and mode fits the window at 1440, 1000 and 390 in both themes; what still extends is clipped inside a scrolling mode bar or a treemap tile.
- Visual baselines: `frontend/e2e/visual.spec.ts`, six fixture harness pages in both themes, stable over two reruns.
- Before and after: 168 pairs per theme (52 screens at each of 1440, 1000 and 390, plus 6 special surfaces and 6 harness pages) and contact sheets of both sets, kept with the V6 handover note.

### Live usability audit

Report: [`audits/usability/gamma_usability_findings_2026-11-05.md`](./audits/usability/gamma_usability_findings_2026-11-05.md) (account masked). It ran on 2026-11-05 with TWS connected (a second backend port, IB client id 17, `check-live-ibkr.ps1` exit 0) in two blocks, 03:07–03:17 and 14:03–14:40, after TWS had closed during a pause. It was driven headless because the Browser pane was hidden, and both blocks were outside US market hours. The visual pass covered the twelve Research tabs in both themes. Portfolio and the account's Risk were left out so that no account data was captured.

**Acceptance: no new P0 or P1 visual finding.** Every visual defect found was P2 and is fixed. Scores against 2026-10-27: visual density and design consistency 8/10 (+1), Copilot 6 (−1), cross-tab 6 (−1), overall 6 (−1). The thesis (December versus January Fed pricing) was partially confirmed. Its decisive test needs a meeting-dated futures curve that Gamma does not expose.

Found and fixed on the branch:

- Sitrep › Rates: the Prior column repeated the current value on the policy rows ("Fed Funds 3.88% +0.25 pp, prior 3.88%"; now 3.63%, and 47 bps for 2s10s), with a "Feds Funds" typo (0697257).
- Three Sitrep empty states were still in capitals, missed by V6b (0697257).
- The Commodities momentum/roll scatter stretched a 360×110 viewBox, which distorted every label and clipped the vertical title; main has the same defect (499642c).
- Risk › Largest Movers toned flat rows (cash at 0 P&L) as gains (e70d6e4).
- The Macro FX charts read "Loading FX data" for good when the IBKR history comes back empty (d296f6f).

Found as backend defects and, with the user's go-ahead, fixed the same day (5f01681, e94fe62):

- P1 (GUA-20261105-1): a Copilot run with Prediction Markets in its context hangs at "Plan / Stop". The context builder calls the wallet summary, Polymarket's trades endpoint answers 410 Gone, and the agent thread catches only `ValueError`, so it dies without a failed event.
- P1 (GUA-20261105-2): Macro › Rates & Policy reads "Market bias Easier, avg probability 67%" and "diverging" from three resolved Polymarket contracts (the December 2025 and January 2026 FOMC cut markets), although the service asks the screener for open markets. The open December 2026 contract priced a 25 bp hike at 78%. The same read feeds Sitrep's What Changed.
- P2 (GUA-20261105-4): the Polymarket wallet summary returns 500 on the same 410. Polymarket had retired Data API v1; the summary now reads v2 and degrades to a warning.

Also open, frontend, from the report: the contract page keeps an old detail after a screener Refresh (GUA-20261105-5), the Meeting Ladder allocates the whole 2Y gap to two meetings (GUA-20261105-6), and Copilot's Sitrep context seems to omit the Rates table (GUA-20261105-7).

### Website

369e51c moves the site to B′ (scope b: both themes following the OS, Instrument Sans, sentence case, no textures) and replaces every capture. The 13 screens were taken headless at 1920×1200, DPR 1, each in both themes, and are served through `<picture>` by the visitor's colour scheme. The user reviewed and approved every image.

- Live, public providers with no broker connected: Macro (FRED, Treasury), Prediction Markets (Polymarket, Kalshi), Sealanes (AISstream; vessels draw from zoom 4) and Crypto (CoinGecko).
- Demo mode: Sitrep, Commodities, Options, Risk, Copilot, Portfolio, Equity Research, Strategy Lab and Fundamentals, so no account, position, balance or P&L of the user's appears. Sitrep and Fundamentals still read public rates and SEC filings.
- The worktree cache still held IBKR FX and futures data from the live audit session, and both backends served it. It was quarantined, and the Sitrep and Macro captures were retaken and approved again before the commit.
- Badges: Live on Macro, Prediction Markets and Sealanes; Mock on the other six figures. The "mock mode" sentence and the footer say which screens are live; the Risk caption reads "Portfolio · Risk · Overview"; alt texts and markers match the captures.
- Not verified, for the user before publishing: whether the ICE BofA high-yield OAS that FRED serves may be reproduced, and CoinGecko's attribution terms for its free API.

### Left after V6

- The three frontend findings from the report, and the contract status in the Copilot context (GUA-20261105-2).
- Options in session: both audit blocks were outside US market hours.
- Risk's simple tables tone whole rows, so identifiers and rule text take the signal colour; the MC VaR and ES labels overlap in the terminal distribution.
- Equity Research and Strategy Lab show little in demo mode (an N/A treemap, an empty composer result), so their site captures are thin; the page does not use them.

## Doctrine rewrite map (V5)

Edit sections in place and keep the numbering and the rule names. Skills and reviews cite `§14`/`§15` and named rules.

- **Opening (lines 5–7):** replace the "Bloomberg Terminal's information density with Linear's spatial discipline" lineage with a research-instrument lineage that does not reference trading terminals. Keep "not a terminal imitation, a generic SaaS dashboard, or a data-visualization showcase".
- **§2 One-Plane Rule:** "one instrument panel divided by seams" becomes "one plane of tonal sheets separated by consistent seams; regions never float". The blur-your-eyes test stays.
- **§3 Foundations:**
  - Color Roles gains tint, soft semantic tokens, scrim and the light theme.
  - The Two-Type Rule keeps its name with a new meaning: sans explains the instrument, tabular figures carry the research, mono is for code.
  - The radius scale becomes controls 5px, panels 6px, overlays 12px and pills for tags only.
- **§4 Texture:** remove the dot grid; allow flat area fills and difference bands as data encoding.
- **§5 Surface contracts:** rewrite the table for borderless sheets, tinted inputs, the table header band and floating overlays. "No shadows on panels" stays.
- **§8 Component contracts:**
  - Section headers: sentence case.
  - KPI strips: tinted blocks on one baseline replace "gap 0 with internal dividers".
  - Tables: header band, no zebra.
  - Tags and provenance pill: new shapes.
  - Cards: radius, no border.
- **§10 and §11:** sentence-case stable state text ("Loading…") and the floating drawer as an overlay exception.
- **§12 Review tests:** the Hierarchy test asks for tabular figures in data instead of "mono for data"; update the Drift scan for B′.
- **§14 Common Mistakes:** edit these rows:
  - Nested bordered card becomes a tinted block inside a tinted block.
  - Radius values.
  - "Sans on numeric data" becomes "Proportional figures on numeric data, or mono on chrome".
  - Warm darks also covers light-theme temperature.
- **§15 Quick Reference:** update the Plane, Panel background, Radius, Type and Charts rows.

## Risks and guardrails

- **Not a trading app:** B′ is the most product-like direction. Keep primary actions accent-tinted and quiet, never green or red buttons, and keep provenance visible.
- **Identifier legibility:** sans figures for codes and dates at 12px are the main readability risk. The V4 gate above decides it.
- **Light theme QA roughly doubles visual review:** maps, the Sitrep stream, 3D surfaces, CodeMirror and canvas charts each need a pass.
- **Parallel work:** V1 and V2 touch scoped styles in every view and will conflict with feature work. Migrate view by view and rebase often.
- **Packaging:** include the font license and confirm the fonts ship inside the desktop bundle.
- **Marketing site:** `website/` has its own `DESIGN.md` and real mock-mode screenshots, so it diverges after V4. Decide in V6 whether to follow.

## Progress log

- 2026-10-27: exploration of directions A (Ruled), B (Tonal) and C (Grid) against today's look on Commodities and Copilot, with measured density.
- 2026-10-28: exploration extended to Sitrep, Options and Risk, plus the B′ variant and a drawer versus top-tabs comparison. The user chose B′ and kept the drawer. V1 started in a separate worktree session: commit 684312b adds the 26px panel title, an opt-in `.data-table`, `.tag` and the Macro `.tag.is-tinted`, with no visual change (18/18 screenshots and 7,486 computed-style checks identical). It was merged into main as 9151727 the same day.
- 2026-10-28: with the user's approval, V1 continues with deliberate convergences. On branch `claude/musing-easley-b0d363`, a373294 moves every data table onto `.data-table` plus modifiers and 7616ea2 folds the four gold Macro tags into `.tag.is-tinted.context`. The convergences and kept exceptions are listed above. Buttons, inputs, selects and inline stats are still open.
- 2026-10-28: the user reviewed the before/after screenshots, accepted the convergences, and merged the branch into main as 77d40e5 (not pushed).
- 2026-10-28: the controls showed no copy family like the tables did (34 components with their own base button: 7 heights and 11 paddings), so the user chose to converge them as well. e98fd26 moves buttons, inputs and selects onto `.btn` and `.form-control`, and dedc5d7 moves the inline stats onto `.stat`, on branch `claude/musing-easley-b0d363`. The convergences and exceptions are listed under "Controls and inline stats" above.
- 2026-10-28: the user reviewed the controls and stats screenshots, accepted the convergences and merged the branch into main as 7867445 (not pushed). V1 is complete; the kept exceptions carry over to V2 (`font: inherit`, raw colours) and V4 (Copilot chat chrome).
- 2026-10-28: V2 on branch `claude/v2-token-completeness` from local main 9412498: 2b3ee01 font roles, 5be065d new tokens, 600d961 raw colours onto tokens, 1b5ed86 chart colours and flashes, 32362a3 `font: inherit` on chrome buttons, bb26c40 the raw-colour gate. For step 6 the user chose to keep every input, select and textarea as it was. Steps 2–5 and 7 changed no pixel in mock mode; step 6 before/after pairs are with the V2 handover note. Decisions and kept exceptions are under [V2 token completeness and font roles](#v2-token-completeness-and-font-roles). The user reviewed the pairs, accepted the change and merged the branch into main as 9676017 (not pushed). V2 is complete.
- 2026-10-29: main pushed to origin (ffefb09..a1c74e2), so V1 and V2 are on the remote.
- 2026-10-29/30: V3 on branch `claude/v3-theme-infrastructure` from main a1c74e2: 175e419 theme preference, 8dc3dbc light token block and contrast test, 3ec377c charts, 3D surface and map repaint, 7d5430d chart theme retired and Data Figures, 1d36bd0 theme colours for the last dark-only literals. The user chose Dark as the default until V4. Dark stays pixel-identical in mock mode; light screenshots are with the V3 handover note. Not merged.
- 2026-10-30: gaps closed on the same branch after the first review: 29e0b79 keeps open windows on the same theme, and a rendered contrast audit led to 8948d0a (neutral text on heat-map fills and token syntax colours in the Script editor, in both themes with the user's approval; decorative separators aria-hidden). The audit now finds no failing text in either theme.
- 2026-10-30: the user reviewed the light screenshots and the contrast pairs and merged the branch into main as a68ed3a (not pushed). V3 is complete.
- 2026-11-02/03: V4 on branch `claude/v4-bprime` from local main f878592: 9e8f58c fold-rows guardrail (baseline 58 rows in both themes), a2e478b Instrument Sans, c6116c6 B′ token values, d355b4c B′ structure, 8a88bdc sentence-case labels, 3d43f8b chart styling and a KPI sparkline, 5103fec grey comparison series and 85ecbc9 Instrument Sans for identifiers (both user decisions on 2026-11-03), 29bf046 System default, then the gate fixes 8a30beb, 265cfb6 and 106a835. Rows above the fold: 60 in each theme. Contrast audit: 0 failures in both themes. Screenshots, pairs and the offline-font proof are with the V4 handover note. Not merged.
- 2026-11-03: the user reviewed the V4 screenshots and merged the branch into main as c3343b4 (not pushed). V4 is complete.
- 2026-11-03: main pushed to origin (a1c74e2..0aace25, V3 and V4).
- 2026-11-03: ghost buttons fixed on branch `claude/v4-ghost-buttons` from main 0aace25. A rendered audit found 39 action buttons per theme with no fill and no edge (the top bar's Change View and Settings in every view, and `.btn.is-ghost`). The user chose two tonal steps over a ghost-only tint or a hairline: `--button-bg` for buttons, the tint for ghosts. After the fix no action button is without a boundary. Not merged.
- 2026-11-03: the user merged the button fix into main as b10e48c (not pushed).
- 2026-11-03: V5 on branch `claude/v5-doctrine` from local main ab6467c: 9f6f504 `design_principles.md` rewritten for B′ with the numbering, headings and named rules unchanged, 0c29a3f token and primitive comments (build output byte-identical), 48211a3 `PRODUCT.md` and the docs index, then this plan. Before the rewrite the user decided three conflicts between code and plan: no zebra, a solid Risk benchmark, and `--chart-secondary` for comparison only; the code that disagrees is listed for V6. The new Drift Scan was run as a review with fourteen groups of findings for V6. The gamma-ui and gamma-charts skills outside the repository were rewritten after a backup. Not merged.
- 2026-11-03/04: after the report, at the user's request, 7b36ac3 renamed the brand subtitle in the app from "Research Terminal" to "Research Workspace" (and the gamma-usability-audit skill's wording), and 694bb07 did the same on the marketing site.
- 2026-11-04: the user merged V5 into main as 9192e29 (not pushed). V5 is complete.
- 2026-11-04: main pushed to origin (fast-forward from ab6467c), V5.
- 2026-11-04/05: V6 on branch `claude/v6-hardening` from main 4b60e16: 5bf2ffb V6a primitives, c134206 V6b copy and charts, 6d943d1 V6c special surfaces, fe13f68 V6d narrow widths, 5294bfa gate (visual baselines, two contrast fixes) and 87333e4 (the last narrow overflows); 0697257, 499642c, e70d6e4 and d296f6f from the live audit session; 369e51c the website on B′ with captures the user approved. Contrast audit 0 failures and 74 fold rows in each theme. The live audit stopped when TWS closed and resumed at 14:03 after the user reopened it; its report found no new P0/P1 visual finding, and the two backend P1s it found were fixed with the user's go-ahead (5f01681, e94fe62). Not merged, not pushed.
