# Phase 3 Keyboard Navigation & Workspace Customization Prompt

Use this prompt when handing Gamma's Phase 3 implementation to another AI coding agent.

## Prompt

You are implementing **Gamma Phase 3: Keyboard Navigation & Workspace Customization** in the repository at `C:\Users\User\Desktop\Gamma`.

Start by reading:
- `AGENTS.md`
- `roadmap.md`
- `README.md`
- `frontend/src/App.svelte`
- `frontend/src/components/TabBar.svelte`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/stores/app.ts`

### Product goal

Implement the roadmap's **keyboard-driven navigation layer** and **customizable tab ordering** so Gamma can be used efficiently without the mouse.

This is not a cosmetic pass. It should change how the user moves through the app:
- keyboard shortcuts should work at the app level
- the sidebar should become a reorderable navigation surface
- tab order should persist per workspace
- shortcut mapping should follow visual tab order

The end state should match the roadmap's intent:
- visual order = shortcut order
- the first tab in each workspace is pinned and not draggable
- power users can operate Gamma primarily from the keyboard

### Roadmap scope to implement

Phase 3 requires:
- drag-and-drop tab reordering in the sidebar
- `Ctrl+1` through `Ctrl+N` tab switching based on current custom order
- a sidebar toggle shortcut
- visible shortcut hints in the sidebar
- action shortcuts for refresh, settings, and dismiss/close
- workspace switching via keyboard
- a settings entry for viewing and, if practical, customizing keybindings in a separate window

If you have time, add a lightweight `?` shortcuts overlay, but do not let that block the core deliverable.

### Current implementation context

The current app already has the basic pieces you need:
- `frontend/src/App.svelte` owns:
  - `workspaceMode`
  - `activeTab`
  - `sidebarOpen`
  - `selectTab(...)`
  - `switchWorkspace(...)`
  - refresh behavior for the active tab
- `frontend/src/components/TabBar.svelte` currently renders a simple sidebar list
- `frontend/src/lib/stores/app.ts` already holds shared frontend state and is the right place for a shared tab-order store if needed

Use these existing integration points instead of inventing a second navigation system.

### UX requirements

#### 1. Sidebar reordering

The sidebar should support drag-and-drop reordering with these rules:
- In Portfolio workspace, `Portfolio` is pinned in slot 1 and cannot be dragged.
- In Research workspace, `Research` is pinned in slot 1 and cannot be dragged.
- All other tabs in that workspace are reorderable.
- Reordering is vertical only.
- The interaction should show:
  - a drag handle on draggable rows
  - a clear insertion indicator
  - restrained motion only

Do not introduce a heavy drag-and-drop framework unless truly necessary. Native HTML5 drag-and-drop is acceptable. If you use a small Svelte-native DnD helper, keep the dependency lightweight and justified.

#### 2. Per-workspace persistence

Tab order must persist independently for:
- Portfolio workspace
- Research workspace

Use localStorage-backed frontend state unless a stronger existing persistence pattern already exists in the repo.

Required behavior:
- each workspace keeps its own order
- reload restores the saved order
- newly added tabs appear at the end by default
- a reset-to-default affordance exists in the sidebar

The reset affordance can be small. It does not need a modal.

#### 3. Keybinding rules

Implement app-level keybindings with cleanup on unmount.

Required bindings:
- `Ctrl+1` ... `Ctrl+N`: switch to the tab in that visual order for the active workspace
- `Ctrl+B` or backtick: toggle sidebar
- `Ctrl+R` or `F5`: refresh the current active view using the app's existing refresh logic
- `Ctrl+,`: open settings or diagnostics/settings surface if no dedicated settings view exists yet
- `Escape`: close sidebar and dismiss lightweight overlays/popovers
- `Ctrl+Shift+P` and/or `Ctrl+Shift+R`: switch workspaces

Keybinding behavior must:
- avoid obviously destructive conflicts
- be registered at the app shell level, not per-view
- work consistently regardless of which tab is active
- avoid hijacking text input interactions where the shortcut would be inappropriate

If you need to scope certain shortcuts away from input/textarea/select/contenteditable elements, do so.

### Settings / keybindings window

Add a keyboard-settings affordance under Settings:
- a `Key Bindings` button or entry should exist in the settings/diagnostics surface
- clicking it should open a **new window**, not an inline panel
- that window should at minimum show:
  - the default keybindings
  - the current effective keybindings
  - which bindings are derived from tab order versus explicitly assigned

If practical within the phase, allow the user to customize selected keybindings there and persist them locally.

Customization is valuable for power users, but it is secondary to shipping the core navigation system. If full editing is too large for one pass, ship the new-window keybindings viewer first and structure the state so editable bindings can be added cleanly next.

### Information architecture requirements

There must be **one shared source of truth** for tab ordering that is read by:
- the sidebar renderer
- the keybinding handler
- the visible shortcut hints
- any active-view label or breadcrumb logic that depends on ordering

Do not duplicate tab order logic in both `App.svelte` and `TabBar.svelte`.

Create a small shared tab-order module or store if needed.

### Suggested implementation shape

The exact file layout is up to you, but a good implementation will likely touch:
- `frontend/src/App.svelte`
- `frontend/src/components/TabBar.svelte`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/stores/app.ts`

