# Equity Research Strategy Lab Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic Research tab with Equity Research and Strategy Lab, and add the first read-only Strategy Lab composition contract for live Gamma research objects.

**Architecture:** Keep the existing Research service and `ResearchView.svelte` behavior stable while introducing explicit Equity Research and Strategy Lab navigation surfaces. Add a shared research-object/composition model on the backend, expose it through `/research/strategy-lab/compose`, then wire frontend types, stores, and view-model helpers around that contract. The first UI split should reuse the existing Research view internals with mode restrictions before deeper component extraction.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, pandas return-stream analytics, Svelte 5, TypeScript, Vitest, pytest.

---

## Scope Check

This plan is one coherent vertical slice:

- navigation exposes two tabs;
- Equity Research preserves the current overview/scope workflows;
- Strategy Lab owns imports, compare/analyze, saved runs, and composition;
- backend composition handles return-capable objects only and records lens/overlay objects as read-only context.

It does not implement strategy recipes or sandboxed code execution.

## File Structure

- Modify `frontend/src/lib/api/types.ts`: add tab ids, modes, research-object and composition response types.
- Modify `frontend/src/lib/navigation.ts`: replace top-level `research` tab with `equity_research` and `strategy_lab`, add mode registries, and add legacy path aliases.
- Modify `frontend/src/lib/navigation.test.ts`: cover default tab order, old-order normalization, mode shortcuts, and legacy `/Research/...` path mapping.
- Modify `frontend/src/lib/view-models/research.ts`: split `ResearchMode` into `EquityResearchMode` and `StrategyLabMode`, add saved-object classification, add research-object builders.
- Modify `frontend/src/lib/view-models/research.test.ts`: cover mode helpers, saved-object classification, and research-object generation.
- Modify `src/models/research_lab.py`: add shared research-object dataclasses and composition dataclasses.
- Modify `src/application/research_service.py`: add `compose_strategy_lab`, return-stream resolution, lens/overlay validation, and read-only warnings.
- Modify `src/api/schemas/research.py`: add Pydantic request/response models for research objects and composition.
- Modify `src/api/routes/research.py`: add `POST /research/strategy-lab/compose`.
- Modify `tests/test_research_v2.py`: add backend composition coverage.
- Modify `frontend/src/lib/stores/app.ts`: add composition store/action, new Copilot domains, and context validation for Equity Research and Strategy Lab.
- Modify `frontend/src/lib/stores/app.test.ts`: add composition API tests and Copilot context tests.
- Create `frontend/src/views/EquityResearchView.svelte`: wrapper around the shared research surface in equity mode.
- Create `frontend/src/views/StrategyLabView.svelte`: wrapper around the shared research surface in strategy mode.
- Modify `frontend/src/views/ResearchView.svelte`: make it an internal shared surface with a `surface` prop and mode lists for each new tab.
- Modify `frontend/src/App.svelte`: maintain separate active modes, render the two new views, and map legacy active tab state to Equity Research.
- Modify `frontend/src/KeyBindingsWindow.test.ts` if labels or tab counts are asserted.
- Modify `src/application/copilot_context_helpers.py`, `src/services/openai_copilot_provider.py`, and `tests/test_copilot.py` only if backend Copilot hard-codes domain labels.

---

### Task 1: Navigation Split

**Files:**
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/lib/navigation.test.ts`
- Modify: `frontend/src/KeyBindingsWindow.test.ts`

- [ ] **Step 1: Write failing navigation tests**

Update `frontend/src/lib/navigation.test.ts` expected research order and mode assertions:

```ts
expect(getDefaultTabOrder("research")).toEqual([
  "sitrep",
  "equity_research",
  "strategy_lab",
  "macro",
  "prediction_markets",
  "crypto",
  "fundamentals",
  "commodities",
  "maritime",
  "copilot",
  "risk",
  "iv",
]);

expect(getTabModes("equity_research").map((mode) => mode.id)).toEqual([
  "overview",
  "scope_analysis",
  "comparables",
  "scenario_context",
  "saved_equity_research",
]);

expect(getTabModes("strategy_lab").map((mode) => mode.id)).toEqual([
  "composer",
  "backtest_analyze",
  "regime_stress",
  "imports",
  "saved_runs",
]);

const orderState = normalizeWorkspaceTabOrderState(null);
expect(resolveNavigationPath("research", orderState, "/Research")?.tab.id).toBe("equity_research");
expect(resolveNavigationPath("research", orderState, "/Research/Scope")?.mode?.id).toBe("scope_analysis");
expect(resolveNavigationPath("research", orderState, "/Research/Strategy")?.tab.id).toBe("strategy_lab");
expect(resolveNavigationPath("research", orderState, "/Strategy Lab/Imports")?.mode?.id).toBe("imports");
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/navigation.test.ts
```

Expected: FAIL because `equity_research` and `strategy_lab` are not registered.

- [ ] **Step 3: Add new tab ids and modes**

In `frontend/src/lib/api/types.ts`, replace the `research` tab id with the new ids:

```ts
export type TabId =
  | "portfolio"
  | "sitrep"
  | "equity_research"
  | "strategy_lab"
  | "macro"
  | "commodities"
  | "prediction_markets"
  | "crypto"
  | "fundamentals"
  | "maritime"
  | "copilot"
  | "risk"
  | "iv";

export type EquityResearchMode =
  | "overview"
  | "scope_analysis"
  | "comparables"
  | "scenario_context"
  | "saved_equity_research";

export type StrategyLabMode =
  | "composer"
  | "backtest_analyze"
  | "regime_stress"
  | "imports"
  | "saved_runs";
```

In `frontend/src/lib/navigation.ts`, replace the Research tab definition and mode registry:

```ts
research: [
  { id: "sitrep", label: "SITREP", pinned: true, defaultIndex: 0 },
  { id: "equity_research", label: "EQUITY RESEARCH", pinned: false, defaultIndex: 1 },
  { id: "strategy_lab", label: "STRATEGY LAB", pinned: false, defaultIndex: 2 },
  { id: "macro", label: "MACRO", pinned: false, defaultIndex: 3 },
  { id: "prediction_markets", label: "PREDICTION MARKETS", pinned: false, defaultIndex: 4 },
  { id: "crypto", label: "CRYPTO", pinned: false, defaultIndex: 5 },
  { id: "fundamentals", label: "FUNDAMENTALS", pinned: false, defaultIndex: 6 },
  { id: "commodities", label: "COMMODITIES", pinned: false, defaultIndex: 7 },
  { id: "maritime", label: "SEALANES", pinned: false, defaultIndex: 8 },
  { id: "copilot", label: "COPILOT", pinned: false, defaultIndex: 9 },
  { id: "risk", label: "RISK", pinned: false, defaultIndex: 10 },
  { id: "iv", label: "OPTIONS", pinned: false, defaultIndex: 11 },
],
```

```ts
equity_research: defineTabModes([
  { id: "overview", label: "Overview", defaultIndex: 0 },
  { id: "scope_analysis", label: "Scope Analysis", defaultIndex: 1 },
  { id: "comparables", label: "Comparables", defaultIndex: 2 },
  { id: "scenario_context", label: "Scenario / Context", defaultIndex: 3 },
  { id: "saved_equity_research", label: "Saved Equity Research", defaultIndex: 4 },
]),
strategy_lab: defineTabModes([
  { id: "composer", label: "Composer", defaultIndex: 0 },
  { id: "backtest_analyze", label: "Backtest / Analyze", defaultIndex: 1 },
  { id: "regime_stress", label: "Regime / Stress", defaultIndex: 2 },
  { id: "imports", label: "Imports", defaultIndex: 3 },
  { id: "saved_runs", label: "Saved Runs", defaultIndex: 4 },
]),
```

- [ ] **Step 4: Add legacy route and saved-order compatibility**

Add helpers in `frontend/src/lib/navigation.ts`:

```ts
const LEGACY_TAB_ALIASES: Partial<Record<WorkspaceMode, Record<string, TabId>>> = {
  research: {
    research: "equity_research",
  },
};

