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

This closes manual retention and exact-pair tracking, not vendor historical-curve acquisition, official settlement history, continuous-contract research or the rest of Workstream 8. Captures accumulate only when the user saves them. Browser acceptance covers the production view and API, rather than the packaged Tauri shell. Corrupt records remain on disk and are reported; storage is bounded to 2 MB per record and 2,000 records per category. There is no execution or order-routing functionality.
