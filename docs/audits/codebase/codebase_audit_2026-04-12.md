# Gamma Codebase Audit — 2026-04-12

## Executive Summary

Gamma is a well-structured, read-only market research desktop application (FastAPI + Svelte + Tauri). The codebase is healthy: **all 141 Python tests and 66 frontend tests pass**. Architecture follows clean separation of concerns (routes → services → adapters → analytics). The main areas for improvement are around frontend component size, duplicate utility code, missing CI/CD, and sparse linting/formatting configuration.

**Note**: IBKR live data features were not tested (TWS not running). Any IBKR-dependent paths that would fail in this state are expected and not flagged as bugs.

---

## 1. Test Suite Health

| Suite | Tests | Status | Duration |
|-------|-------|--------|----------|
| Python (pytest) | 141 | **All passing** | 77s |
| Frontend (vitest) | 66 | **All passing** | 3.4s |

**Warnings observed:**
- 3 deprecation warnings from `edgartools` (v5.x modules will be removed in v6.0 — `html_documents`, `html`, `htmltools`)
- 1 Svelte CSS warning: unused selector `.basket-card p` in `CryptoView.svelte:1462`

---

## 2. Architecture Overview

```
Svelte Frontend (25+ components, 8 views)
    ↕ HTTP/JSON
Tauri Shell (Rust, desktop window management)
    ↕ localhost:8000
FastAPI Backend
    ├── API Routes (10 modules)
    ├── Application Services (business logic)
    ├── Data Adapters (IBKR, FRED, CoinGecko, Polymarket, Kalshi, SEC Edgar)
    └── Analytics (returns, risk metrics, VaR)
```

**Strengths:**
- Clean layered architecture with dependency injection via `runtime.py`
- Pydantic validation on all API boundaries
- Immutable domain models (`@dataclass(frozen=True)`)
- Provenance metadata on all data records (`source_provider`, `retrieved_at`, `origin`)
- Good test isolation (mock services, tmp_path fixtures)

---

## 3. Critical Findings

### 3.1 Oversized Frontend Components

Several components far exceed maintainable size:

| File | Lines | Concern |
|------|-------|---------|
| `FundamentalsView.svelte` | 1,752 | Should split into sub-components |
| `CryptoView.svelte` | 1,701 | 32+ reactive statements, cascading recalculations |
| `PredictionMarketsView.svelte` | 1,448 | Could extract screener/detail panels |
| `App.svelte` | 1,435 | Orchestrates everything — workspace, tabs, copilot, keybindings |
| `ResearchView.svelte` | 1,233 | Mixed scope building + display logic |

**Risk:** Hard to maintain, test, and debug. Reactive chains in CryptoView can trigger cascading recalculations.

### 3.2 Monolithic Store File

`frontend/src/lib/stores/app.ts` — **1,790 lines with 96+ exports**. Contains both state definitions and async operations for every domain. Should be split by domain (portfolio, research, crypto, macro, etc.).

### 3.3 Duplicate Utility Functions

**5 separate implementations** of float-conversion helpers across the backend:

| Location | Function | Difference |
|----------|----------|------------|
| `src/api/schemas/portfolio.py:186` | `_to_float()` | NaN via `value != value` |
| `src/api/schemas/risk.py:147` | `_to_float()` | Uses `np.isnan()`, bare `except` |
| `src/application/copilot_context_helpers.py:523` | `_as_float()` | Catches `TypeError, ValueError` |
| `src/services/crypto_adapters.py:840` | `_as_float()` | Another variant |
| `src/services/mock_copilot_provider.py` | `_as_float()` | Nested duplicate |

Similarly, `_is_cash()` / `_is_cash_position()` and `_is_valid_currency_code()` are duplicated across modules.

**Recommendation:** Consolidate into `src/utils/converters.py` and `src/utils/validators.py`.

### 3.4 Hardcoded Developer Identity in Source

`src/services/fundamentals_adapters.py:310-312`:
```python
# TODO: Replace this development-time SEC identity fallback
name = os.getenv("GAMMA_SEC_USER_NAME", "Gorka Bravo")
email = os.getenv("GAMMA_SEC_USER_EMAIL", "gorka.bravo1@gmail.com")
```

Personal information as hardcoded defaults. SEC requests from other users would be made under this identity if env vars aren't set.

---

## 4. High-Priority Findings

### 4.1 No CI/CD Pipeline

No GitHub Actions, GitLab CI, or any automated pipeline exists. All testing and building is manual/developer-driven. The build scripts in `frontend/scripts/` handle PyInstaller packaging and Tauri builds but nothing runs automatically on push/PR.

### 4.2 No Linting or Formatting Configuration

- No ESLint, Prettier, Ruff, Black, or any formatter configured
- No pre-commit hooks (no `.husky/`, no `pre-commit-config.yaml`)
- TypeScript strict mode is enabled (good) but no style enforcement beyond that

### 4.3 No Error Boundaries (Frontend)

If any Svelte component throws, the entire app crashes. No error boundary wrapper or fallback UI exists. This is especially risky given the complexity of chart components and external data rendering.

### 4.4 edgartools Deprecation Warnings

Three deprecation warnings from edgartools v5.x modules that will be removed in v6.0:
- `edgar.files.html_documents` → use `edgar.documents.HTMLParser`
- `edgar.files.html` → same migration
- `edgar.files.htmltools` → same migration

