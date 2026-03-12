# Gamma Migration Plan

This file is the detailed migration log and audit record for the ongoing strangler migration from PySide6/Qt to Tauri + FastAPI + Svelte.

`README.md` is intentionally kept shorter and operational. This document holds the fuller phase history, audit evidence, and open-risk tracking.

## Current Status

- Branch: `migration/tauri-fastapi`
- Restore point: `pre-ai-migration-2026-03-07`
- Tauri is now the default desktop path.
- PySide desktop app remains in place as an explicit fallback and is still runnable.
- Mock mode is preserved.
- Application service layer now exists in `src/application/`.
- FastAPI backend now exists in `src/api/`.
- Browser frontend bootstrap now exists in `frontend/`.
- Phase 7 is complete for local development.
- Phase 8 has an implemented Windows-first packaging path, but broader installed-workflow QA is still open.
- Phase 9 cutover is implemented and smoke-validated, with burn-in still open.

## Documentation Notes

- The old standalone risk-tab audit document was retired on 2026-03-09 because it had drifted from the current frontend-plus-shared-services implementation.
- Risk behavior now spans shared Python services plus the browser/Tauri view layer, so detailed risk changes should be tracked here or in code-adjacent docs with current ownership and scope.

## Phase Dashboard

| Phase | Status | Completion | Evidence | Open work |
| --- | --- | --- | --- | --- |
| 1. Extract Backend Orchestration From Qt | Complete | 100% | `src/application/*`, `src/application/runtime.py`, thin Qt adapters in `src/ui/tabs/*` | Ongoing regression checks only |
| 2. Define API Contracts | Complete | 100% | `src/api/schemas/*`, exercised by `tests/test_api.py` | None called out |
| 3. Add FastAPI | Complete | 100% | `src/api/main.py`, `src/api/routes/*`, `tests/test_api.py` | None called out |
| 4. Bootstrap Browser Frontend First | Complete for baseline scope | 100% | `frontend/src/*`, browser app boots, `npm run build` passes | Parity was never the exit target for this phase |
| 5. Chart-First Migration | Complete for target scope | 100% | Interactive portfolio, research, risk, and IV chart surfaces in `frontend/src/views/*` | IV still intentionally uses a 2D explorer rather than the Qt 3D workstation |
| 6. Functional Parity | Substantially complete | 85% | Core portfolio, research, risk, diagnostics, and IV workflows are usable through shared services and browser context forwarding | Advanced desktop ergonomics, saved-workspace flows, and some deeper IV/research affordances still lag Qt |
| 7. Add Tauri Shell | Complete for local development | 100% | `frontend/src-tauri/*`, `src/desktop_launcher.py`, `npm run desktop:smoke` passes | Local-dev assumptions still require the repo checkout plus `.venv` |
| 8. Packaging | Substantially complete | 85% | `src/api/desktop_entry.py`, `frontend/scripts/build-backend.mjs`, `tests/test_desktop_backend_smoke.py`, `npm run backend:smoke` passes | Broader installed-app QA remains open; `npm run tauri:build` was not revalidated to completion inside this audit window |
| 9. Cutover | Implemented, in burn-in | 90% | Tauri is the default launcher through `src.desktop_launcher`; PySide fallback remains; `npm run desktop:smoke` passes | Longer-session and live-IBKR burn-in remain open |

## Audit Snapshot

Last audited: 2026-03-08

