# Provenance Expectations

This document defines the minimum provenance contract that new roadmap-aligned entities should carry before Gamma expands into prediction markets, crypto, AI-assisted outputs, or fundamentals.

Gamma remains a read-only research environment. That means every new normalized dataset or derived analytic should be traceable enough that the user can answer:

- where it came from,
- when it was fetched,
- which adapter or module produced it,
- what transformation logic was applied before display.

## Minimum Provenance Fields

Every roadmap-era entity should be able to expose, directly or alongside the payload, the following fields:

- `source_provider`
  The external provider or upstream system name, such as `ibkr`, `polymarket`, `coingecko`, `alchemy`, `fred`, or `manual`.

- `retrieved_at`
  UTC timestamp for when Gamma fetched or materialized the source payload.

- `origin`
  The adapter, endpoint, or internal module that produced the record, such as `research_data_provider.load_instrument_history`, `polymarket.gamma.markets`, or `risk_service.compute`.

- `transformation_note`
  Null for raw fields. Required for derived values, scaled estimates, normalized identities, joins, or fallback logic.

## How To Apply It

- Raw fetched entities should preserve the upstream provider identity and fetch timestamp without inventing transformation notes.
- Derived analytics should reference the upstream provider when possible and explain the derived step in `transformation_note`.
- Cached payloads should retain the original `retrieved_at`; cache write time is not a substitute.
- When multiple upstream sources contribute to one record, store the dominant provider on the entity and include the combination in `transformation_note`, or attach field-level provenance if the model needs it.
- Compatibility shims may expose provenance as additive metadata before it becomes mandatory in every response model.

## Initial Normalized Shape

Use this as the baseline shape for future adapters and schemas:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProvenanceRecord:
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
```

This does not require every current response model to change immediately. It defines the contract new roadmap entities should satisfy as they are introduced.

## Required Cases

The following cases must include a non-null `transformation_note`:

- normalized instrument identifiers built from provider fields,
- FX-converted benchmark series,
- delayed/live fallback behavior,
- coverage-scaled risk estimates,
- wallet concentration metrics,
- calibration/backtest outputs,
- AI-generated summaries or hypothesis cards that depend on internal tools or transformed datasets.

## Non-Goals

- Do not block current legacy responses on a big-bang provenance retrofit.
- Do not add UI-only provenance labels without carrying the underlying metadata through the backend.
- Do not collapse multiple source steps into a vague string such as `computed internally`.