It may also make sense to add one or more new files such as:
- `frontend/src/lib/navigation.ts`
- `frontend/src/lib/stores/tabOrder.ts`
- `frontend/src/components/ShortcutOverlay.svelte`
- focused tests near those modules

### Functional expectations

#### Sidebar

The sidebar should:
- render the tabs in persisted workspace-specific order
- show shortcut hints that update live with order
- visually distinguish pinned vs draggable rows
- expose a reset-to-default control

The pinned first row should still show its shortcut hint.

#### Tab switching

The app should be able to derive:
- the ordered tabs for the active workspace
- the tab at position `n`
- the correct `Ctrl+n` mapping from that order

This logic should work even after reorder and reload.

#### Workspace switching

When the user switches workspace by shortcut:
- move between `portfolio` and `research`
- preserve the target workspace's tab order
- land on that workspace's pinned home tab unless the app already has a strong reason to preserve the previously active tab in that workspace

Be consistent and explicit in code.

#### Refresh shortcut

Hook the refresh shortcut into Gamma's existing tab-specific refresh logic in `App.svelte`. Do not create a parallel refresh mechanism.

### Testing requirements

Add targeted tests. Do not rely only on manual checks.

At minimum, cover:
- default tab order generation per workspace
- pinned-first-tab behavior
- reorder persistence and reload restoration
- new-tab append behavior for unknown tabs
- `Ctrl+N` mapping following reordered state
- sidebar shortcut hints updating after reorder
- workspace-specific isolation of saved order
- reset-to-default behavior
- keybindings window launch behavior if implemented
- default/effective keybinding rendering if implemented

If practical, add component tests for the sidebar and store/unit tests for order logic.

### Constraints

- Keep Phase 3 focused on navigation and customization. Do not expand product scope.
- Do not add new top-level product concepts.
- Do not build onboarding flows or flashy help UI.
- Do not let a shortcut overlay become the main deliverable.
- Prefer small, composable state and utility modules over embedding everything in `App.svelte`.
- Preserve Gamma's existing read-only research identity.

### Deliverable

The result should make Gamma materially closer to the roadmap Phase 3 end state:
- reorderable sidebar navigation
- per-workspace persistent tab order
- keyboard-driven tab switching
- sidebar toggle shortcut
- workspace switching shortcut
- refresh and dismiss shortcuts
- discoverable shortcut hints in the sidebar
- a settings entry that opens a separate keybindings window
- tests covering the core navigation behavior

### Execution advice

Go as far as possible in one pass. Prioritize in this order:
1. shared tab-order store and persistence
2. reorderable sidebar UI
3. app-level keybinding handler
4. shortcut hints and reset affordance
5. keybindings window from Settings
6. tests
7. optional editable/custom keybindings and/or `?` overlay if time remains

If you must leave anything incomplete, leave editable custom keybinding assignment and the optional overlay incomplete before leaving the core reorder/keybinding system incomplete.
