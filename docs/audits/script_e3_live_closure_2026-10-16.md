# Script E3 live Operator closure — 2026-10-16

**Result: passed.** After the defects below were fixed, three consecutive bounded live journeys completed E3's full Operator loop. Each one: acquired exact Gamma datasets, staged a reviewed candidate, accepted it as the user, executed it in the isolated OpenAI Code Interpreter runtime, and synthesized from actual retained outputs. Two of the runs used the final code. One of those used the default `auto` profile; the other used a user-selected `deep` profile.

## Journey under test

Harness: ignored `output/e3-live-closure.py`. It uses the configured services, the `openai` Script runtime (`gpt-6.1-sol`, 120-second guard, network disabled) and isolated stores under its evidence directory.

The Script is created the way Strategy Lab creates it, under session `strategy-lab-script-workspace`. Copilot uses a different chat session, and the Script is visibly attached through `script_state`. The bundle starts with a user-supplied `external.json` (`{"scale": 2}`).

1. **Turn 1, Operator.** Prompt: "Fetch exact SPY and QQQ equity_history datasets (30 days, daily) … append them as spy.json and qqq.json, preserving external.json … draft a candidate … Stop for my review and do not run it."
2. **Between turns, user.** Accept the staged candidate (`accept_staged_revision`, expected parent hash).
3. **Turn 2, Operator.** Prompt: "Run this Python Script with its reviewed input bundle, then summarize the actual printed results and comparison.csv."

## Passing evidence

| Run (evidence dir) | Profile | Turn 1 | Turn 2 | Run | Card |
| --- | --- | --- | --- | --- | --- |
| `20261016T164550` | deep / high | 75.7 s, 9 tools (read, discover/inspect/add ×2, read, draft_from_bundle) | 40.1 s, exact run | `f1008ef2b92a4728b799cc43903778b8`, completed, `openai_code_interpreter_v1` | "Executed: SPY versus QQQ endpoint comparison" |
| `20261016T164753` | auto → quick / low | 50.0 s, 9 tools | 32.3 s, exact run | `dd466fbbbcac4e7089e1bc605f6f3f0f`, completed | "Completed: SPY–QQQ comparison" |
| `20261016T164107` | deep / high | 80.9 s, 9 tools | 40.0 s, exact run | `bd15d27ddd8945649de3fbaeb510d055`, completed | Correct values, but a false wrapper-hash caveat (defect 5, fixed afterwards) |

For each run, the following was checked independently from the retained bundle files rather than from model text:

- **Exact identities.** The executed revision is the accepted candidate. The input snapshot is the reviewed bundle (`external.json`, `spy.json`, `qqq.json`; yfinance), and source and manifest hashes match.
- **Actual Python.** `executed_code=true`. Normalized wrapper hashes match. Stdout and `comparison.csv` were retained.
- **Numbers.** Recomputed first-to-last percent changes, difference and scaled difference match both the retained log and the card. For example, run `164550`: SPY −0.488853 %, QQQ −1.131938 %, difference +0.643085 pp, scaled 1.286169. Values differ between runs because yfinance updated the latest close during the session.
- **Truthful caveats.** The card states that the results cover the full retained period, not 30 days, and keeps Yahoo's unofficial-source and cache warnings.

Operator token usage per journey was about 115–126k input tokens (about 70 % cached) and about 2.4–4.1k output tokens across 12 model calls. Code Interpreter usage is accounted separately in the run records. Raw usage records are in each evidence directory's `usage/`; they contain no prompts or credentials.

## Defects found by the live investigation (all fixed, with regression tests)

1. **The model never received the attached Script.** The Operator loop's user message carried the task and plan but not `script_state`. The model therefore could not fill `script_id` or the exact hashes, so it either answered without tools or drafted a placeholder. The earlier 2026-10-15 attempt had worked around this by pasting ids into the prompt. The loop now adds `attached_context.script_state` for Script workflows: ids, hashes and canonical source capped at 8,000 characters, never outputs.
2. **Output ceiling too low for code.** `max_output_tokens=1600` truncated the response that stages the candidate (`incomplete: max_output_tokens`). Script workflows now allow 25,000 tokens, following the official reasoning guidance to reserve at least 25,000 for reasoning plus output. This is a ceiling; only generated tokens are billed. Other workflows keep 1,600.
3. **Derived change summary over limit.** `draft_research_script` on an existing Script prefixed `research_intent` into a summary capped at 512 characters, so the step failed. The summary is now shortened with an ellipsis.
4. **Usage audit aborted the run.** `os.replace` of the opt-in usage record hit a transient Windows lock (`WinError 5`), and the exception aborted the Operator. The rename is now retried, and a persistent audit I/O failure is logged instead of propagated.
5. **Misleading wrapper hashes.** The runtime validated the wrapper on normalized text but stored raw hashes. These differed for a fenced but identical wrapper, and the model reported this as an unresolved discrepancy. Both hashes are now normalized, with `wrapper_hash_basis`.

These complement the 2026-10-15 deterministic fixes: attached-Script access, acquisition permission, reviewed-bundle binding scope, observation fitting, the Script-only budget, and the prepared-bundle context. See the Script and Copilot plans.

## Remaining limits and follow-ups

- **Requested range not honored.** `equity_history` with `lookback_days=30` returned 46 daily observations over 64 calendar days. The Python disclosed this and the card caveated it, but the owning export should honor or explicitly label the requested window (E2 catalog contract).
- **Runtime retention noise.** The run retained copies of the input files as `file` outputs, plus a `summary` output containing the placeholder `[comparison.csv]({retained_artifact})`. Neither is analytically eligible, but both add noise.
- **Stale warning.** Live Operator results still carry the plan warning "Planner-only prototype: this preview does not execute tools…" even though tools executed.
- **Scope of certification.** One listed-data provider path (yfinance) and one calculation shape were certified. Other catalog domains (Fundamentals, Options, commodities, crypto, prediction markets) are not live-certified by this run. The staged-review boundary is unchanged, so data-dependent build-and-run spans two turns by design.

## Reproduce

From the repository root, using existing credentials and the configured `openai` Script runtime. Each invocation makes paid model, Code Interpreter and provider calls:

```powershell
$env:E3_CLOSURE_PROFILE='auto'   # or 'deep'
.venv/Scripts/python.exe output/e3-live-closure.py
```

The harness aborts before any model call unless the configured runtime executes isolated Python.