Verified in the current audit:
- `.\.venv\Scripts\python.exe -m pytest` -> `52 passed`
- `npm run test` in `frontend/` -> `8 passed`
- `npm run build` in `frontend/` -> success
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml` -> success
- `npm run backend:smoke` in `frontend/` -> success; packaged `gamma-backend.exe` reached `/health`
- `npm run desktop:smoke` in `frontend/` -> success; the default launcher started Tauri, the backend reached readiness, and the main window reached frontend page load
- `npm run tauri:build` in `frontend/` -> attempted, but not revalidated to completion inside a 5-minute audit cap; an NSIS installer artifact already exists under `%TEMP%\gamma-tauri-build\release\bundle\nsis\`

Resolved during this audit:
- Completed the remaining Phase 1 extraction by moving active-snapshot selection, IV symbol-follow rules, and market-data mode propagation into shared application modules.
- Removed the duplicated fallback risk engine from `src/ui/tabs/risk_tab.py`; Qt now calls `src/application/risk_service.py` exclusively for non-visual risk computation.
- Removed obsolete backend helper wrappers from `src/ui/tabs/overview_tab.py` and moved warning categorization into `src/application/portfolio_service.py`.
- Added browser diagnostics and operator controls: diagnostics panel, connection toggle action, and market-data mode switching backed by shared FastAPI/runtime state.
- Exposed Monte Carlo distribution/fan payloads through the risk API so browser risk charts can reuse the shared Python analytics output directly.
- Upgraded the browser research and risk views from chart placeholders into app-native chart decks, including drawdown, rolling vol/beta, return distributions, contribution ranking, and Monte Carlo fan/distribution visuals.
- Added browser context forwarding from research into risk and IV so the web flow now carries snapshot/symbol context across tabs instead of forcing re-entry.
- Added a shared `/portfolio/performance` API route and upgraded the browser portfolio workflow to consume shared benchmark/performance diagnostics rather than relying only on raw local history.
- Expanded the browser portfolio, research, risk, and IV views into fuller command decks with richer table controls, structure/context summaries, operator-visible diagnostics, and shared-service-backed exploration state.
- Added browser operator actions for diagnostics, force subscribe, and local-history reset backed by shared FastAPI/runtime endpoints instead of frontend-only controls.
- Added IV session endpoints (`/iv/session`, `/iv/session/start`, `/iv/session/stop`) so the browser/Tauri path can use Python-owned IV session state rather than only shallow one-shot loads.
- Added a frontend test harness with Vitest and targeted tests for store orchestration, async loading, context forwarding, and critical view-model behavior.
- Scaffolded an in-repo Tauri shell under `frontend/src-tauri/` that launches the repo-local Python backend, waits for `/health`, shows a startup splash, creates the main window only after readiness, and kills the backend on shell exit.
- Added Tauri/local-desktop documentation and broadened FastAPI CORS handling for Tauri origins.
- Added a dedicated desktop backend entrypoint in `src/api/desktop_entry.py` so dev and packaged desktop flows share the same startup path.
- Added Windows-first backend packaging via PyInstaller and wired `frontend/scripts/build-backend.mjs` into `npm run tauri:build`.
- Updated the Tauri production path to launch the bundled backend executable from resources instead of assuming a repo checkout or `.venv`.
- Added packaged-startup diagnostics written to app-data logs plus a backend failure report for splash-screen error reporting.
- Added automated desktop packaging validation via `tests/test_desktop_backend_smoke.py` and `npm run backend:smoke`.
- Added `src/desktop_launcher.py` and `gamma-desktop` so the default desktop launcher now targets Tauri instead of PySide.
- Kept PySide available through `src.desktop_launcher --client pyside`, `GAMMA_DESKTOP_CLIENT=pyside`, and `gamma-pyside`.
- Added `frontend/scripts/smoke-desktop-launcher.mjs` plus `npm run desktop:smoke` to validate the real default desktop cutover path instead of only backend startup.
- Tightened Tauri startup so the splash remains visible until the main frontend window reaches page load; stale packaged-startup logs are also cleared before each launch.
- `frontend/src/views/PortfolioView.svelte` now recomputes summary cards, positions, and chart state when API data arrives.
- `frontend/src/views/ResearchView.svelte` now recomputes chart state when results or chart mode change.
- `frontend/src/views/RiskView.svelte` now tracks the active snapshot and chart state reactively.
- `frontend/src/views/IvView.svelte` now recomputes expiry rows and the selected slice when surface data changes.

Still outstanding after audit:
- Broader workflow QA beyond startup/build remains advisable during burn-in, especially for live IBKR and long-session desktop use.
- Installed-app workflow coverage still goes less deep than startup/backend smoke.

Completed:
- Phase 2 API schemas are implemented.
- Phase 3 FastAPI routes are implemented and covered by `tests/test_api.py`.
- Phase 4 browser baseline is now usable, builds successfully, and has had the major reactive-state audit issue corrected.
- Phase 5 chart migration is complete with interactive browser-native charts now covering the core migrated workflows.

Work in progress:
- The research workflow is routed through `src/application/research_service.py`.
- Portfolio, risk, and IV services now own the primary non-UI orchestration path used by both FastAPI and the Qt adapters.
- Phase 6 parity polish remains open.
- Post-cutover burn-in remains open.
- Packaging/install validation remains open.

Not done yet:
- Broader installed-workflow validation beyond packaging/startup smoke
- Full live-IBKR and long-session validation across the default Tauri desktop path

## Principles

- Do not break the existing PySide app early in the migration.
- Keep IBKR integration and analytics in Python.
- Reuse analytics, services, and models before rewriting anything.
- Prefer polling-friendly HTTP endpoints before websockets.
- Treat Tauri as a thin desktop shell, not a business-logic layer.

## Phase 1: Extract Backend Orchestration From Qt

Objective:
- Move non-visual logic out of Qt tabs so workflows are callable without Qt widgets.

Status:
- Complete.

Completed:
- Added `src/application/`.
- Added `src/application/runtime.py` to assemble the Python runtime for the API path.
- Extracted research orchestration into `src/application/research_service.py`.
- Added working service layers for:
  - `src/application/portfolio_service.py`
  - `src/application/risk_service.py`
  - `src/application/iv_service.py`
- Added shared workflow helpers for:
  - `src/application/workspace_service.py`
  - `src/application/system_service.py`
- Added/updated service-level extraction coverage in:
  - `tests/test_research_service.py`
  - `tests/test_risk_tab_logic.py`
  - `tests/test_app_mode_logic.py`
  - `tests/test_api.py`

Qt ownership after extraction:
- `src/ui/tabs/overview_tab.py`, `src/ui/tabs/risk_tab.py`, and `src/ui/tabs/iv_surface_tab.py` are now thin adapters for widget state, event wiring, and rendering.
- Shared application code now owns the remaining non-visual workflow decisions that were still trapped in those tabs.

Current reality:
- `src/ui/main_window.py` now builds from `src/application/runtime.py` instead of reassembling the runtime graph itself.
- `src/ui/tabs/overview_tab.py` now delegates snapshot retrieval, performance/history orchestration, and diagnostics plumbing to `src/application/portfolio_service.py`.
- `src/ui/tabs/risk_tab.py` now delegates the risk compute path exclusively to `src/application/risk_service.py` and uses shared snapshot-selection helpers instead of Qt-owned workflow logic.
- `src/ui/tabs/iv_surface_tab.py` now delegates engine/session lifecycle to `src/application/iv_service.py` and uses shared workspace helpers for research symbol follow behavior.
- `src/ui/main_window.py` now delegates runtime market-data mode propagation to `src/application/runtime.py`.
- The API and the desktop app now share the same primary application-service path for portfolio, risk, research, and IV workflows.

## Phase 2: Define API Contracts

Objective:
- Introduce stable request/response schemas between backend and frontend.

Status:
- Implemented.

Files:
- `src/api/schemas/system.py`
- `src/api/schemas/portfolio.py`
- `src/api/schemas/research.py`
- `src/api/schemas/risk.py`
- `src/api/schemas/iv.py`

Coverage:
- Health and system status
- Connection state
- Portfolio snapshot and history
- Positions
- Research request/result
- Risk request/result
- IV surface payload
- Diagnostics payload

Validation:
- API schema coverage is exercised through `tests/test_api.py`.

## Phase 3: Add FastAPI

Objective:
- Expose extracted Python workflows as a local HTTP API without removing PySide.

Status:
- Implemented.

Files:
- `src/api/main.py`
- `src/api/routes/system.py`
- `src/api/routes/portfolio.py`
- `src/api/routes/research.py`
- `src/api/routes/risk.py`
- `src/api/routes/iv.py`

Implemented endpoints:
- `GET /health`
- `GET /system/status`
- `POST /system/connection/toggle`
- `POST /system/market-data-mode`
- `GET /portfolio/snapshot`
- `GET /portfolio/history`
- `POST /portfolio/performance`
- `POST /portfolio/history/clear`
- `POST /research/analyze`
- `POST /risk/compute`
- `GET /iv/surface`
- `GET /iv/session`
- `POST /iv/session/start`
- `POST /iv/session/stop`
- `GET /diagnostics`
- `POST /diagnostics/run`
- `POST /system/account-subscribe`

Validation:
- `tests/test_api.py`
- Current audit run: passing

## Phase 4: Bootstrap Browser Frontend First

Objective:
- Build the new UI in a browser before wrapping it in Tauri.

Status:
- Bootstrap implemented.

Files:
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/src/main.ts`
- `frontend/src/App.svelte`
- `frontend/src/lib/api/`
- `frontend/src/lib/stores/`
- `frontend/src/lib/theme/`
- `frontend/src/components/`
- `frontend/src/views/`

