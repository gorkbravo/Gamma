# Visual Refresh Implementation Plan (B′ · Tonal compact)

_Living implementation and handoff document._

- Decision approved: 2026-10-28. Target direction **B′ "Tonal compact"**; the current left navigation drawer stays as primary navigation.
- Last reviewed: 2026-10-28
- Implementation status: V1 in progress. Panel title, tags and the data table with its modifiers are done (tables converged on branch `claude/musing-easley-b0d363`, not yet merged); buttons, inputs, selects and inline stats remain. V2–V6 planned.
- Roadmap owner: Workstream 1, Cross-Cutting Platform Foundation, in [`../roadmap.md`](../roadmap.md). V1–V3 are shared-platform work; V4–V6 are the visual layer on top of it.
- Exploration and measurements: private artifact `https://claude.ai/artifact/GWx2nqyGg7WK2JhAaxeXXb` (version 2, 2026-10-28). It mocks Sitrep, Commodities › Curves & Spreads, Options › Overview, Risk › Overview and Copilot in every direction considered.
- Doctrine: [`design_principles.md`](./design_principles.md) stays authoritative for the current look until V5 rewrites it. Do not apply B′ values to views before V4.

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
- **Open decision (V4 gate):** tickers and contract codes (`BZZ6`, `CLZ6`, option symbols) and ISO dates in sans versus mono at 12px. Default to sans. If they read worse with real data, add `--font-id` (mono) for identifier cells only.

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
- **Tables:** 28px rows, 10–12px side padding, tinted header band, light row rules, no zebra, sticky header. Heat-map cells may separate with 2px gaps and a 3px radius.
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
| V1 — Shared primitives under the current look | Extend `frontend/src/lib/theme/primitives.css` (panel, header, mode bar, KPIs and eyebrow already exist) with the data table, tag, 26px panel title, inline stats, buttons, inputs and selects. Migrate the ~20 scoped `th, td` copies and 9 `.tag` copies. Keep genuine local exceptions as scoped overrides and list them. | No visual change except the deliberate convergences listed under [V1 convergences and kept exceptions](#v1-convergences-and-kept-exceptions), each reviewed on before/after screenshots of every view in mock mode (1440×900, DPR 1). `npm run typecheck`, `npm test` and `npm run build` pass without warnings from the changed files. | In progress (2026-10-28): panel title, tags and the data table done; buttons, inputs, selects and inline stats open |
| V2 — Token completeness and font roles | Replace the 71 raw `rgba(122, 166, 200, …)` values and 92 hex literals (18 files). Fix the ~62 `font: inherit` that pull chrome back to mono. Split `--app-font`/`--display-font` into `--font-ui`, `--font-num`, `--font-code` and `--font-label`. Add tint, soft semantic, scrim, `--panel-radius`, `--panel-border-width` and label-case tokens. Move `chart-colors.ts` and the flash keyframes onto tokens. | Values unchanged, so screenshot parity still holds. A grep gate shows no raw accent colors or hex literals in `.svelte` files outside a documented exception list. | Planned |
| V3 — Theme infrastructure | `data-theme` on `<html>` (System/Light/Dark) with persistence and a Settings control, plus a theme store. `TimeSeriesChart`, `Surface3D`, `MaritimeMap` and the CodeMirror editor re-read tokens on change. Retire the chart-theme setting; turn the font setting into "Data figures". Add the light token block, with current dark values kept as the dark block. | Switching theme needs no reload and every chart and map recolors. Contrast meets WCAG AA (4.5:1 text, 3:1 graphics and focus), including warning text on its soft fill in light mode. | Planned |
| V4 — B′ values and fonts | Self-host Instrument Sans and preload it. Set B′ token values and the structural rules: borderless sheets, radii, header band, pill tags, KPI blocks, segmented controls, floating drawer and chart styling. Resolve the identifier-font decision. | Visual review of all 13 views in light and dark at 1440, 1000 and 390px. Rows above a 780px fold on Sitrep, Commodities, Options and Risk stay within −5% of today. Fonts resolve in the packaged desktop build with no network. | Planned |
| V5 — Doctrine and skills | Rewrite `design_principles.md` in place (map below) and update the `tokens.css` comments. Update the `gamma-ui` and `gamma-charts` skills outside the repo, whose descriptions still ask for "more like a professional trading terminal". | §1–§15 numbering is unchanged and the skills' §14/§15 references still land on the right content. The drift scan reflects B′. | Planned |
| V6 — Hardening | Per-surface exceptions: Sitrep stream, Sealanes map style, `Surface3D`, the Script editor, the Copilot run inspector, website screenshots. Update the screenshot baselines and run a usability audit pass. | Usability audit with no new P0/P1 visual findings; website screenshots regenerated or explicitly deferred. | Planned |

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
- Per-table specifics that stay scoped on top of `.data-table`: Sitrep market column proportions and fixed layout; Options chain strike, ITM and ATM shading and the surface's sticky row headers; the Fundamentals DCF sheet grid; the Strategy Lab composer's compact inputs; 11px mono cells in the Script tables; content width and 2px rows for tables inside Copilot answers; Prediction Markets group, section and tick columns; the partner code under each Trade Partners name; Macro Rates' fainter stripe and the Macro snapshot row hover (raw rgba, left for V2).
- Tags: the warning outline at 0.3 in MacroLinkedMarketRow and MacroSnapshot, `flex-shrink: 0` in three Macro rows, and MacroCoherencePanel's wrapping chips. MacroCoherencePanel is not imported anywhere; deleting or reviving it is a follow-up.

Still open in V1: buttons, inputs and selects (about 250 scoped element rules in 36 files, plus class-based buttons such as `.mode-btn` and `.ghost`) and the inline stats. Move them without fixing `font: inherit` or raw colours, which belong to V2.

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
- 2026-10-28: with the user's approval, V1 continues with deliberate convergences. On branch `claude/musing-easley-b0d363` (not merged), a373294 moves every data table onto `.data-table` plus modifiers and 7616ea2 folds the four gold Macro tags into `.tag.is-tinted.context`. The convergences and kept exceptions are listed above. Buttons, inputs, selects and inline stats are still open.