const LEGACY_RESEARCH_MODE_ALIASES: Record<string, { tabId: TabId; modeId: string }> = {
  overview: { tabId: "equity_research", modeId: "overview" },
  scope_analysis: { tabId: "equity_research", modeId: "scope_analysis" },
  strategy_lab: { tabId: "strategy_lab", modeId: "imports" },
  compare_scenario: { tabId: "strategy_lab", modeId: "backtest_analyze" },
  saved_research: { tabId: "strategy_lab", modeId: "saved_runs" },
};

function normalizeLegacyTabId(mode: WorkspaceMode, tabId: unknown): unknown {
  if (typeof tabId !== "string") return tabId;
  return LEGACY_TAB_ALIASES[mode]?.[tabId] ?? tabId;
}
```

Use `normalizeLegacyTabId` inside `normalizeWorkspaceTabOrder` before `isWorkspaceTab`.

In `resolveNavigationPath`, special-case `/Research/<mode>`:

```ts
if (mode === "research" && matchesNavigationSegment({ id: "research", label: "Research" }, tabSegment)) {
  const legacyModeKey = normalizeNavigationSearchTerm(modeSegment ?? "").replace(/\s+/g, "_");
  const mapped = LEGACY_RESEARCH_MODE_ALIASES[legacyModeKey];
  if (mapped) {
    const tab = WORKSPACE_TAB_LOOKUP.research.get(mapped.tabId);
    const routeMode = getTabModes(mapped.tabId).find((candidate) => candidate.id === mapped.modeId) ?? null;
    return tab ? { tab, mode: routeMode } : null;
  }
  const tab = WORKSPACE_TAB_LOOKUP.research.get("equity_research");
  return tab ? { tab, mode: null } : null;
}
```

- [ ] **Step 5: Run navigation tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/navigation.test.ts src/KeyBindingsWindow.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/lib/api/types.ts frontend/src/lib/navigation.ts frontend/src/lib/navigation.test.ts frontend/src/KeyBindingsWindow.test.ts
git commit -m "Split research navigation into equity and strategy tabs"
```

---

### Task 2: Backend Research Object And Composition Contract

**Files:**
- Modify: `src/models/research_lab.py`
- Modify: `src/application/research_service.py`
- Modify: `src/api/schemas/research.py`
- Modify: `src/api/routes/research.py`
- Modify: `tests/test_research_v2.py`

- [ ] **Step 1: Write failing backend tests**

Add tests to `tests/test_research_v2.py`:

```python
def test_strategy_lab_composes_weighted_return_objects(tmp_path):
    service = _service(tmp_path)
    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Live Gamma Composition",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:a",
                        object_type="strategy_return_stream",
                        display_name="Strategy A",
                        source_tab="strategy_lab",
                        source_mode="imports",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=0.6,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:b",
                        object_type="strategy_return_stream",
                        display_name="Strategy B",
                        source_tab="strategy_lab",
                        source_mode="imports",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.00),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.00),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.02),
                        ],
                    ),
                    weight=0.4,
                ),
            ],
            lenses=[],
            overlays=[],
            benchmark_object=None,
            min_observations=5,
        )
    )

    assert result.name == "Live Gamma Composition"
    assert list(result.leg_contributions.keys()) == ["Strategy A", "Strategy B"]
    assert len(result.returns) == 5
    assert result.warnings[0].startswith("Strategy Lab compositions are read-only research")
    assert result.metrics.observation_count == 5


def test_strategy_lab_rejects_lens_as_weighted_leg(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(ResearchValidationError) as exc_info:
        service.compose_strategy_lab(
            StrategyLabCompositionRequest(
                name="Bad Composition",
                legs=[
                    StrategyLabCompositionLeg(
                        object=GammaResearchObject(
                            object_id="macro:inflation-shock",
                            object_type="macro_regime",
                            display_name="Inflation Shock",
                            source_tab="macro",
                            source_mode="events_regimes",
                            resolver_capabilities=["lens"],
                        ),
                        weight=1.0,
                    )
                ],
                lenses=[],
                overlays=[],
                benchmark_object=None,
                min_observations=5,
            )
        )

    assert "cannot be used as a weighted return leg" in exc_info.value.errors[0]
```

Import the new classes at the top of the test file:

```python
from src.models.research_lab import (
    GammaResearchObject,
    ResearchObjectReturnPoint,
    StrategyLabCompositionLeg,
    StrategyLabCompositionRequest,
)
```

- [ ] **Step 2: Run the failing backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_research_v2.py -q
```

Expected: FAIL because the composition classes do not exist.

- [ ] **Step 3: Add dataclasses**

In `src/models/research_lab.py`, add:

```python
ResolverCapability = Literal["return_leg", "benchmark", "lens", "overlay", "reference_only"]


@dataclass(frozen=True)
class ResearchObjectReturnPoint:
    timestamp: str
    value: float


@dataclass(frozen=True)
class GammaResearchObject:
    object_id: str
    object_type: str
    display_name: str
    source_tab: str
    source_mode: str | None = None
    resolver_capabilities: list[ResolverCapability] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    constituents: list[dict[str, Any]] = field(default_factory=list)
    weights: list[dict[str, Any]] = field(default_factory=list)
    available_start: str | None = None
    available_end: str | None = None
    provider_summary: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    return_points: list[ResearchObjectReturnPoint] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyLabCompositionLeg:
    object: GammaResearchObject
    weight: float


@dataclass(frozen=True)
class StrategyLabCompositionRequest:
    name: str
    legs: list[StrategyLabCompositionLeg] = field(default_factory=list)
    lenses: list[GammaResearchObject] = field(default_factory=list)
    overlays: list[GammaResearchObject] = field(default_factory=list)
    benchmark_object: GammaResearchObject | None = None
    min_observations: int = 5


@dataclass(frozen=True)
class StrategyLabCompositionResult(StrategyLabAnalysisResult):
    leg_contributions: dict[str, float] = field(default_factory=dict)
    lenses: list[GammaResearchObject] = field(default_factory=list)
    overlays: list[GammaResearchObject] = field(default_factory=list)
