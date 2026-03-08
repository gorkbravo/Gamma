# StrataLab

Hybrid quant workstation in the middle of a strangler migration from PySide6/Qt to Tauri + FastAPI + Svelte. The Python runtime still owns IBKR integration, analytics, mock mode, and shared application services. Today the repo supports three client paths:

- Tauri desktop app, which is now the primary/default desktop client
- Browser frontend served separately against the local FastAPI backend
- PySide desktop app, kept as an explicit fallback during post-cutover burn-in

## Current State
- Shared application service layer lives in `src/application/`
- FastAPI backend lives in `src/api/`
- Browser frontend lives in `frontend/`
- Tauri shell lives in `frontend/src-tauri/`
- Windows packaging path is implemented through PyInstaller + Tauri NSIS bundling
- Tauri is the default desktop launcher path in-repo and in packaged builds
- PySide remains intentionally available through an explicit launcher switch

## Migration Audit
Audit date: `2026-03-08`

Current verification:
- `.\.venv\Scripts\python.exe -m pytest` -> `52 passed`
- `npm run test` in `frontend/` -> `8 passed`
- `npm run build` in `frontend/` -> success
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml` -> success
- `npm run backend:smoke` in `frontend/` -> success
- `npm run desktop:smoke` in `frontend/` -> success
- `npm run tauri:build` -> not revalidated to completion in this audit; an NSIS installer artifact already exists under `%TEMP%\stratalab-tauri-build\release\bundle\nsis\`

Phase status:
- Phase 1 `Extract Backend Orchestration From Qt`: complete
- Phase 2 `Define API Contracts`: complete
- Phase 3 `Add FastAPI`: complete
- Phase 4 `Bootstrap Browser Frontend First`: complete for baseline scope
- Phase 5 `Chart-First Migration`: complete for target scope
- Phase 6 `Functional Parity`: substantially complete; core workflows are usable but advanced desktop ergonomics and some deeper research/IV affordances still lag Qt
- Phase 7 `Add Tauri Shell`: complete for local development
- Phase 8 `Packaging`: substantially complete; packaged-backend smoke is green, but broader installed-workflow QA remains open
- Phase 9 `Cutover`: implemented; Tauri is the default launcher and PySide remains the fallback during burn-in

Primary remaining work:
- Broader live-IBKR workflow QA
- Longer-session desktop burn-in
- Installed-app validation beyond startup/backend smoke

## Features
- Landing page with workspace selection and IBKR connect control
- Portfolio Overview tab
  - IBKR connection status plus delayed/live market-data mode selection
  - Account summary KPIs: net liquidation, market value, cash, and day P&L
  - Positions table with FX-normalized values and weights
  - Portfolio composition and benchmarked performance charts
  - Diagnostics panel for account subscriptions, IB errors, cache stats, and local-history reset
- Research Overview tab
  - Single-ticker and synthetic-portfolio workflows
  - Synthetic weight normalization
  - Research performance, annualized volatility, and drawdown analysis
  - Optional benchmark overlay
- Risk tab
  - Historical VaR / CVaR and parametric VaR
  - Risk coverage tracking for partially covered portfolios
  - Daily and annualized volatility, max drawdown, beta, correlation, and Jensen alpha for USD base books
  - Concentration metrics and per-asset risk-contribution table
  - Excluded-assets reporting when history or base values are missing
- IV Surface tab
  - Mock or IBKR-backed implied-volatility surface
  - Delayed/live market-data support
  - Auto-follow of the research symbol for single-name research
- Shared infrastructure
  - Dedicated IB thread to keep the Qt UI responsive
  - Disk-backed cache for history, FX values, and FRED risk-free data
  - Base-currency FX normalization for positions, cash, and benchmarks
  - Local portfolio history store for fallback performance tracking
  - Mock mode for offline development and testing

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
# runtime-only alternative: pip install -e .
# or: pip install -r requirements.txt
```

Copy the env template:
```bash
copy .env.example .env
```

## IBKR / TWS Setup
- Use **Trader Workstation (TWS)** for live mode. IB Gateway is not wired up yet.
- In TWS: `Configure -> API -> Settings`
  - Enable `ActiveX and Socket Clients`
  - Optional: enable `Read-Only API` for extra safety
  - Set the socket port to match your environment: paper `7497`, live `7496`
  - Add `127.0.0.1` to trusted IPs if required
