# Copilot Checkpoint 9 acceptance — 2026-10-04

Checkpoint 9 passes its deterministic interruption, recovery and authority-transition exit criteria. Copilot advances from the completed Checkpoint 8 baseline (~92%) to **~94%**. Checkpoint 10 remains open; this report is not successful live OpenAI/market-provider evidence or a 100% release certification.

## Delivered contract

Gamma retains the original run, user turn, context snapshot, exact request/role/scopes, plan, observations, working-analysis ids, pending action, decision and remaining tool/provider/time budgets in `copilot.run-recovery.v1`. Approve, reject and restart recovery continue that run and replace its original persisted turn. Pausing emits `run.paused`, not a completed turn; continuation emits `run.resumed`, progress and one completion/cancellation boundary per continuation attempt.

The existing saved DCF update is the consumer. Its exact diff, context fingerprint, reviewed proposal hash, expiry, current-model hash and Operator authority are checked on Gamma's server. A pre-change rollback snapshot is mandatory. Concurrent/repeated decisions do not repeat the mutation. A committed decision can recover remaining research after an interruption; an uncertain mutation outcome fails closed as `recovery_required` instead of automatically retrying a write. Deleting the owning session removes its recovery/approval records.

Read retries are bounded to one additional attempt within the original budgets. Exhaustion has a typed `tool_retry_exhausted` observation and degrades the result. Recovery charges reserved interrupted attempts and skips already observed steps. Remaining-plan revisions recheck the current registry and retained selected scopes; removed permissions omit steps rather than introducing tools or authority.

Frontend approvals use the shared NDJSON lifecycle and register the original run/loading/session ownership before network work. Stop addresses that run, including the boundary before a queued decision commits. Reconnect uses the persisted monotonic cursor and subscribes without resubmitting the decision. Timeout/transport exhaustion reloads the persisted turn without inventing a new submission. Session switches do not project the result into another conversation. A generic Retry cannot recreate an approval-bearing run; the explicit Operator-only continuation control recovers it.

Both the shelf and dedicated tab expose the same diff, approval/rejection/recovery callbacks, loading state and Stop action. Agent selection disables approval execution; selecting Operator visibly explains the research authority. WACC fractions render as percentages (8% → 9%), the comparison precedes decision controls and remains keyboard focusable/scrollable on narrow screens. Stale-preview errors persist on the same turn so reload cannot hide the reason the change was refused.

No new durable mutation family, trading/order/account/wallet/rebalance authority, arbitrary host-code tool, model/framework migration or credential/configuration change was added. Responses remains the default model/tool loop; the optional SDK remains a comparison path. The generic interruption record and run-event lifecycle are server-owned, with DCF-specific validation/execution retained at the existing consumer boundary.

## Exit-criteria evidence

| Criterion | Acceptance evidence |
| --- | --- |
| Exact approve/reject continuation and restart | Both decisions survive reconstruction from disk, keep the original run/turn/context-snapshot/response ids, retain observations and continue remaining reads. |
| Idempotency and rollback | Concurrent approval, duplicate request/changed request, payload tampering, missing rollback snapshot and interruption after commit are tested; the DCF snapshot/write is never repeated. |
| Stale context and rejection | Changed fingerprint, changed saved DCF, expired/tampered preview and invalid session/role/token/hash cannot apply. Stale streamed errors remain visible and rejectable. |
| Cancellation | Paused cancellation writes nothing; resumed cancellation stops at the next safe read boundary and retains an already committed update. Stop before a queued decision commits rejects it without waiting for the approval lock. |
| Retry exhaustion and interrupted reads | A transient read gets at most one retry; exhausted retries are typed/degraded. Interrupted continuation retains earlier observations and spent budgets; recovery does not repeat completed reads. |
| Replanning and permissions | A revoked read permission omits the step; remaining steps are a subset of the retained plan and scopes. Agent approval decisions are refused. |
| Frontend lifecycle and parity | Store tests cover loading/session ownership, Stop, session switching, cursor reconnect before/after the first event, exhausted reconnect and refusal of a new-run Retry. Browser tests exercise shelf/tab role controls and shared continuation. |

## Verification

- Combined focused backend suite: **206 passed**, covering Copilot, Checkpoint 8 completion, the then-29 recovery cases, SDK smoke and Operator eval tests. After the final pre-commit cancellation and persisted-stale-error refinements, the expanded recovery suite passed **30/30**.
- Standalone `python -m evals.copilot_operator_eval`: **31/31 deterministic cases passed**, average score 0.9093 across auto/quick/standard/deep custom profiles and the SDK stub. Routing stayed `gamma_custom_loop`; there is no live-default-switch evidence.
- Frontend: **460 tests across 61 files passed**; final focused Copilot run: **58/58**. TypeScript typecheck, production build and Tauri `desktop:check` passed. Build warnings remain the pre-existing IV SVG interaction and Surface3D unused exports.
- Chromium: **16/16 journeys passed** — eight approval/recovery cases plus all eight `options-copilot-continuity.spec.ts` regressions from `e1e1ead`. Shelf and dedicated approval flows were checked at **1440, 1024 and 640 CSS pixels**, including keyboard role selection, focused DCF comparison, approve, reject, recover and Stop. Captured screenshots were visually inspected; no page overflow or application page errors occurred. Screenshots are generated under ignored `frontend/test-results`.
- `git diff --check` passed. Unrelated `.env.example`, `.impeccable/`, `PRODUCT.md` and `website/` work was excluded from both commits. No push was performed.

The focused backend verification used explicit `BASE_CURRENCY=USD` and `IB_MARKET_DATA_MODE=auto`, alongside the repository's mock test-provider settings. These are test process settings, not configuration edits. The isolated Checkpoint 8 staged-tree verification is documented in its acceptance report and committed separately as `bdce458`.

## Remaining release evidence

There is no remaining Checkpoint 9 blocker under its representative deterministic contract. **Checkpoint 10 is not certified:** successful intentionally authorized live Agent/Operator model-tool-model and approval-resume workflows against representative providers remain required, together with the broader release trace, accessibility/screen-reader/reduced-motion, first-run/degraded-provider, migration/restart and repository-wide release gates. This pass used fixtures and simulated transports, did not intentionally spend OpenAI API quota, and did not run the repository-wide backend suite as a Checkpoint 10 gate. Historical live quota/failure evidence is not a successful live pass.

Current official OpenAI documentation was fetched through the Developer Docs connector on 2026-10-04. Reviewed URLs and the Responses/SDK responsibility decision are recorded in the active Copilot plan.
