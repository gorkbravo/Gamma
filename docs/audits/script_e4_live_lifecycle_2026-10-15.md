# Script live lifecycle acceptance — 2026-10-15

**Result: passed after fixing missing stdout collection.** Three actual isolated-Python runs used the user's configured `gpt-6.1-sol`, existing OpenAI Code Interpreter adapter, disabled network and existing limits. The main case acquired actual yfinance-backed SPY history through Gamma's configured owning service and combined that copied export with supplied external JSON and CSV. This is live API/provider evidence, not a mock runtime or host execution of the research source.

## What passed

| Check | Observed evidence |
| --- | --- |
| Gamma data plus external files | One immutable bundle containing `spy.json`, `settings.json` and `rules.csv`; Gamma export retained provider identity, warnings, coverage and hashes. No data was acquired from inside Python. |
| Actual calculation and standalone outputs | Sol invoked the exact immutable wrapper. Python produced typed analytical JSON, a CSV table, SVG image, standalone text file and actual stdout. All were retained locally. |
| All optional kinds | Metrics, fractional simple daily returns at 252 periods/year, dated diagnostic indicators and signed hypothetical +0.60/−0.40 exposures validated. Signals and weights remained standalone with their explicit unsupported-mapping explanations. They were never applied to the return stream. |
| Numerical fidelity | 58 copied closes yielded 57 return observations, dated 2026-07-28 through 2026-10-15. Both independent expected and owning-service total return were **0.045182004587037694 (4.5182004587%)**. Every return matched within `1e-14`; all owning-service metric fields matched exactly. Independent retained signal and signed-weight comparisons also passed. This describes the copied provider series, not an account return, executable strategy or dividend-model certification. |
| Temporary opening | Repeated opening through the real authenticated FastAPI route created zero saved research objects. |
| Deliberate saving | A separate save request created one research object; altered return values and a stale preview hash were rejected with HTTP 422. |
| Recovery and edits | Reconstructing Script and saved-research stores reproduced identical analytical validation and saved provenance. Later source revision and input-bundle changes did not rebind the original result. |
| Export | The main run ZIP includes exact source, input files/manifests, output files and analytical validation. Saved analysis JSON preserves the full result and provenance. |
| Ordinary Python | A separate top-level print/file script completed without any analytical contract. Actual stdout and `ordinary.txt` were retained. |
| Invalid optional output | A third script wrote unsupported-version analytical JSON, printed a marker and wrote a valid standalone file. Python remained `completed`; stdout/files survived; optional validation failed and analytical opening was refused. |

The live test passed in **53.67 seconds**. Seven aggregate lifecycle checks passed. Independent retained signal/weight checking was then repeated directly against the preserved evidence without another API execution.

## Retained identity and evidence

- Main run: `65ae2226100d4283ab52cddeb42b115c`.
- Immutable source SHA-256: `49c42c05f0fbeea8c70c7aebfe809012ae31218aa9b4cd47e2fa5afcbc05c161`.
- Input manifest SHA-256: `0d2b70b62056ae10afcc4d4d2b3351177accb35f3e9816720b941f9f04147120`.
- Evidence directory: `output/playwright/script-e4-live-lifecycle/e48d124eeafe/`.
- Main run ZIP: `gamma-research-script-65ae2226100d.zip`.
- Other retained files: `evidence.json`, `analytical-validation.json`, `saved-analysis.json`, `ordinary-run.zip`, `invalid-run.zip`.
- Raw API usage records: ignored local `output/openai-usage/`; no prompts or credentials in those records.

These research objects use an isolated acceptance store under the evidence directory, leaving the user's ordinary saved research separate. Endpoint validation and saving used real owning services via an in-process authenticated API client. This run does not claim a new live-browser acceptance pass; prior desktop/intermediate/narrow browser evidence used explicitly labeled runtime fixtures.

## Defect found and fixed

The first attempt (`output/playwright/script-e4-live-lifecycle/3ed51924cbba/`) passed the actual SPY computation, all four result kinds, numerical comparisons, opening/saving/restart/export and tamper checks. It then failed the ordinary-script stdout assertion: Python had completed and its file was retained, but the response lacked Code Interpreter outputs.

The adapter now explicitly requests `include=["code_interpreter_call.outputs"]`, as documented by the current official Responses API and installed SDK. This returns actual Python logs to Gamma's existing log collection; model-authored completion summaries are not substituted. The exact wrapper, model, network policy, authority and compute limits were preserved. The corrected three-run test passed and each run retained one actual stdout output. The first attempt remains a failed acceptance attempt and has not been relabeled as a success.

Additional deterministic validation after the fix: **36 runtime/Script tests**, **94 analytical/catalog/Operator/SDK tests**, and all **17 Script Operator eval checks** passed. These are deterministic regression evidence, distinct from the three actual executions.

## Remaining limits

- This does not certify E3's full model-driven Operator acquisition/draft/review/run/synthesis journey. Its earlier elapsed-guard limitation remains a separate acceptance gate.
- Hypothetical-weight handoff remains unsupported: Composer gross-normalizes static weights; Risk requires aggregate returns and per-leg histories. Retained signed schedules do not authorize normalization, account selection or history acquisition.
- One listed-provider path was exercised. Fundamentals, Options, commodities, crypto and prediction-market live exports are not certified by this run.
- Acquisition inherited the configured `yfinance,ibkr` provider order and returned `yfinance`; no provider, model or runtime was silently substituted. Yahoo's unofficial-source and cache-use warnings remain retained.

## Reproduce

From the repository root in PowerShell, using the existing configured credentials/runtime/model:

```powershell
$env:GAMMA_RUN_LIVE_SCRIPT_E4_LIFECYCLE='true'
$env:GAMMA_OPENAI_USAGE_AUDIT_DIR='output/openai-usage'
.venv/Scripts/python.exe -m pytest tests/test_script_analytics_live.py -k complete_script_lifecycle -q -s
```

This explicitly makes three paid isolated-Python executions and a bounded configured-provider history acquisition. Default test runs skip it and keep ordinary tests pinned to mock. Each invocation retains a new independent evidence directory and never runs the authored research source on the host.