```

- [ ] **Step 4: Add service implementation**

In `src/application/research_service.py`, import the new classes and add:

```python
    def compose_strategy_lab(self, request: StrategyLabCompositionRequest) -> StrategyLabCompositionResult:
        warnings: list[str] = [
            "Strategy Lab compositions are read-only research runs; Gamma does not rebalance or modify broker portfolios."
        ]
        retrieved_at = now_utc()
        if not request.legs:
            raise ResearchValidationError(["At least one weighted return leg is required."])

        weighted_returns: list[pd.Series] = []
        normalized_weights = self._normalize_composition_weights(request.legs)
        for leg, normalized_weight in zip(request.legs, normalized_weights, strict=True):
            if "return_leg" not in leg.object.resolver_capabilities:
                raise ResearchValidationError(
                    [f"{leg.object.display_name} cannot be used as a weighted return leg."]
                )
            returns = self._research_object_return_series(leg.object, warnings)
            if returns.empty:
                raise ResearchValidationError([f"{leg.object.display_name} has no usable return stream."])
            weighted_returns.append(returns.rename(leg.object.display_name) * normalized_weight)
            warnings.extend(leg.object.warnings)

        aligned = pd.concat(weighted_returns, axis=1, join="inner").dropna()
        if len(aligned) < max(int(request.min_observations), 2):
            raise ResearchValidationError(
                [f"Composition needs at least {request.min_observations} overlapping observations."]
            )
        composition_returns = aligned.sum(axis=1)

        benchmark_returns = pd.Series(dtype=float)
        if request.benchmark_object is not None:
            if "benchmark" not in request.benchmark_object.resolver_capabilities and "return_leg" not in request.benchmark_object.resolver_capabilities:
                warnings.append(f"Benchmark object {request.benchmark_object.display_name} is not return-resolvable.")
            else:
                benchmark_returns = self._research_object_return_series(request.benchmark_object, warnings)

        analysis = analyze_return_stream(
            composition_returns,
            benchmark_returns=benchmark_returns if not benchmark_returns.empty else None,
            min_observations=max(int(request.min_observations), 2),
        )
        contribution_totals = {
            column: float((1.0 + aligned[column]).prod() - 1.0)
            for column in aligned.columns
        }
        return StrategyLabCompositionResult(
            name=str(request.name or "").strip() or "Strategy Lab Composition",
            value_kind="return",
            benchmark_column=request.benchmark_object.display_name if request.benchmark_object else None,
            benchmark_value_kind="return",
            returns=analysis.returns,
            equity_curve=analysis.equity_curve,
            drawdowns=analysis.drawdowns,
            benchmark_returns=benchmark_returns,
            benchmark_equity_curve=equity_curve_from_returns(benchmark_returns),
            metrics=analysis.metrics,
            rolling_points=analysis.rolling_points,
            monthly_returns=analysis.monthly_returns,
            annual_returns=analysis.annual_returns,
            warnings=list(dict.fromkeys(warnings)),
            source_provider="gamma_strategy_lab",
            retrieved_at=retrieved_at,
            origin="research_service.strategy_lab.compose",
            transformation_note=(
                "Weighted Gamma research objects are resolved to return streams, aligned on shared timestamps, "
                "and summed as a read-only research composition."
            ),
            freshness_label=FreshnessLabel.DERIVED.value,
            leg_contributions=contribution_totals,
            lenses=list(request.lenses),
            overlays=list(request.overlays),
        )

    @staticmethod
    def _normalize_composition_weights(legs: list[StrategyLabCompositionLeg]) -> list[float]:
        raw = [float(leg.weight) for leg in legs]
        if any(weight < 0 for weight in raw):
            raise ResearchValidationError(["Composition leg weights must be non-negative."])
        total = sum(raw)
        if total <= 0:
            raise ResearchValidationError(["Composition leg weights must sum to a positive value."])
        return [weight / total for weight in raw]

    @staticmethod
    def _research_object_return_series(row: GammaResearchObject, warnings: list[str]) -> pd.Series:
        values: dict[pd.Timestamp, float] = {}
        for point in row.return_points:
            timestamp = pd.to_datetime(point.timestamp, errors="coerce")
            if pd.isna(timestamp):
                warnings.append(f"{row.display_name}: dropped return point with invalid timestamp.")
                continue
            values[pd.Timestamp(timestamp).normalize()] = float(point.value)
        if not values:
            return pd.Series(dtype=float)
        return clean_return_series(pd.Series(values).sort_index().astype(float))
```

- [ ] **Step 5: Add API schemas and route**

In `src/api/schemas/research.py`, add Pydantic models mirroring the dataclasses and a response model that extends `StrategyLabAnalyzeResponseModel`:

```python
class ResearchObjectReturnPointModel(BaseModel):
    timestamp: datetime
    value: float

    def to_domain(self) -> ResearchObjectReturnPoint:
        return ResearchObjectReturnPoint(timestamp=self.timestamp.isoformat(), value=self.value)


class GammaResearchObjectModel(BaseModel):
    object_id: str
    object_type: str
    display_name: str
    source_tab: str
    source_mode: str | None = None
    resolver_capabilities: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    constituents: list[dict[str, Any]] = Field(default_factory=list)
    weights: list[dict[str, Any]] = Field(default_factory=list)
    available_start: str | None = None
    available_end: str | None = None
    provider_summary: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    return_points: list[ResearchObjectReturnPointModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: GammaResearchObject) -> "GammaResearchObjectModel":
        return cls(
            object_id=row.object_id,
            object_type=row.object_type,
            display_name=row.display_name,
            source_tab=row.source_tab,
            source_mode=row.source_mode,
            resolver_capabilities=list(row.resolver_capabilities),
            symbols=list(row.symbols),
            constituents=[dict(item) for item in row.constituents],
            weights=[dict(item) for item in row.weights],
            available_start=row.available_start,
            available_end=row.available_end,
            provider_summary=row.provider_summary,
            provenance=dict(row.provenance),
            warnings=list(row.warnings),
            return_points=[
                ResearchObjectReturnPointModel(timestamp=pd.Timestamp(point.timestamp).to_pydatetime(), value=point.value)
                for point in row.return_points
            ],
        )

    def to_domain(self) -> GammaResearchObject:
        return GammaResearchObject(
            object_id=self.object_id,
            object_type=self.object_type,
            display_name=self.display_name,
            source_tab=self.source_tab,
            source_mode=self.source_mode,
            resolver_capabilities=list(self.resolver_capabilities),
            symbols=list(self.symbols),
            constituents=[dict(item) for item in self.constituents],
            weights=[dict(item) for item in self.weights],
            available_start=self.available_start,
            available_end=self.available_end,
            provider_summary=self.provider_summary,
            provenance=dict(self.provenance),
            warnings=list(self.warnings),
            return_points=[point.to_domain() for point in self.return_points],
        )
```

```python
class StrategyLabCompositionLegModel(BaseModel):
    object: GammaResearchObjectModel
    weight: float

    def to_domain(self) -> StrategyLabCompositionLeg:
        return StrategyLabCompositionLeg(object=self.object.to_domain(), weight=self.weight)