Current frontend scope:
- Terminal/dark shell
- Top status rail
- Tab navigation
- Portfolio baseline with better summary cards, local-history context, positions table, and a real migrated chart region
- Research baseline with single-ticker and synthetic-portfolio inputs, summary cards, warnings, and a chart-ready output area
- Risk baseline with configurable benchmark/confidence/lookback/horizon controls plus warnings and excluded-asset visibility
- IV baseline with symbol input, requested market-data mode, surface status, 2D heatmap, and expiry-slice preview

Validation:
- `npm run build` passes
- Current audit confirmed the migrated views now refresh correctly from asynchronous store updates after the reactive-state fix.

Known gaps:
- Frontend remains intentionally incremental and does not yet match the richer Qt analytics surface
- Risk view still defaults to polling-style request/response rather than richer live session behavior
- IV frontend now has session controls and richer exploration, but it still remains a 2D browser explorer rather than the full 3D Qt surface workstation
- Qt still has stronger desktop ergonomics and a richer operator workflow than the browser/Tauri path
- Frontend validation now has dedicated tests, but coverage is still focused on critical store/view-model behavior rather than full component interaction

Phase 4 exit note:
- Bootstrap and usable-baseline work are complete for this stage, but this still does not imply parity.

## Phase 5: Chart-First Migration