The dependency is pinned `>=5.28.4,<6` so this won't break unexpectedly, but migration planning is needed before v6 lands.

### 4.5 Sparse Accessibility

Only ~55 ARIA attributes across the entire frontend. Most interactive elements, SVG charts, and data tables lack proper ARIA roles and labels. Keyboard navigation exists (good keybinding system) but screen reader support is minimal.

---

## 5. Medium-Priority Findings

### 5.1 Mixed Python Type Syntax

Old-style `Dict`, `List`, `Optional` from `typing` mixed with modern `dict`, `list`, `| None` (PEP 604). Found in:
- `src/models/portfolio.py`
- `src/analytics/returns.py`
- `src/application/risk_service.py`
- `src/services/app_context.py`

### 5.2 Untyped Dictionaries in Copilot Helpers

`src/application/copilot_context_helpers.py` uses `dict[str, Any]` extensively for internal transformations, losing type information. Functions like `_position_summary()`, `_research_weight_summary()` pass around untyped dicts.

### 5.3 No Authentication Middleware

All API endpoints are completely open. Appropriate for a desktop app (localhost only), but the architecture has no auth layer if the app ever needs to serve over a network. CORS is correctly restricted to localhost origins.

### 5.4 No Rate Limiting on External API Calls

External API calls have timeouts (good) but no rate limiting at the HTTP layer. A `ThrottleQueue` exists in services but isn't integrated with API routes.

### 5.5 Frontend Test Coverage Gaps

18 of ~69 frontend files have tests (~26% file coverage). Missing test coverage for:
- Most view components (only Macro and Crypto views tested)
- Chart components
- Tauri/Rust shell code
- Drag-and-drop interactions
- Error/edge-case rendering

### 5.6 Silent Failure Patterns

Several Python functions return empty collections on `None` input instead of raising:
```python
def snapshot_identity_map(snapshot: PortfolioSnapshot | None) -> dict:
    if snapshot is None:
        return {}  # Silent empty return
```

This can mask bugs where `None` shouldn't occur.

### 5.7 Unused CSS Selector

`CryptoView.svelte:1462` — `.basket-card p` selector is unused (flagged by Svelte compiler during test run).

### 5.8 No Code Coverage Tracking

Neither Python (no `.coveragerc`, no `pytest-cov`) nor frontend (no coverage config in vitest) have coverage reporting configured. Unknown actual line/branch coverage.

---

## 6. Low-Priority / Minor Findings

| Finding | Location | Notes |
|---------|----------|-------|
| No Docker/containerization | Project root | Desktop-only app, not cloud-targeted |
| Cache key collision potential | `src/services/cache.py` | `make_key()` uses `_` separator; "a/b" and "a_b" collide. Low risk since inputs are controlled. |
| Provenance metadata duplication | All `src/models/*.py` | 4 fields (`source_provider`, `retrieved_at`, `origin`, `transformation_note`) repeated across 30+ dataclasses. Could use a base mixin. |
| No centralized constants | Scattered | Magic strings like "Gaussian", "Bootstrap" in var.py; no enums module |
| Error messages may leak details | `src/services/openai_copilot_provider.py` | Raw OpenAI error responses returned to client |
| JSON parsing has no size limits | Various adapters | Large API responses could cause memory issues |

---

## 7. Positive Observations

- **Zero type assertions** in TypeScript — no `as any`, `as unknown`, `@ts-ignore`, or `@ts-expect-error` found
- **No SQL injection risk** — no SQL databases used at all
- **No command injection** — no `os.system()`, `subprocess`, or `eval()` calls
- **Safe path handling** — all file operations use `pathlib.Path`, preventing traversal attacks
- **API keys properly managed** — stored in env vars, not hardcoded (except the SEC identity fallback)
- **Thread safety** — proper locks on shared state (portfolio history store, cache)
- **Timeouts on all external calls** — every HTTP adapter has explicit timeout configuration
- **View-model pattern** — `frontend/src/lib/view-models/` cleanly separates domain logic from components
- **Comprehensive backend test suite** — 141 tests covering API endpoints, services, adapters, analytics, and edge cases

---

## 8. Recommended Action Items

### Quick Wins
1. Fix unused CSS selector in `CryptoView.svelte:1462`
2. Remove hardcoded SEC identity defaults or make them clearly placeholder
3. Consolidate `_to_float()` / `_as_float()` into a shared utility

### Short-Term
4. Add ESLint + Prettier for frontend, Ruff for Python backend
5. Add pre-commit hooks (formatting, linting, type checks)
6. Add Svelte error boundary wrapper for graceful failure
7. Add code coverage reporting to both test suites
8. Plan edgartools v6 migration (address deprecation warnings)

### Medium-Term
9. Split oversized components (FundamentalsView, CryptoView, App.svelte)
10. Split `stores/app.ts` by domain
11. Set up GitHub Actions CI (test, lint, type-check on PR)
12. Standardize Python type annotations to modern syntax
13. Add frontend tests for untested views

### Long-Term
14. Add E2E tests (Playwright for Tauri desktop)
15. Add accessibility audit and ARIA improvements
16. Consider auth middleware for potential network deployment
17. Add rate limiting middleware to API routes
