# Gamma research client (Python)

A small, read-only client for Gamma's local API, for users who research in their own Python, pandas or Jupyter. It is checkpoint I4b of [Workstream 12 - Ideas](../../docs/idea_workspace_spec.md#quant-bridge-read-only-client).

- **Local only.** It talks to the Gamma backend on your machine, authenticated with the session token Gamma started with. Gamma never runs it.
- **Read-only, with one write path.** It reads daily closes, macro series, ideas, tracking records and the observable registry, each with its provenance. The only thing it can write is a signal imported into an idea, which Gamma validates exactly like a Strategy Lab CSV import. Every request is checked against `ALLOWED_ROUTES` before it is sent; nothing in it can place, stage or route an order, or touch an account.
- **Not advice.** Tracking records are hypothetical and labelled "Hypothetical, not executed".

## Install

From this folder, into the environment you research in:

```bash
pip install -e ".[pandas]"
```

`httpx` is required; `pandas` is optional (without it, reads return lists of dicts).

## Connect

Gamma's backend needs the same session token the app uses. Set it, and the API address if it is not the default `http://127.0.0.1:8000`:

```bash
export GAMMA_SESSION_TOKEN=...   # PowerShell: $env:GAMMA_SESSION_TOKEN = "..."
export GAMMA_API_BASE=http://127.0.0.1:8000
```

## Use

```python
from gamma_client import Gamma

g = Gamma()                                  # token and address from the environment

spy = g.history("SPY", days=730)             # DataFrame: close, close_at, source_provider, retrieved_at, origin
btc = g.history("bitcoin", kind="crypto")    # CoinGecko daily closes
ust10 = g.macro("us-10y-yield")              # a macro series id from Gamma's catalog (FRED needs FRED_API_KEY)
spy.attrs["provenance"]                      # where the closes came from

ideas = g.ideas.list(status="active")
record = g.ideas.tracking(ideas[0]["idea_id"])   # hypothetical forward record

# Weights: one column per instrument, signed shares of NAV; dates in the index or a "date" column.
import pandas as pd
weights = pd.DataFrame({"AAPL": [0.5, 0.6], "MSFT": [0.5, -0.2]}, index=pd.to_datetime(["2026-01-12", "2026-01-13"]))
idea = g.ideas.attach_signal(ideas[0]["idea_id"], weights, kind="weights", label="Momentum v3")
idea["signals"][-1]["trial_count"]           # every attach is a trial; the count never goes down
```

What Gamma does with an imported signal (see the spec's I4 design decisions):

- `weights` and `positions`: the latest row on or before today becomes the idea's book and drives its hypothetical tracking from the next close; a row dated after today is refused. A crypto column is mapped with `instruments={"BTC": {"symbol": "bitcoin", "entity_type": "crypto"}}`.
- `returns`: validation only. Gamma cannot rebuild a return stream from provider closes, so it never enters the tracking record.
- Dates, numbers (`%` suffix, thousands separators), missing cells and duplicate dates are read with the Strategy Lab import rules; the warnings come back on the signal.

## Errors

A refused request raises `GammaClientError` with the HTTP status and Gamma's reason, for example `422: The CSV has rows after today …`. A request outside the allowlist raises `RouteNotAllowedError` before anything is sent.
