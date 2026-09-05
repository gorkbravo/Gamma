# Copilot Checkpoint 8G acceptance — 2026-09-05

Implemented exact Prediction Markets comparison working analyses. The server owns the strict action, comparison execution, seven-day retained evidence and non-durable target. The existing configured OpenAI key was authorized for reuse and was neither changed nor exposed. No live OpenAI inference or live venue acceptance is claimed.

## Verified behavior

- Final focused backend run: 13 passed, covering Checkpoint 8G, Responses-loop regressions, existing prediction tools and registry checks. All three new Checkpoint 8G tests pass.
- Exact IDs and range/resolution reach the existing comparison service without a selected contract. An unrelated selected contract is not prepended. Duplicate, excess, malformed or incomplete inputs are rejected.
- Missing requested contracts remain explicit warnings; fewer than two loaded contracts cannot materialize. Unexpected provider contract identities are rejected.
- Retained records preserve charts, statistics, provenance and warnings across a new store instance. Materialization is idempotent and makes no provider call or saved-set mutation. Discarded records reject reopening.
- The model observation excludes chart geometry while retaining analytical statistics and coverage. Local working state keeps bounded chart samples. The simulated Responses continuation checks the actual observation and emits an analysis based on its overlap and spread values; the SDK observation budget accepts the same compact payload.
- All 434 frontend tests passed. Targeted rendering checks cover temporary versus live identity, missing IDs, disabled recompute/save behavior, and expired evidence. TypeScript typecheck and production build passed; build warnings are the existing IV SVG interaction and Surface3D unused-export warnings.
- Browser acceptance used the real Copilot session inspector → Open in Prediction markets → Compare handoff with an isolated mock backend. Retained charts, exact 1W/60-minute settings, warnings/methodology and the temporary banner rendered at measured 1800, 1024 and 640 CSS-pixel widths. The page had no horizontal overflow and the browser reported no application console errors. A development reload was followed by reopening the persisted record from Copilot.
- A completed workspace refresh preserved the retained three-contract 1W comparison. Return to live restored the original empty basket, MAX range and saved-set controls without saving the temporary basket.

## Existing backend failures

The broader Copilot and SDK smoke run returned 141 passed and seven failed with one previously reproduced failure excluded. All eight failures were separately reproduced using the committed `HEAD` version of `copilot_service.py` in an isolated Python process, without replacing the working file:

- `test_copilot_operator_plan_includes_hypothetical_portfolio_comparison`
- `test_copilot_operator_execution_runs_hypothetical_portfolio_comparison`
- `test_copilot_operator_hypothetical_portfolio_can_include_risk_handoff`
- `test_copilot_operator_plan_includes_strategy_lab_backtest_tool`
- `test_checkpoint8c_temporary_portfolio_risk_workflow_materializes_and_replays`
- `test_checkpoint8f_strategy_lab_portfolio_materializes_exact_signed_inputs`
- `test_copilot_plan_execution_runs_external_context_provider`
- The CPI/Fed parameter of `test_checkpoint5_representative_plans_select_domains_and_explain_omissions`

These are existing planning/entity-resolution or external-context failures, not new comparison failures. They remain open; the full backend suite is not green. Live provider acceptance and remaining Checkpoint 8 families are also open.

Follow-up on September 5: the [domain routing reliability fix](copilot_domain_routing_2026-09-05.md) repairs all eight cases in focused regression runs. The results above record the original 8G acceptance baseline.