Objective:
- Replace static/matplotlib-heavy charts with app-native interactive charts.

Status:
- Complete.

Target stack:
- TradingView Lightweight Charts for portfolio/research time series
- D3 for custom 2D risk visuals
- Plotly.js or 2D heatmap/slice views for IV

Current progress:
- Added TradingView Lightweight Charts to the frontend.
- Migrated the portfolio history/performance workflow into an interactive browser chart backed by `GET /portfolio/history`.
- Upgraded the research browser view into a multi-mode chart deck with performance, price, drawdown, rolling vol, and rolling beta views driven by shared API data.
- Upgraded the risk browser view into a richer chart deck with time series, return distribution, contribution ranking, Monte Carlo distribution, and Monte Carlo fan visuals.
- Extended the risk API schema so the browser can render Monte Carlo fan/distribution visuals from shared backend outputs instead of reimplementing analytics client-side.
- IV remains on a custom 2D heatmap/slice presentation, which satisfies the interim Phase 5 target for IV.

## Phase 6: Functional Parity

Objective:
- Make the web frontend genuinely usable.

Status:
- Implemented with remaining polish gaps.

Target features:
- Positions table parity
- Research builder parity
- Synthetic portfolio builder parity
- Diagnostics panel
- Connection state and market-data switching
- Context forwarding from research to risk and IV

Recent progress:
- Browser diagnostics panel is now implemented.
- Browser connection state and market-data switching controls are now implemented.
- Browser research context can now jump directly into risk compute or IV loading with forwarded snapshot/symbol context.
- Browser portfolio workflow now includes shared-service performance/benchmark diagnostics, richer positions controls, and broader book diagnostics.
- Browser research workflow now includes a stronger synthetic-builder path, structure preview, and richer chart modes.
- Browser risk workflow now surfaces the broader shared Python metric set, coverage diagnostics, concentration, and exclusions.
- Browser IV workflow now includes backend session controls plus term-structure and skew-style exploration on top of the shared Python payload.
- Frontend regression coverage now exists for async store loading, state synchronization, and research context forwarding.