class StrategyLabCompositionRequestModel(BaseModel):
    name: str = "Strategy Lab Composition"
    legs: list[StrategyLabCompositionLegModel] = Field(default_factory=list)
    lenses: list[GammaResearchObjectModel] = Field(default_factory=list)
    overlays: list[GammaResearchObjectModel] = Field(default_factory=list)
    benchmark_object: GammaResearchObjectModel | None = None
    min_observations: int = 5

    def to_domain(self) -> StrategyLabCompositionRequest:
        return StrategyLabCompositionRequest(
            name=self.name,
            legs=[leg.to_domain() for leg in self.legs],
            lenses=[item.to_domain() for item in self.lenses],
            overlays=[item.to_domain() for item in self.overlays],
            benchmark_object=self.benchmark_object.to_domain() if self.benchmark_object else None,
            min_observations=max(int(self.min_observations), 2),
        )


class StrategyLabCompositionResponseModel(StrategyLabAnalyzeResponseModel):
    leg_contributions: dict[str, float] = Field(default_factory=dict)
    lenses: list[GammaResearchObjectModel] = Field(default_factory=list)
    overlays: list[GammaResearchObjectModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: StrategyLabCompositionResult) -> "StrategyLabCompositionResponseModel":
        base = StrategyLabAnalyzeResponseModel.from_domain(row).model_dump()
        return cls(
            **base,
            leg_contributions=dict(row.leg_contributions),
            lenses=[GammaResearchObjectModel.from_domain(item) for item in row.lenses],
            overlays=[GammaResearchObjectModel.from_domain(item) for item in row.overlays],
        )
```

In `src/api/routes/research.py`, add:

```python
@router.post("/research/strategy-lab/compose", response_model=StrategyLabCompositionResponseModel)
def compose_strategy_lab(
    payload: StrategyLabCompositionRequestModel,
    request: Request,
) -> StrategyLabCompositionResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.compose_strategy_lab(payload.to_domain())
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return StrategyLabCompositionResponseModel.from_domain(result)
```

- [ ] **Step 6: Run backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_research_v2.py tests/test_research_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/models/research_lab.py src/application/research_service.py src/api/schemas/research.py src/api/routes/research.py tests/test_research_v2.py
git commit -m "Add strategy lab research object composition"
```

---

### Task 3: Frontend Types, Stores, And View-Model Helpers

**Files:**
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/stores/app.ts`
- Modify: `frontend/src/lib/stores/app.test.ts`
- Modify: `frontend/src/lib/view-models/research.ts`
- Modify: `frontend/src/lib/view-models/research.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Add to `frontend/src/lib/view-models/research.test.ts`:

```ts
it("classifies saved research for equity and strategy surfaces", () => {
  expect(classifySavedResearchSurface({ object_type: "scope_analysis" } as SavedResearchItem)).toBe("equity");
  expect(classifySavedResearchSurface({ object_type: "strategy_lab" } as SavedResearchItem)).toBe("strategy");
  expect(classifySavedResearchSurface({ object_type: "strategy_composition" } as SavedResearchItem)).toBe("strategy");
});

it("builds a return-leg research object from the latest scope result", () => {
  const object = buildResearchObjectFromScopeResult(makeResearchResult("synthetic_portfolio", [
    { symbol: "AAPL", weight: 0.6 },
    { symbol: "MSFT", weight: 0.4 },
  ]));

  expect(object?.object_type).toBe("equity_scope");
  expect(object?.resolver_capabilities).toContain("return_leg");
  expect(object?.return_points.length).toBeGreaterThan(0);
});
```

Add to `frontend/src/lib/stores/app.test.ts` with the existing API mock pattern:

```ts
it("posts strategy lab composition payloads", async () => {
  mockFetchJson({
    name: "Composition",
    value_kind: "return",
    benchmark_column: null,
    benchmark_value_kind: "return",
    metrics: makeResearchMetrics(),
    returns_points: [],
    equity_curve_points: [],
    drawdown_points: [],
    benchmark_points: [],
    benchmark_equity_curve_points: [],
    rolling_points: [],
    monthly_returns: [],
    annual_returns: [],
    warnings: ["Strategy Lab compositions are read-only research runs."],
    source_provider: "gamma_strategy_lab",
    retrieved_at: "2026-05-18T00:00:00Z",
    origin: "research_service.strategy_lab.compose",
    transformation_note: null,
    freshness_label: "derived",
    leg_contributions: {},
    lenses: [],
    overlays: [],
  });

  await composeStrategyLab({
    name: "Composition",
    legs: [],
    lenses: [],
    overlays: [],
    benchmarkObject: null,
    minObservations: 5,
  });

  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/research/strategy-lab/compose"), expect.any(Object));
});
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/view-models/research.test.ts src/lib/stores/app.test.ts
```

Expected: FAIL because the helper and store action do not exist.

- [ ] **Step 3: Add API types**

In `frontend/src/lib/api/types.ts`, add:

```ts
export type ResearchObjectResolverCapability = "return_leg" | "benchmark" | "lens" | "overlay" | "reference_only";

export interface ResearchObjectReturnPoint {
  timestamp: string;
  value: number;
}

export interface GammaResearchObject {
  object_id: string;
  object_type: string;
  display_name: string;
  source_tab: string;
  source_mode: string | null;
  resolver_capabilities: ResearchObjectResolverCapability[];
  symbols: string[];
  constituents: Record<string, unknown>[];
  weights: Record<string, unknown>[];
  available_start: string | null;
  available_end: string | null;
  provider_summary: string | null;
  provenance: Record<string, unknown>;
  warnings: string[];
  return_points: ResearchObjectReturnPoint[];
}

export interface StrategyLabCompositionLegInput {
  object: GammaResearchObject;
  weight: number;
}

export interface StrategyLabCompositionResult extends StrategyLabResult {
  leg_contributions: Record<string, number>;
  lenses: GammaResearchObject[];
  overlays: GammaResearchObject[];
}
```

- [ ] **Step 4: Add view-model helpers**

In `frontend/src/lib/view-models/research.ts`, add:

