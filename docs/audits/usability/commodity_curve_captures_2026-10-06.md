# Commodity historical curves and exact calendar spreads

Date: 2026-10-06. Scope: Roadmap Workstream 8, manual read-only Commodities research.

## Delivered behavior

Curves & Spreads can save the displayed instrument, full futures curve and coverage metadata as an immutable versioned record. Records retain exact contract IDs, symbols, months, expiries, quote units, currency, provider timestamps, save timestamps, warnings and per-node quote field/delay/freshness. The store uses checksums and atomic writes. Reopening needs no provider access and does not replace the live workspace.

Two retained curves compare by exact contract identity. Missing contracts, missing prices and conflicting identities produce explicit statuses and unavailable differences. Instruments and units must agree. Comparisons describe captured observations, not official settlement changes.

Saved calendar spreads retain the original left and right contracts and calculate left price minus right price over compatible retained observations. Expired or missing contracts, identity conflicts, missing prices and incompatible units remain gaps. No front-month substitution, interpolation or backfill occurs. Refresh Saved reloads a selected spread's history. Earlier compatible captures also supply Overview term structure.

Offset-free backend timestamps display as UTC. The existing Commodities header now wraps its mode controls on small screens; tables scroll within their panels.

## Live acceptance

The production Commodities view ran in a browser harness against the real local API, with an isolated history/cache directory. TWS capture used read-only IBKR client 89, WTI enabled and six contracts. The user's environment configuration was unchanged. After capture, the backend restarted and replay used a disconnected IBKR service.

At 17:28:51 and 17:28:54 UTC, two captures retained CLX6, CLZ6, CLF7, CLG7, CLH7 and CLJ7. All six nodes reported IBKR last-price snapshots with delayed=false. The exact pair CLX6 (`ibkr:304037511`) minus CLZ6 (`ibkr:296574787`) produced 1.070 USD/bbl in both observations.

Capture IDs: `26af65a76f32470db63e990c81f6142a`, `74c77a6a573b4f28a3f4794414e95d80`. Spread ID: `757e6dde3b0e44159122f6a87b98f058`. Reopened payloads matched the original records exactly; comparisons and both spread observations passed after restart. Full evidence remains locally under `output/playwright/commodity-curves-live/`.

The sample acceptance additionally removed the original left contract from a third capture. Comparison showed absent-from-comparison, and the tracked spread showed contract-not-in-capture with an unavailable value. Responsive checks and screenshot review covered 1440, 1000 and 390 pixel widths; the page and new panel stayed within the viewport, with tables scrolling internally. An injected API failure showed an actionable error. No browser page errors occurred.

## Validation and limits

- 106 focused backend tests passed across captures, commodities and API tests, including restart persistence, missing/expired contracts, identity conflicts, corruption, interrupted writes, incompatible units and Overview history.
- Three frontend helper tests passed, including UTC handling and zero versus missing prices.
- Frontend typecheck and production build passed. Existing IV SVG accessibility and Surface3D unused-property warnings remain.
- Sample and live browser capture/restart/replay acceptance passed using `output/verify_commodity_curves.py` (add `--live` for TWS).

This closes manual retention and exact-pair tracking, not vendor historical-curve acquisition, official settlement history, continuous-contract research or the rest of Workstream 8. Captures accumulate only when the user saves them. Browser acceptance covers the production view and API, rather than the packaged Tauri shell. Corrupt records remain on disk and are reported; storage is bounded to 2 MB per record; the original 2,000-records-per-category cap was replaced on 2026-10-19 (see the follow-up below). There is no execution or order-routing functionality.

## Follow-up — 2026-10-19 (2026-10-15 review)

Four medium findings were still open in the current code and are now fixed. Deterministic only; live TWS acceptance was not rerun.

- **Mixed leg evidence.** A spread point whose legs differ in `quote_field`, `delayed` or `freshness_label` is now `mixed_quote_evidence`, not `observed`. Gamma keeps the value, lists the differing fields in `evidence_mismatch`, adds a history warning, and shows the mismatch in the spread table. Consumers that accept only `observed` points exclude these points. The live branch of `e2e/commodity-curves.spec.ts` accepts either status with a non-null value; the sample branch still requires `observed`.
- **Observation order and duplicates.** Spread history, capture listings and the Overview's earlier curves are now ordered by `as_of`. Save time only breaks ties. Captures with the same `as_of` count as one observation: the latest save is shown, earlier ids appear in `superseded_capture_ids`, and a warning names saves that disagree. Overview's eight earlier curves are eight distinct observation times. Saving a byte-identical capture or spread again returns the existing record instead of writing a duplicate.
- **Mock/live separation.** Each new record carries `mode` (`mock` or `live`), taken from the runtime. A runtime only lists, loads, compares, deletes or uses records of its own mode; the other mode's ids return `404`. Records saved before this change are classified by their evidence: sample coverage or `sample_data` providers are mock, everything else is live. Their responses say `mode_inferred: true`. A legacy spread takes the mode of its source capture. Files are not moved or rewritten.
- **Retention, delete and scans.** The global 2,000-record cap is replaced by per-instrument, per-mode limits: 500 captures and 200 spreads. In mock mode, the oldest sample captures are pruned automatically, except captures that are a spread's source. In live mode, saving at the limit returns `409` and asks the user to delete older records: retained live observations are never removed automatically. `DELETE /commodities/curve-captures/{id}` and `DELETE /commodities/calendar-spreads/{id}` exist, and Curves & Spreads has two-step **Delete Capture**/**Delete Spread** buttons. Deleting a capture that a spread cites returns `409` until the spread is deleted. An in-memory index keyed by file mtime and size means a workspace load rereads only new or changed files. The Overview then loads only the up to eight selected curves in full, instead of revalidating every retained file.

Tests: `test_commodity_curve_captures.py` adds mixed evidence, `as_of` order and duplicates, idempotent saves, mock/live isolation, legacy classification, index reads, mock pruning versus live refusal, and delete/provenance routes. The two existing history tests now give successive observations distinct `as_of` values. `commodity-captures.test.ts` covers the new spread-point note. The new backend tests fail against the previous store.

Browser acceptance (`output/verify_commodity_curves.py`, sample mode only) passed three consecutive capture → restart → replay runs. The spec now refreshes until the curve has a new `as_of` before the second capture. The sample provider stamps `as_of` to the second, so two saves in the same second had become a single observation, and one run failed until this change. The roll-shaped gap capture also gets a later `as_of`. The replay deletes that sample gap capture through the two-step button, and shows the `409` when deleting a spread's source capture. Screenshots at 1440/1000/390 px show the new buttons and spread-point notes inside the panel, with no page overflow. The live TWS run was not repeated.