- Set matching values in `.env`: `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, optional `IB_ACCOUNT`
- `IB_MARKET_DATA_MODE=delayed` is the default and is recommended when you do not have live entitlements
- Optional: `IB_SNAPSHOT_TIMEOUT_SECONDS` controls how long the app waits for snapshot quotes

### Common failure modes
- **TWS not running / wrong port**: connection fails and the Overview status moves to `Error`
- **No live market data subscription**: delayed data is used when available
- **Historical pacing / missing bars**: warnings are shown and downstream analytics still run on covered assets
- **FX unavailable**: totals remain partially unconverted and warnings are shown

### Troubleshooting: connected but empty portfolio
If the app shows `Connected` but account values or positions are empty:
- Open **Diagnostics** on the Portfolio Overview tab and click `Run Diagnostics`
- Verify `Managed accounts` is non-empty
- Check that `IB_ACCOUNT` matches one of the managed accounts
- Use `Force Account Subscribe` to rerun the subscription flow
- Confirm TWS API settings, port selection, and whether you are connected to paper vs live

### IB threading model
All `ib_insync` calls are serialized on a dedicated IB thread so the Qt UI remains responsive and IB event processing stays on one loop/thread.

## Desktop app (default)
First-time frontend setup for the Tauri desktop path:

```powershell
cd frontend
npm install
cd ..
```

Default desktop launcher:

```powershell
.\.venv\Scripts\python.exe -m src.desktop_launcher
```

If you installed the package in editable mode, the same launcher is also available as:

```powershell
stratalab-desktop
```

The launcher defaults to Tauri. Use the explicit PySide fallback only when needed:

```powershell
.\.venv\Scripts\python.exe -m src.desktop_launcher --client pyside
```

Or via environment switch:

```powershell
$env:STRATALAB_DESKTOP_CLIENT="pyside"
.\.venv\Scripts\python.exe -m src.desktop_launcher
```

The legacy Qt entrypoint still exists as a direct fallback:

```powershell
.\.venv\Scripts\python.exe -m src.main
```

## Browser frontend
```powershell
cd frontend
npm install
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

## Tauri shell (local dev)
```powershell
cd frontend
npm install
$env:MOCK_DATA="true"
npm run tauri:dev
```

The Tauri shell launches the repo-local Python backend itself, waits for its local `/health` endpoint, keeps the splash visible until the frontend page has loaded, and only then shows the main window. Current limitations:
- `npm run tauri:dev` now sets `CARGO_TARGET_DIR` to a temp directory automatically to avoid Windows file-lock failures in `frontend/src-tauri/target`
- The shell prefers port `8000` but will fall back to another free localhost port if needed; set `STRATALAB_API_PORT` to force a specific port
- The local-dev shell still expects the repository checkout plus `.venv` to be present locally
- The browser-only frontend flow remains supported and unchanged

## Tauri packaging (Windows)
```powershell
cd frontend
npm install
npm run backend:smoke
npm run tauri:build
```

The production build now packages the Python backend with PyInstaller before invoking Tauri bundling, so the installed desktop app launches a bundled `stratalab-backend.exe` instead of relying on a repo-local `.venv`.

- `npm run backend:smoke` validates the generated backend executable by waiting for `/health`
- `npm run desktop:smoke` validates the default desktop launcher path by starting Tauri, waiting for the backend, and confirming the main frontend window reaches page load
- `npm run tauri:build` produces an NSIS installer; with the default wrapper this lands under `%TEMP%\stratalab-tauri-build\release\bundle\nsis\`
- Override `CARGO_TARGET_DIR` before running `npm run tauri:build` if you want the installer in a stable custom output directory
- Packaged runtime state lives under `%APPDATA%\com.stratalab.shell\runtime\`
- Backend startup diagnostics are written to `%APPDATA%\com.stratalab.shell\runtime\logs\backend-failure.txt`, `backend-stdout.log`, and `backend-stderr.log`
- PySide remains available as an explicit fallback client through `src.desktop_launcher --client pyside`

## Mock mode
Set `MOCK_DATA=true` in `.env` to use local sample data without IBKR.

## Tests
```bash
.venv\Scripts\python.exe -m pytest
cd frontend && npm run test
cd frontend && npm run build
cd frontend && npm run backend:smoke
cd frontend && npm run desktop:smoke
```

## Additional validation
```bash
cargo check --manifest-path frontend\src-tauri\Cargo.toml
cd frontend && npm run tauri:build
```

## Known limitations
- TWS is the supported live connector for now; IB Gateway is not supported yet
- Delayed mode avoids most entitlement issues, but some symbols/contracts can still return missing quotes
- Risk metrics are linear and history-based; option greeks and nonlinear scenario aggregation are not modeled yet
- Research mode is focused on stocks and synthetic stock portfolios, not a full multi-asset research platform
- IV surfaces are exploratory and depend on the quality of IBKR option-chain and greeks data

## Extending
- Add a fundamentals tab with a dedicated service layer
- Add factor and scenario-risk analytics to the Risk tab
- Persist research watchlists and saved synthetic baskets
- Add snapshot archive/export workflows
- Extend IV analytics with term structure and realized-vs-implied studies

## Repo layout
```
src/
  application/
  api/
  main.py
  ui/
    main_window.py
    landing_page.py
    tabs/
      overview_tab.py
      research_overview_tab.py
      risk_tab.py
      iv_surface_tab.py
    widgets/
      mpl_canvas.py
      worker.py
  services/
    app_context.py
    ibkr_client.py
    ib_thread.py
    market_data.py
    fx.py
    cache.py
    throttle.py
    mock_data.py
    portfolio_history_store.py
    risk_free_rate.py
    data_providers.py
    iv_surface_engine.py
  analytics/
    returns.py
    var.py
    risk_metrics.py
  models/
    app_mode.py
    portfolio.py
  utils/
    logging_config.py
    time.py
tests/
docs/
frontend/
sample_data/
```