Current gap summary:
- Qt remains the richer client for advanced desktop ergonomics and the 3D IV surface presentation
- The browser frontend is now a credible core-workflow replacement for portfolio, research, risk, diagnostics, and IV exploration in mock/local API use
- Remaining parity gaps are now mostly advanced desktop ergonomics, saved-workspace workflows, and some deeper IV/research affordances rather than missing core screens

## Phase 7: Add Tauri Shell

Objective:
- Wrap the working web frontend in a desktop shell.

Status:
- Complete for local development.

Target responsibilities:
- Launch Python backend
- Wait for `/health`
- Load frontend
- Clean shutdown
- Show a startup/error splash while backend readiness is pending

Implementation notes:
- Tauri shell now lives in `frontend/src-tauri/`.
- Local development launches the repo-local `.venv` Python via `python -m src.api.desktop_entry`.
- Backend readiness is gated on `GET /health`.
- The main window is created only after backend readiness; a splash window stays visible during startup and on startup failure.
- Backend child-process shutdown is wired to shell exit.
- `npm run tauri:dev` now routes Cargo build artifacts to a temp directory automatically so the Windows local-dev path avoids the file-lock contention seen in the default in-repo target directory.
- The shell now prefers localhost port `8000` for the backend but falls back to another free port when needed and injects the selected API base into the frontend at window startup.
- Current local-dev assumption: repo checkout and `.venv` are present on disk.

## Phase 8: Packaging

Objective:
- Ship a one-click desktop install.

Status:
- Implemented for Windows-first packaging; broader installer QA still open.

Implemented:
- Added `src/api/desktop_entry.py` as the shared desktop backend entrypoint.
- Added PyInstaller-based backend packaging through `frontend/scripts/build-backend.mjs`.
- `npm run tauri:build` now packages the Python backend before invoking the Tauri build.
- Tauri bundled mode now resolves `resources/backend/gamma-backend/gamma-backend.exe` and no longer depends on a repo-local `.venv` at runtime.
- Packaged desktop runtime paths now use Tauri app-data directories for cache, local history, and backend startup logs.
- Backend startup failures now surface a failure report plus stdout/stderr log paths to the splash window.
- Windows NSIS installer generation is enabled and validated.
- Automated validation now exists for the desktop backend startup path:
  - `tests/test_desktop_backend_smoke.py`
  - `npm run backend:smoke`

Remaining packaging work:
- Expand installed-app QA beyond backend/startup smoke into broader manual desktop workflow coverage.
- Decide whether to slim the packaged backend footprint further; the current PyInstaller bundle is pragmatic and working, but it still carries PySide-era Python dependencies because those remain installed and supported.

## Phase 9: Cutover

Objective:
- Make the Tauri app primary only when it is stable enough.

Status:
- Complete.

Rule:
- Keep PySide fallback until parity and stability are credible.

Implemented in this phase:
- The repo-level default desktop launcher is now `src.desktop_launcher`, which defaults to Tauri.
- PySide remains a supported fallback through `--client pyside`, `GAMMA_DESKTOP_CLIENT=pyside`, or `gamma-pyside`.
- Desktop validation now covers the real default launcher path through `npm run desktop:smoke`.
- Tauri startup now waits for frontend page load before dismissing the splash screen, so installed-app startup failures are less likely to masquerade as success.

Residual risk:
- Cutover is validated for startup, packaging, and smoke-mode desktop boot in mock mode; it is not exhaustive coverage of every long-running or live-IBKR operator workflow.

## Validation Commands

Backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run FastAPI locally:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Run the existing PySide app:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m src.main
```

Run the default desktop launcher:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m src.desktop_launcher
```

Run the explicit PySide fallback through the shared launcher:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m src.desktop_launcher --client pyside
```

Run the frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

Run frontend tests:

```powershell
cd frontend
npm run test
```

Frontend build check:

```powershell
cd frontend
npm run build
```

Run the local Tauri shell:

```powershell
cd frontend
npm install
$env:MOCK_DATA="true"
npm run tauri:dev
```

Run packaged-backend smoke:

```powershell
cd frontend
npm run backend:smoke
```

Run desktop-launcher smoke:

```powershell
cd frontend
npm run desktop:smoke
```

Build the Windows installer:

```powershell
cd frontend
npm run tauri:build
```
