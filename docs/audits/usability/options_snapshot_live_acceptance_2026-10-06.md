# Options snapshot live acceptance — 2026-10-06

Status: passed for the manual snapshot capture, retained comparison, and runtime-restart contract.

## Setup and scope

Used the configured live TWS endpoint at `127.0.0.1:7496` through a separate read-only IBKR connection (client ID 87). Gamma ran with `MOCK_DATA=false`. Called the real FastAPI routes through an in-process TestClient, without provider mocks, using SPY, live market-data mode, compact depth, linear surface display, and a bounded 30-second collection window. No orders were placed. The verification connection was closed afterward.

Saved two captures through `POST /iv/snapshots` in the normal configured history directory (`data/options_snapshots` for this run), shut down the original runtime, constructed a fresh runtime, and re-read both records through `GET /iv/snapshots/{id}`. This verifies runtime teardown/reconstruction and disk persistence; it is not an OS reboot or a separate-process desktop restart test.

## Results

Times below are Europe/Madrid (UTC+2).

| Evidence | Baseline | Comparison |
| --- | --- | --- |
| Surface time | 18:13:10 | 18:13:37 |
| Snapshot ID | `11ffc196ee4540caa574831a91a294d2` | `1b49cfba263b4b9cb17891fdd11fee4f` |
| Source / freshness | IBKR / live | IBKR / live |
| Delayed flag | false | false |
| Underlying spot | 781.015 | 781.04 |
| Observed cells / expected cells | 17 / 24 | 14 / 24 |
| Interpolated cells | 7 | 10 |
| Exact displayed payload preserved | yes | yes |
| Exact replay after runtime restart | yes | yes |

Both captures retained all returned surface fields, contracts, observations, pricing assumptions, model metadata, and quality counters exactly. Neither provider payload included a surface warning. Partial coverage remained explicit in the quality metadata. No storage warnings were returned after reconstruction.

Ran the production frontend `compareIvSnapshots` helper against these actual retained captures by bundling the existing TypeScript module with the installed esbuild runtime. Four expiry dates overlapped. Two had an exact observed baseline reference strike in both captures:

| Expiry | Baseline reference strike | Baseline IV | Comparison IV | Change |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-06 | 782 | 11.5554% | 11.6498% | +0.0945 pp |
| 2026-10-13 | 782 | 9.5044% | 9.4206% | -0.0838 pp |
| 2026-10-20 | 780 | 10.9777% | N/A | N/A |
| 2026-11-06 | 775 | 15.1728% | N/A | N/A |

Put/call wing skew was computed where the same observed wing strikes and reference strike existed. Missing observations produced null/N/A and the comparison warning: “Some exact observed strikes are missing. Their changes are unavailable; fitted cells are excluded.” Display-grid interpolation did not fill the comparison gaps.

This short live sample validates mechanics, provenance, and missing-data behavior. It does not establish a stable daily time series, IV percentile/rank coverage, or the economic significance of the observed changes. Zero-day wing changes were large; the retained quote/quality evidence should be inspected before interpreting them.

## Evidence and remaining scope

Local raw evidence is under `output/iv-snapshots-live-2026-10-06/`: `surface-1.json`, `surface-2.json`, `capture-1.json`, `capture-2.json`, `summary.json`, and `comparison.json`. Reproduction scripts are `output/verify_iv_snapshots_live.py` and `output/compare_iv_snapshots_live.mjs`. Runtime logs remain local.

No implementation changes were required for this live pass. The prior deterministic browser checks at 1440/1000/390px remain the UI evidence; this follow-up exercised the live API/provider and production comparison helper rather than driving the browser against TWS. Broader Options live workflows, long-duration history, and beta release gates are unchanged.
