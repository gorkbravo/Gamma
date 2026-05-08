# Macro US/EU Trade And Country Compare Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add US/EU-first Macro depth with trade-partner context and country comparison modes while keeping Global lighter.

**Architecture:** Keep provider logic in backend Macro service/model/schema layers. Expose curated normalized `trade_partners` and `country_compare` payloads on the existing Macro snapshot so mode switching remains a single workspace load. Frontend modes render dense tables and summary panels without provider-native parsing.

**Tech Stack:** Python dataclasses, FastAPI/Pydantic schemas, Svelte, TypeScript, Vitest, pytest.

---

### Task 1: Backend Models And Snapshot Payload

**Files:**
- Modify: `src/models/macro.py`
- Modify: `src/api/schemas/macro.py`
- Test: `tests/test_macro.py`

- [ ] Write failing tests for `MacroSnapshotPayload.trade_partners` and `MacroSnapshotPayload.country_compare`.
- [ ] Add dataclasses for `MacroTradePartnerRow`, `MacroTradePartnerSummary`, `MacroCountryCompareRow`, and `MacroCountryCompareSummary`.
- [ ] Add Pydantic response models and include them in `MacroSnapshotResponseModel`.
- [ ] Run targeted pytest and verify the new tests pass.

### Task 2: Macro Service Curated US/EU Payloads

**Files:**
- Modify: `src/application/macro_service.py`
- Test: `tests/test_macro.py`

- [ ] Write failing tests that US/EU snapshots include ranked trade partners and country comparison rows with provenance.
- [ ] Implement static curated first-pass provider-backed placeholders: BEA/Census-style US trade partner rows, Eurostat-style EU rows, and IMF/OECD-style country comparison rows.
- [ ] Attach warnings that true live provider adapters remain optional/future where API keys are absent.
- [ ] Run targeted pytest and verify pass.

### Task 3: Frontend Types, Store, And Modes

**Files:**
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/stores/app.ts`
- Modify: `frontend/src/views/MacroView.test.ts`

- [ ] Write failing Vitest coverage for `trade_partners` and `country_compare` Macro modes.
- [ ] Extend `MacroMode` with `trade_partners` and `country_compare`.
- [ ] Ensure those modes do not prefetch unrelated chart series.
- [ ] Run targeted Vitest and verify pass after UI implementation.

### Task 4: Macro Mode Components

**Files:**
- Create: `frontend/src/components/MacroTradePartners.svelte`
- Create: `frontend/src/components/MacroCountryCompare.svelte`
- Modify: `frontend/src/views/MacroView.svelte`

- [ ] Add dense table/panel components using Gamma panel/table rules.
- [ ] Add two buttons to Macro mode bar and render the new components.
- [ ] Keep region/timeframe/theme controls shared; Global mode should show a lighter scope note.
- [ ] Run frontend tests and static design drift scan.

### Task 5: Provider Capability And Env Placeholders

**Files:**
- Modify: `.env.example`
- Modify: `src/application/provider_capability_registry.py`
- Modify: `README.md`

- [ ] Add optional placeholders for `BLS_API_KEY`, `BEA_API_KEY`, `WTO_API_KEY`, `UN_COMTRADE_API_KEY`, `IMF_API_KEY`, `OECD_API_KEY`, `EUROSTAT_API_KEY`, and `ECB_API_KEY`, with notes when keys are usually not required.
- [ ] Register active/planned capability metadata for the added Macro providers.
- [ ] Document that first-pass trade/country rows are curated/read-only and future live adapters should replace sample/static rows source-by-source.

### Task 6: Verification

**Files:**
- Changed files only.

- [ ] Run targeted backend tests: `.\.venv\Scripts\python.exe -m pytest tests/test_macro.py -q`.
- [ ] Run targeted frontend tests: `cd frontend; npm run test -- --run src/views/MacroView.test.ts src/lib/stores/macro.test.ts`.
- [ ] Run design drift scans on changed Svelte files.
- [ ] Report any failures or unverified areas.