```ts
export type EquityResearchMode = "overview" | "scope_analysis" | "comparables" | "scenario_context" | "saved_equity_research";
export type StrategyLabMode = "composer" | "backtest_analyze" | "regime_stress" | "imports" | "saved_runs";
export type ResearchMode = EquityResearchMode | StrategyLabMode;

export function classifySavedResearchSurface(item: SavedResearchItem): "equity" | "strategy" | "unknown" {
  if (item.object_type === "scope_analysis" || item.object_type === "equity_scope" || item.object_type === "equity_screen") {
    return "equity";
  }
  if (
    item.object_type === "strategy_lab" ||
    item.object_type === "strategy_return_stream" ||
    item.object_type === "strategy_composition" ||
    savedResearchHasReturnStream(item)
  ) {
    return "strategy";
  }
  return "unknown";
}

export function buildResearchObjectFromScopeResult(result: ResearchResult | null): GammaResearchObject | null {
  if (!result?.performance_points?.length) {
    return null;
  }
  const displayName =
    result.scope_type === "single_ticker"
      ? `Equity Scope: ${result.primary_symbol ?? "Single Ticker"}`
      : "Equity Scope: Synthetic Basket";
  return {
    object_id: `equity_scope:${result.primary_symbol ?? "synthetic"}:${result.observations_count}`,
    object_type: "equity_scope",
    display_name: displayName,
    source_tab: "equity_research",
    source_mode: "scope_analysis",
    resolver_capabilities: ["return_leg", "benchmark"],
    symbols: result.weights.map((weight) => weight.symbol),
    constituents: result.constituents as unknown as Record<string, unknown>[],
    weights: result.weights as unknown as Record<string, unknown>[],
    available_start: result.performance_points[0]?.timestamp ?? null,
    available_end: result.performance_points[result.performance_points.length - 1]?.timestamp ?? null,
    provider_summary: result.history_source_label ?? result.source_provider ?? null,
    provenance: {
      source_provider: result.source_provider ?? "gamma_research",
      freshness_label: result.freshness_label ?? "derived",
    },
    warnings: result.warnings ?? [],
    return_points: result.performance_points,
  };
}

export function buildResearchObjectFromStrategyResult(result: StrategyLabResult | null): GammaResearchObject | null {
  if (!result?.returns_points?.length) {
    return null;
  }
  return {
    object_id: `strategy_return_stream:${result.name}:${result.returns_points.length}`,
    object_type: "strategy_return_stream",
    display_name: `Strategy: ${result.name}`,
    source_tab: "strategy_lab",
    source_mode: "imports",
    resolver_capabilities: ["return_leg", "benchmark"],
    symbols: [],
    constituents: [],
    weights: [],
    available_start: result.returns_points[0]?.timestamp ?? null,
    available_end: result.returns_points[result.returns_points.length - 1]?.timestamp ?? null,
    provider_summary: result.source_provider,
    provenance: {
      source_provider: result.source_provider,
      retrieved_at: result.retrieved_at,
      origin: result.origin,
      freshness_label: result.freshness_label,
    },
    warnings: result.warnings,
    return_points: result.returns_points,
  };
}
```

- [ ] **Step 5: Add store state and action**

In `frontend/src/lib/stores/app.ts`, import the new types and add:

```ts
export interface StrategyLabComposeOptions {
  name: string;
  legs: StrategyLabCompositionLegInput[];
  lenses: GammaResearchObject[];
  overlays: GammaResearchObject[];
  benchmarkObject?: GammaResearchObject | null;
  minObservations?: number;
}

export const strategyLabComposition = writable<StrategyLabCompositionResult | null>(null);
```

Add:

```ts
export async function composeStrategyLab(options: StrategyLabComposeOptions) {
  setLoading("strategyLab", true);
  try {
    const result = await postJson<StrategyLabCompositionResult>("/research/strategy-lab/compose", {
      name: options.name,
      legs: options.legs,
      lenses: options.lenses,
      overlays: options.overlays,
      benchmark_object: options.benchmarkObject ?? null,
      min_observations: options.minObservations ?? 5,
    });
    strategyLabComposition.set(result);
    resetCopilotCard("strategy_lab");
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("strategyLab", false);
  }
}
```

- [ ] **Step 6: Run frontend unit tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/view-models/research.test.ts src/lib/stores/app.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/lib/api/types.ts frontend/src/lib/stores/app.ts frontend/src/lib/stores/app.test.ts frontend/src/lib/view-models/research.ts frontend/src/lib/view-models/research.test.ts
git commit -m "Add frontend strategy lab composition contract"
```

---

### Task 4: Split Research UI Into Two Wrapper Views

**Files:**
- Create: `frontend/src/views/EquityResearchView.svelte`
- Create: `frontend/src/views/StrategyLabView.svelte`
- Modify: `frontend/src/views/ResearchView.svelte`

- [ ] **Step 1: Add a shared surface prop to ResearchView**

In `frontend/src/views/ResearchView.svelte`, keep existing markup and add props:

```svelte
  export let surface: "equity" | "strategy" = "equity";
```

Map mode ids:

```ts
  const equityModeMap: Record<EquityResearchMode, ResearchMode> = {
    overview: "overview",
    scope_analysis: "scope_analysis",
    comparables: "scope_analysis",
    scenario_context: "compare_scenario",
    saved_equity_research: "saved_research",
  };

  const strategyModeMap: Record<StrategyLabMode, ResearchMode> = {
    composer: "compare_scenario",
    backtest_analyze: "compare_scenario",
    regime_stress: "compare_scenario",
    imports: "strategy_lab",
    saved_runs: "saved_research",
  };
