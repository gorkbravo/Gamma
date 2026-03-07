# StrataLab Migration Plan

This file tracks the ongoing strangler migration from PySide6/Qt to Tauri + FastAPI + Svelte.

## Current Status

- Branch: `migration/tauri-fastapi`
- Restore point: `pre-ai-migration-2026-03-07`
- PySide desktop app remains in place and runnable.
- Mock mode is preserved.
- FastAPI backend now exists and is covered by tests.
- Browser frontend bootstrap now exists in `frontend/`.

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
- In progress.

Completed:
- Added `src/application/`.
- Extracted research orchestration into `src/application/research_service.py`.
- Added service shells for portfolio, risk, and IV.
- Added runtime bootstrap in `src/application/runtime.py`.

Still coupled to Qt:
- `src/ui/tabs/overview_tab.py`
- `src/ui/tabs/risk_tab.py`
- `src/ui/tabs/iv_surface_tab.py`

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
- Research request/result
- Risk request/result
- IV surface payload
- Diagnostics payload

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
- `GET /portfolio/snapshot`
- `GET /portfolio/history`
- `POST /research/analyze`
- `POST /risk/compute`
- `GET /iv/surface`
- `GET /diagnostics`

Validation:
- `tests/test_api.py`

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
- Portfolio placeholder view wired to FastAPI
- Research placeholder view wired to FastAPI
- Risk placeholder view wired to FastAPI
- IV placeholder view wired to FastAPI

Not done yet:
- Interactive chart migration
- Full functional parity
- Tauri shell

## Phase 5: Chart-First Migration

Objective:
- Replace static/matplotlib-heavy charts with app-native interactive charts.

Status:
- Not started.

Target stack:
- TradingView Lightweight Charts for portfolio/research time series
- D3 for custom 2D risk visuals
- Plotly.js or 2D heatmap/slice views for IV

## Phase 6: Functional Parity

Objective:
- Make the web frontend genuinely usable.

Status:
- Not started.

Target features:
- Positions table parity
- Research builder parity
- Synthetic portfolio builder parity
- Diagnostics panel
- Connection state and market-data switching
- Context forwarding from research to risk and IV

## Phase 7: Add Tauri Shell

Objective:
- Wrap the working web frontend in a desktop shell.

Status:
- Not started.

Target responsibilities:
- Launch Python backend
- Wait for `/health`
- Load frontend
- Clean shutdown

## Phase 8: Packaging

Objective:
- Ship a one-click desktop install.

Status:
- Not started.

Priority:
- Package Python backend first
- Bundle with Tauri second

## Phase 9: Cutover

Objective:
- Make the Tauri app primary only when it is stable enough.

Status:
- Not started.

Rule:
- Keep PySide fallback until parity and stability are credible.

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

Run the frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

Frontend build check:

```powershell
cd frontend
npm run build
```
