# Gamma

For future product expansion work, start with [`roadmap.md`](./roadmap.md). It defines what to build next, the intended sequencing, and the architectural constraints that should guide new features.

Gamma is a hybrid quant workstation built around a Python analytics/runtime layer with FastAPI, a Svelte frontend, and a Tauri desktop shell. Tauri is now the primary desktop path. PySide remains available as an explicit fallback during burn-in.

For the detailed migration log, phase history, and audit notes, see [`migration.md`](./migration.md).

## Repo At A Glance

- Python application services live in `src/application/`
- FastAPI backend lives in `src/api/`
- Browser frontend lives in `frontend/`
- Tauri shell lives in `frontend/src-tauri/`
- Sample/mock data lives in `sample_data/`
- Automated tests live in `tests/` and `frontend/src/**/*.test.ts`

## Current State

- Tauri is the default desktop launcher path
- Core portfolio, research, risk, diagnostics, and IV workflows are usable through the web/Tauri stack
- Packaging is implemented for Windows-first distribution
- PySide is still supported as a fallback client
- Broader live-IBKR and longer-session QA are still open

## Core Workflows

- Portfolio workspace with account summary, positions, composition, performance, and diagnostics
- Research workspace for single-ticker and synthetic-portfolio analysis
- Risk workspace for VaR, volatility, concentration, contribution, and Monte Carlo views
- IV workspace for browser/Tauri-based surface exploration and session controls

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env
```

Runtime-only alternative:

```powershell
pip install -e .
```

## IBKR / TWS Notes

- Use Trader Workstation for live mode. IB Gateway is not supported yet.
- In TWS, enable `ActiveX and Socket Clients` and match the configured port.
- Set `.env` values for `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, and optionally `IB_ACCOUNT`.
- `IB_MARKET_DATA_MODE=delayed` is the safe default if you do not have live entitlements.
- `MOCK_DATA=true` enables offline development with local sample data.

If the app connects but shows an empty portfolio, use the Portfolio diagnostics controls to verify managed accounts, account selection, and subscription state.

## Run Modes

Run the backend directly:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Run the browser frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

Run the default desktop launcher:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m src.desktop_launcher
```

Run the explicit PySide fallback:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m src.desktop_launcher --client pyside
```

Run local Tauri development:

```powershell
cd frontend
npm install
$env:MOCK_DATA="true"
npm run tauri:dev
```

## Validation

Backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Frontend checks:

```powershell
cd frontend
npm run test
npm run build
npm run backend:smoke
npm run desktop:smoke
```

Additional desktop validation:

```powershell
cargo check --manifest-path frontend\src-tauri\Cargo.toml
cd frontend
npm run tauri:build
```

## Packaging

The Windows packaging flow bundles the Python backend with PyInstaller before Tauri creates the installer.

```powershell
cd frontend
npm run backend:smoke
npm run tauri:build
```

The installer output lands under `%TEMP%\gamma-tauri-build\release\bundle\nsis\` unless `CARGO_TARGET_DIR` is overridden.

## Known Limitations

- IB Gateway is not supported yet
- Some live/delayed market-data scenarios still depend on IBKR entitlements and symbol availability
- Risk analytics are linear and history-based rather than full nonlinear scenario modeling
- Browser/Tauri workflows are usable, but some advanced desktop ergonomics still lag the old PySide client

## Repo Layout

```text
src/
  application/
  api/
  analytics/
  models/
  services/
  ui/
tests/
docs/
frontend/
sample_data/
```
