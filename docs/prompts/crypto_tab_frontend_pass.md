# Prompt: Crypto Tab Frontend Polish Pass

## Your Role

You are a frontend styling agent. Your job is to conduct a visual and structural polish pass on the **Crypto tab** (`frontend/src/views/CryptoView.svelte`) of the Gamma platform. You are not adding features, not changing data flow, not modifying backend calls. You are purely adjusting styling, spacing, layout, and visual consistency to bring the Crypto tab in line with the platform's design system.

## Before You Write Any Code

Read these documents **in this order**. Do not skim — read fully:

1. **`docs/design_principles.md`** — This is your primary authority. Every styling decision you make must be traceable to a rule in this document. If a choice isn't covered, look at what the Macro tab does and match it.

2. **`frontend/src/lib/theme/tokens.css`** — The token system. You must use these variables. Never hardcode a color, background, or border that has a token equivalent.

3. **`frontend/src/views/CryptoView.svelte`** — The file you'll be modifying. Read the full `<style>` block before making changes. Understand the current structure.

4. **`frontend/src/views/MacroView.svelte`** and **`frontend/src/components/MacroSnapshot.svelte`** — The reference implementation. The Macro tab is the gold standard for how Gamma should feel. Study its spacing, its use of tokens, its panel padding, its density. The Crypto tab should feel like it belongs in the same app.

## What You're Looking For

Open the app in a browser preview at 1440x900 (laptop size). Navigate to the Research View, then click the "Crypto" tab in the sidebar. Visually inspect the tab and compare what you see against the design principles. Specifically audit:

### 1. Panel Structure and Backgrounds
- Every `<article>` panel must use `background: var(--panel-bg)` (transparent).
- Borders must be `1px solid var(--panel-border)`.
- No gradients, no opacity-based backgrounds, no warm-tinted colors.
- Check the chart shell too — should be `background: var(--bg-0)`.

### 2. Spacing and Density
- Gaps between panels: `0.5rem` (8px). Check `.view`, `.workspace-grid`, `.primary-column`, `.support-column`, `.detail-split`.
- Panel internal padding: `0.85–1.05rem` (~13–17px). Not more.
- Internal gaps within panels: `0.5rem`.
- Compare visually against Macro: does Crypto feel as dense? If there's visible "breathing room" that Macro doesn't have, tighten it.

### 3. Input and Button Sizes
- Inputs in the screener panel (search, dropdowns, numeric fields) — check their height. The design principles target `28–32px` for data-context inputs. If they're taller (e.g. `48px`), reduce them.
- Buttons (`Run Screen`, `Refresh Sources`) — should match input height of their context. Check padding.

### 4. Typography
- H2 ("Select a token" / asset name): should be `15–20px`, weight `700`. If larger, reduce.
- H3 (panel titles like "Sector Baskets", "DEX View", "Token Screener"): `~15px`, weight `700`.
- Category labels (small uppercase text like `CRYPTO`, `NARRATIVES`, `DISCOVERY`): `10–11px`, uppercase, `--text-2` color, wide letter-spacing.
- Body text: `13–13.5px`, inherited from the body.
- Do NOT increase any font sizes. If anything, they should match or be slightly smaller than current.

### 5. Color Consistency
- All interactive accent colors must use `--accent` (`#7aa6c8`) or derived `rgba(122, 166, 200, ...)` values.
- No gold, amber, brown, or warm-tinted colors anywhere in the tab. If you find any remnants (e.g. `#d4a054`, `rgba(212, 160, 84, ...)`, `#f0d3a2`, `rgba(26, 23, 17, ...)`), replace them with blue-accent equivalents.
- Signal colors (green for positive, red for negative) are permitted only on data values (price changes, scores), not on UI chrome.

### 6. Tables
- Check the token screener table and any other tables.
- Column headers: small, muted (`--text-2`), uppercase optional.
- Row borders: `var(--divider)`.
- Row hover on interactive rows: `rgba(122, 166, 200, 0.06)`.
- Selected row: `rgba(122, 166, 200, 0.08)`.

### 7. Responsive Behavior
- Resize to ~1000px width. The `workspace-grid` should collapse to single column. Verify nothing breaks.

## How to Work

1. **Open a browser preview** of the frontend at 1440x900.
2. **Screenshot each section** of the Crypto tab — top (hero panel + screener), middle (chart + details), bottom (baskets + DEX + tokens table).
3. **Inspect specific CSS properties** using the browser tools for any element that looks "off" — check computed backgrounds, paddings, gaps, font sizes, border-radius.
4. **Make changes incrementally** in `CryptoView.svelte` only. After each batch of changes, screenshot again to verify.
5. **Do not modify** any other view, component, or the token file. This pass is scoped to CryptoView only.
6. **Use tokens everywhere.** Replace any raw `rgba(...)` or `#hex` that has a token equivalent with `var(--token-name)`.

## What NOT to Do

- Do not add new features or UI elements.
- Do not change the HTML structure (element hierarchy, component usage) unless strictly necessary for a styling fix.
- Do not modify `tokens.css` or any shared component.
- Do not introduce any new colors, gradients, shadows, or border-radius > 4px.
- Do not increase font sizes, padding, or spacing. The direction is always: tighter, denser, flatter.
- Do not add animations or transitions that don't already exist.

## Deliverable

When you're done, the Crypto tab should:
- Look like it belongs in the same app as the Macro Cross-Asset view
- Use zero hardcoded colors — all tokens
- Have 8px gaps between all panels
- Have compact, dense inputs and controls
- Feel flat — one plane, borders only, no depth cues

Commit your changes with a clear message describing what was adjusted.