```

For the first implementation, new modes without full dedicated modules should render compact compatibility panels inside the existing shared surface:

```svelte
{#if surface === "equity" && mode === "comparables"}
  <article class="panel">
    <span class="eyebrow">EQUITY RESEARCH</span>
    <h3>Comparables</h3>
    <p class="muted">Peer and Fundamentals handoffs will use the selected equity scope. Run Scope Analysis first to populate a company or basket context.</p>
  </article>
{:else if surface === "strategy" && mode === "composer"}
  <article class="panel">
    <span class="eyebrow">STRATEGY LAB</span>
    <h3>Composer</h3>
    <p class="muted">Use saved equity scopes and strategy return streams as weighted research legs. This composition is read-only and does not modify any broker portfolio.</p>
  </article>
{/if}
```

Keep existing mode content for mapped modes:

- Equity `overview` uses current Overview.
- Equity `scope_analysis` uses current Scope Analysis.
- Strategy `imports` uses current Strategy Lab import UI.
- Strategy `backtest_analyze` uses current Compare / Scenario UI.
- Strategy `saved_runs` uses current Saved Research UI filtered in Task 7.

- [ ] **Step 2: Create Equity wrapper**

Create `frontend/src/views/EquityResearchView.svelte`:

```svelte
<script lang="ts">
  import ResearchView from "./ResearchView.svelte";
  import type { EquityResearchMode } from "../lib/view-models/research";

  export let mode: EquityResearchMode = "overview";
  export let overview;
  export let result;
  export let draft;
  export let compareResult;
  export let savedItems;
  export let loading = false;
  export let overviewLoading = false;
  export let strategyLoading = false;
  export let compareLoading = false;
  export let savedLoading = false;
  export let onLoadOverview;
  export let onRun;
  export let onSelectEquity;
  export let onAnalyzeStrategy;
  export let onCompare;
  export let onLoadSaved;
  export let onSaveResearch;
  export let onDeleteSaved;
  export let onUpdateDraft;
  export let onOpenRisk;
  export let onOpenIv;
</script>

<ResearchView
  bind:mode
  surface="equity"
  {overview}
  {result}
  {draft}
  {compareResult}
  {savedItems}
  {loading}
  {overviewLoading}
  {strategyLoading}
  {compareLoading}
  {savedLoading}
  {onLoadOverview}
  {onRun}
  {onSelectEquity}
  {onAnalyzeStrategy}
  {onCompare}
  {onLoadSaved}
  {onSaveResearch}
  {onDeleteSaved}
  {onUpdateDraft}
  {onOpenRisk}
  {onOpenIv}
/>
```

- [ ] **Step 3: Create Strategy wrapper**

Create `frontend/src/views/StrategyLabView.svelte` with the same props plus composition props:

```svelte
<script lang="ts">
  import ResearchView from "./ResearchView.svelte";
  import type { StrategyLabMode } from "../lib/view-models/research";

  export let mode: StrategyLabMode = "composer";
  export let composition = null;
  export let onComposeStrategy;
  export let overview;
  export let result;
  export let draft;
  export let compareResult;
  export let savedItems;
  export let loading = false;
  export let overviewLoading = false;
  export let strategyLoading = false;
  export let compareLoading = false;
  export let savedLoading = false;
  export let onLoadOverview;
  export let onRun;
  export let onSelectEquity;
  export let onAnalyzeStrategy;
  export let onCompare;
  export let onLoadSaved;
  export let onSaveResearch;
  export let onDeleteSaved;
  export let onUpdateDraft;
  export let onOpenRisk;
  export let onOpenIv;
</script>

<ResearchView
  bind:mode
  surface="strategy"
  {composition}
  {onComposeStrategy}
  {overview}
  {result}
  {draft}
  {compareResult}
  {savedItems}
  {loading}
  {overviewLoading}
  {strategyLoading}
  {compareLoading}
  {savedLoading}
  {onLoadOverview}
  {onRun}
  {onSelectEquity}
  {onAnalyzeStrategy}
  {onCompare}
  {onLoadSaved}
  {onSaveResearch}
  {onDeleteSaved}
  {onUpdateDraft}
  {onOpenRisk}
  {onOpenIv}
/>
```

- [ ] **Step 4: Type-check the wrappers**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/ResearchView.svelte frontend/src/views/EquityResearchView.svelte frontend/src/views/StrategyLabView.svelte
git commit -m "Create equity research and strategy lab view wrappers"
```

---

### Task 5: Wire App State, Rendering, And Copilot Context

**Files:**
- Modify: `frontend/src/App.svelte`
- Modify: `frontend/src/lib/stores/app.ts`
- Modify: `src/application/copilot_context_helpers.py`
- Modify: `src/services/openai_copilot_provider.py`
- Modify: `tests/test_copilot.py`

- [ ] **Step 1: Write failing app/store tests where coverage exists**

In `frontend/src/lib/stores/app.test.ts`, add Copilot validation coverage:

```ts
it("allows equity research and strategy lab copilot domains when their context exists", () => {
  researchResult.set(makeResearchResult());
  strategyLabResult.set(makeStrategyLabResult());

  expect(buildCopilotContextForTest("equity_research", "research")).toMatchObject({
    current_tab: "equity_research",
    research_state: expect.any(Object),
  });
  expect(buildCopilotContextForTest("strategy_lab", "research")).toMatchObject({
    current_tab: "strategy_lab",
    strategy_lab_state: expect.any(Object),
  });
});
```

If `buildCopilotContext` remains private, expose a test-only wrapper following the existing app-store test pattern:

```ts
export const __test = {
  buildCopilotContext,
  validateCopilotContext,
};
```

- [ ] **Step 2: Run the failing frontend store tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/stores/app.test.ts
```

Expected: FAIL until the domains are wired.

- [ ] **Step 3: Update App imports and state**

In `frontend/src/App.svelte`, replace `ResearchView` import:

```ts
import EquityResearchView from "./views/EquityResearchView.svelte";
import StrategyLabView from "./views/StrategyLabView.svelte";
```

Replace:

```ts
let researchMode: ResearchMode = "overview";
```

with:

```ts
let equityResearchMode: EquityResearchMode = "overview";
let strategyLabMode: StrategyLabMode = "composer";
```

Update mode helpers:

```ts
if (tabId === "equity_research") return equityResearchMode;
if (tabId === "strategy_lab") return strategyLabMode;
```

Update mode selection:

```ts
if (tabId === "equity_research") {
  equityResearchMode = modeId as EquityResearchMode;
  if (equityResearchMode === "overview" && !$researchOverview) await loadResearchOverview();
  if (equityResearchMode === "saved_equity_research") await loadSavedResearch();
  return;
}
if (tabId === "strategy_lab") {
  strategyLabMode = modeId as StrategyLabMode;
  if (strategyLabMode === "saved_runs") await loadSavedResearch();
  return;
}
```

Update old references:

- `activeTab === "research"` becomes `activeTab === "equity_research"` when referring to Overview refresh.
- `tabId === "research"` handoffs become `tabId === "equity_research"` unless they refer to Strategy Lab.
- `selectSharedEquity(..., "research")` becomes `selectSharedEquity(..., "equity_research")`.

- [ ] **Step 4: Render the two views**

Replace the current `{:else if $activeTab === "research"}` block with:

```svelte
{:else if $activeTab === "equity_research"}
  <EquityResearchView
    bind:mode={equityResearchMode}
    overview={$researchOverview}
    result={$researchResult}
    draft={$researchDraft}
    compareResult={$researchCompareResult}
    savedItems={$savedResearchItems}
    loading={$loading.research}
    overviewLoading={$loading.researchOverview}
    strategyLoading={$loading.strategyLab}
    compareLoading={$loading.compareScenario}
    savedLoading={$loading.savedResearch}
    onLoadOverview={loadResearchOverview}
    onRun={runResearchFromView}
    onSelectEquity={(symbol, label) => selectSharedEquity(symbol, label, "equity_research")}
    onAnalyzeStrategy={analyzeStrategyLab}
    onCompare={compareResearch}
    onLoadSaved={loadSavedResearch}
    onSaveResearch={saveResearchItem}
    onDeleteSaved={deleteSavedResearchItem}
    onUpdateDraft={setResearchDraft}
    onOpenRisk={openRiskFromResearch}
    onOpenIv={openIvFromResearch}
  />
{:else if $activeTab === "strategy_lab"}
  <StrategyLabView
    bind:mode={strategyLabMode}
    overview={$researchOverview}
    result={$researchResult}
    draft={$researchDraft}
    compareResult={$researchCompareResult}
    composition={$strategyLabComposition}
    savedItems={$savedResearchItems}
    loading={$loading.research}
    overviewLoading={$loading.researchOverview}
    strategyLoading={$loading.strategyLab}
    compareLoading={$loading.compareScenario}
    savedLoading={$loading.savedResearch}
    onLoadOverview={loadResearchOverview}
    onRun={runResearchFromView}
    onSelectEquity={(symbol, label) => selectSharedEquity(symbol, label, "strategy_lab")}
    onAnalyzeStrategy={analyzeStrategyLab}
    onCompare={compareResearch}
    onComposeStrategy={composeStrategyLab}
    onLoadSaved={loadSavedResearch}
    onSaveResearch={saveResearchItem}
    onDeleteSaved={deleteSavedResearchItem}
    onUpdateDraft={setResearchDraft}
    onOpenRisk={openRiskFromResearch}
    onOpenIv={openIvFromResearch}
  />
```

- [ ] **Step 5: Update frontend Copilot contexts**

In `frontend/src/lib/stores/app.ts`, update `CopilotBaseDomain` consequences by adding labels:

```ts
equity_research: "Equity Research",
strategy_lab: "Strategy Lab",
```

Add `copilotCards` and `copilotThreads` entries for both domains. Add cases in `buildCopilotContext`:

```ts
case "equity_research":
  return {
    current_tab: "equity_research",
    workspace_mode: workspaceMode,
    research_state: {
      overview: get(researchOverview),
      result: get(researchResult)
    }
  };
case "strategy_lab":
  return {
    current_tab: "strategy_lab",
    workspace_mode: workspaceMode,
    strategy_lab_state: {
      imported_result: get(strategyLabResult),
      composition: get(strategyLabComposition),
      compare_result: get(researchCompareResult)
    }
  };
```

Validation rules:

```ts
if (domain === "equity_research" && !get(researchOverview) && !get(researchResult)) {
  return "Load Equity Research overview or run Scope Analysis before generating a research card.";
}
if (domain === "strategy_lab" && !get(strategyLabResult) && !get(strategyLabComposition) && !get(researchCompareResult)) {
  return "Run a Strategy Lab import, composition, or comparison before generating a research card.";
}
```

- [ ] **Step 6: Update backend Copilot labels if hard-coded**

If `src/application/copilot_context_helpers.py` or `src/services/openai_copilot_provider.py` has domain label maps, add:

```python
"equity_research": "Generate a concise research card for the active Gamma equity research workspace.",
"strategy_lab": "Generate a concise research card for the active Gamma strategy lab workspace.",
```

Keep the same read-only wording used for `research`.

- [ ] **Step 7: Run targeted tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/stores/app.test.ts
cd ..
.\.venv\Scripts\python.exe -m pytest tests/test_copilot.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add frontend/src/App.svelte frontend/src/lib/stores/app.ts frontend/src/lib/stores/app.test.ts src/application/copilot_context_helpers.py src/services/openai_copilot_provider.py tests/test_copilot.py
git commit -m "Wire equity research and strategy lab app state"
```

---

### Task 6: Saved Object Split And Compatibility

**Files:**
- Modify: `frontend/src/views/ResearchView.svelte`
- Modify: `frontend/src/lib/view-models/research.ts`
- Modify: `frontend/src/lib/view-models/research.test.ts`
- Modify: `src/services/saved_research_store.py`
- Modify: `tests/test_research_v2.py`

- [ ] **Step 1: Add saved split tests**

In `tests/test_research_v2.py`, add:

```python
def test_saved_research_keeps_legacy_scope_and_strategy_objects(tmp_path):
    store = SavedResearchStore(tmp_path / "research")
    scope = store.create_item(SavedResearchCreateRequest(object_type="scope_analysis", title="AAPL Scope"))
    strategy = store.create_item(SavedResearchCreateRequest(object_type="strategy_lab", title="CSV Strategy"))

    loaded = store.list_items()
    assert {item.id for item in loaded} == {scope.id, strategy.id}
    assert store.load_item(scope.id).object_type == "scope_analysis"
    assert store.load_item(strategy.id).object_type == "strategy_lab"
```

This test documents compatibility: stored object types do not need destructive migration.

- [ ] **Step 2: Filter saved items in the shared view**

In `frontend/src/views/ResearchView.svelte`, import `classifySavedResearchSurface` and derive:

```ts
$: visibleSavedItems = (savedItems ?? []).filter((item) => {
  const classification = classifySavedResearchSurface(item);
  return surface === "equity" ? classification === "equity" : classification === "strategy";
});
```

Use `visibleSavedItems` in saved tables instead of `savedItems`.

- [ ] **Step 3: Update save object types by surface**

Where the view saves scope analysis, keep:

```ts
objectType: "scope_analysis"
```

Where the view saves imported Strategy Lab or composition results, use:

```ts
objectType: "strategy_lab"
```

For composition saves, use:

```ts
objectType: "strategy_composition"
```

- [ ] **Step 4: Run saved object tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_research_v2.py -q
cd frontend
npm run test -- --run src/lib/view-models/research.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/ResearchView.svelte frontend/src/lib/view-models/research.ts frontend/src/lib/view-models/research.test.ts src/services/saved_research_store.py tests/test_research_v2.py
git commit -m "Split saved equity research and strategy lab runs"
```

---

### Task 7: Strategy Lab Composer UI

**Files:**
- Modify: `frontend/src/views/ResearchView.svelte`
- Modify: `frontend/src/lib/view-models/research.ts`
- Modify: `frontend/src/lib/view-models/research.test.ts`

- [ ] **Step 1: Add composer option helper tests**

In `frontend/src/lib/view-models/research.test.ts`, add:

```ts
it("builds strategy composer objects from latest scope, imported strategy, and saved return streams", () => {
  const options = buildStrategyComposerObjects(
    makeResearchResult("single_ticker", [{ symbol: "AAPL", weight: 1 }]),
    makeStrategyLabResult(),
    [
      {
        id: "saved_1",
        object_type: "strategy_lab",
        title: "Saved Strategy",
        payload: makeStrategyLabResult() as unknown as Record<string, unknown>,
        warnings: [],
      } as SavedResearchItem,
    ]
  );

  expect(options.map((option) => option.object.object_type)).toContain("equity_scope");
  expect(options.map((option) => option.object.object_type)).toContain("strategy_return_stream");
});
```

- [ ] **Step 2: Add helper**

In `frontend/src/lib/view-models/research.ts`, add:

```ts
export interface StrategyComposerObjectOption {
  id: string;
  label: string;
  object: GammaResearchObject;
  defaultWeight: number;
}

export function buildStrategyComposerObjects(
  scopeResult: ResearchResult | null,
  strategyResult: StrategyLabResult | null,
  savedItems: SavedResearchItem[]
): StrategyComposerObjectOption[] {
  const options: StrategyComposerObjectOption[] = [];
  const scopeObject = buildResearchObjectFromScopeResult(scopeResult);
  if (scopeObject) {
    options.push({ id: "latest_scope", label: scopeObject.display_name, object: scopeObject, defaultWeight: 0.5 });
  }
  const strategyObject = buildResearchObjectFromStrategyResult(strategyResult);
  if (strategyObject) {
    options.push({ id: "latest_strategy", label: strategyObject.display_name, object: strategyObject, defaultWeight: 0.5 });
  }
  for (const item of savedItems) {
    const restored = hydrateStrategyLabResultFromSaved(item);
    const object = buildResearchObjectFromStrategyResult(restored);
    if (object) {
      options.push({
        id: `saved:${item.id}`,
        label: `Saved: ${item.title}`,
        object: { ...object, object_id: `saved:${item.id}` },
        defaultWeight: 0.25,
      });
    }
  }
  return options;
}
```

- [ ] **Step 3: Render composer controls**

In `frontend/src/views/ResearchView.svelte`, for `surface === "strategy" && mode === "composer"`, render a compact table:

```svelte
<article class="panel table-panel">
  <div class="table-panel-header">STRATEGY COMPOSER</div>
  <table>
    <thead>
      <tr>
        <th>Use</th>
        <th>Object</th>
        <th>Type</th>
        <th class="num-cell">Weight</th>
      </tr>
    </thead>
    <tbody>
      {#each composerOptions as option}
        <tr>
          <td><input type="checkbox" bind:checked={composerSelection[option.id]} /></td>
          <td>{option.label}</td>
          <td>{option.object.object_type}</td>
          <td class="num-cell">
            <input class="compact-input" type="number" min="0" step="0.01" bind:value={composerWeights[option.id]} />
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</article>
<div class="builder-actions compact">
  <button type="button" on:click={composeSelectedObjects} disabled={strategyLoading || !selectedComposerLegs.length}>
    {strategyLoading ? "Composing..." : "Compose"}
  </button>
</div>
```

The `composeSelectedObjects` function should call `onComposeStrategy` with:

```ts
await onComposeStrategy({
  name: "Strategy Lab Composition",
  legs: selectedComposerLegs,
  lenses: [],
  overlays: [],
  benchmarkObject: null,
  minObservations: 5,
});
```

- [ ] **Step 4: Show composition result**

Below composer controls, render this minimal KPI strip for the first pass:

```svelte
{#if composition}
  <article class="panel">
    <span class="eyebrow">COMPOSITION RESULT</span>
    <h3>{composition.name}</h3>
    <div class="kpi-grid">
      <div class="metric"><span>Total return</span><strong>{formatPercent(composition.metrics.total_return)}</strong></div>
      <div class="metric"><span>Annual vol</span><strong>{formatPercent(composition.metrics.annual_volatility)}</strong></div>
      <div class="metric"><span>Max drawdown</span><strong>{formatPercent(composition.metrics.max_drawdown)}</strong></div>
      <div class="metric"><span>Observations</span><strong>{composition.metrics.observation_count}</strong></div>
    </div>
  </article>
{/if}
```

- [ ] **Step 5: Run frontend tests and build**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/view-models/research.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/views/ResearchView.svelte frontend/src/lib/view-models/research.ts frontend/src/lib/view-models/research.test.ts
git commit -m "Add strategy lab composer UI"
```

---

### Task 8: Cross-Tab Handoffs And Legacy Active Tab Compatibility

**Files:**
- Modify: `frontend/src/App.svelte`
- Modify: `frontend/src/lib/workspace.ts`
- Modify: `frontend/src/lib/risk-workspace.test.ts`
- Modify: `frontend/src/lib/view-models/sitrep.ts`
- Modify: `frontend/src/lib/view-models/sitrep.test.ts`

- [ ] **Step 1: Update handoff tests**

In `frontend/src/lib/view-models/sitrep.test.ts`, update expected equity row handoff:

```ts
expect(handoff.targetTab).toBe("equity_research");
expect(handoff.targetMode).toBe("scope_analysis");
```

In `frontend/src/lib/risk-workspace.test.ts`, keep `sourceScope: "research"` for Risk compute basis because workspace mode is still `research`, not a tab id.

- [ ] **Step 2: Run failing handoff tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/view-models/sitrep.test.ts src/lib/risk-workspace.test.ts
```

Expected: FAIL until handoff targets are updated.

- [ ] **Step 3: Update handoff targets**

Change any tab handoff target from `"research"` to `"equity_research"` when the action opens a ticker or scope. Keep workspace mode values as `"research"`.

In `frontend/src/App.svelte`, add compatibility in tab switching:

```ts
function normalizeAppTabId(tabId: string): TabId {
  return tabId === "research" ? "equity_research" : (tabId as TabId);
}
```

Use it before assigning `$activeTab` from deep links, slash navigation, or handoff envelopes.

- [ ] **Step 4: Add Strategy Lab handoff from Equity Research**

In `frontend/src/App.svelte`, add:

```ts
async function openStrategyLabFromEquityResearch() {
  workspaceMode = "research";
  activeTab.set("strategy_lab");
  strategyLabMode = "composer";
  if (!$savedResearchItems.length) {
    await loadSavedResearch();
  }
}
```

Pass `onOpenStrategyLab={openStrategyLabFromEquityResearch}` into `EquityResearchView` and add a compact action button in the Scope Analysis summary when `result` exists:

```svelte
<button type="button" on:click={onOpenStrategyLab} disabled={!result?.performance_points?.length}>
  Add to Strategy Lab
</button>
```

- [ ] **Step 5: Run tests**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/view-models/sitrep.test.ts src/lib/risk-workspace.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/App.svelte frontend/src/lib/workspace.ts frontend/src/lib/risk-workspace.test.ts frontend/src/lib/view-models/sitrep.ts frontend/src/lib/view-models/sitrep.test.ts frontend/src/views/ResearchView.svelte
git commit -m "Update equity and strategy handoffs"
```

---

### Task 9: Final Verification And Documentation

**Files:**
- Modify: `roadmap_v2.md`
- Modify: `docs/README.md` only if it lists the old Research tab explicitly.
- Modify: `README.md` only if the visible tab list is documented there.

- [ ] **Step 1: Update docs wording**

In `roadmap_v2.md`, update the Current App State Snapshot language from:

```md
`Research` is a full multi-mode hub with Overview, Scope Analysis, Strategy Lab, Compare / Scenario, and Saved Research.
```

to:

```md
`Equity Research` owns equity market overview, scope analysis, comparables, scenario context, and saved equity research. `Strategy Lab` owns imported return streams, weighted Gamma object compositions, backtest/analyze views, regime/stress lenses, and saved runs.
```

- [ ] **Step 2: Run backend verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_research_v2.py tests/test_research_service.py tests/test_research_overview.py tests/test_copilot.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend verification**

Run:

```powershell
cd frontend
npm run test -- --run src/lib/navigation.test.ts src/lib/view-models/research.test.ts src/lib/stores/app.test.ts src/lib/view-models/sitrep.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual UI smoke**

Run:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173` and verify:

- Research workspace sidebar shows `SITREP`, `EQUITY RESEARCH`, and `STRATEGY LAB` in that order.
- Equity Research Overview loads the treemap.
- Equity Research Scope Analysis can run a single ticker.
- Strategy Lab Imports can analyze pasted CSV returns.
- Strategy Lab Composer can compose at least one return-capable object after Scope Analysis or Imports has produced a result.
- `/Research/Scope` resolves to Equity Research Scope Analysis.
- `/Research/Strategy` resolves to Strategy Lab Imports.

Stop the dev server after the smoke check.

- [ ] **Step 5: Commit docs and final polish**

```powershell
git add roadmap_v2.md docs/README.md README.md
git commit -m "Document equity research and strategy lab split"
```

- [ ] **Step 6: Final status check**

Run:

```powershell
git status --short
```

Expected: no uncommitted implementation changes, except user-owned unrelated files that were already dirty before this plan was executed.
