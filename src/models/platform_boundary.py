from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.utils.time import now_utc


@dataclass(frozen=True)
class ReadOnlyBoundary:
    boundary_id: str
    read_only: bool
    allows: list[str] = field(default_factory=list)
    prohibits: list[str] = field(default_factory=list)
    hard_operator_locks: list[str] = field(default_factory=list)
    app_boundary_notes: list[str] = field(default_factory=list)
    copilot_notes: list[str] = field(default_factory=list)
    ibkr_tws_notes: list[str] = field(default_factory=list)
    source_provider: str = "gamma"
    retrieved_at: datetime | None = None
    origin: str = "gamma.system.read_only_boundary"
    transformation_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "read_only": self.read_only,
            "allows": list(self.allows),
            "prohibits": list(self.prohibits),
            "hard_operator_locks": list(self.hard_operator_locks),
            "app_boundary_notes": list(self.app_boundary_notes),
            "copilot_notes": list(self.copilot_notes),
            "ibkr_tws_notes": list(self.ibkr_tws_notes),
            "source_provider": self.source_provider,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "origin": self.origin,
            "transformation_note": self.transformation_note,
        }


def build_gamma_read_only_boundary(*, retrieved_at: datetime | None = None) -> ReadOnlyBoundary:
    generated_at = retrieved_at or now_utc()
    return ReadOnlyBoundary(
        boundary_id="gamma_read_only_research_boundary",
        read_only=True,
        allows=[
            "market_data_retrieval",
            "portfolio_inspection",
            "historical_research",
            "derived_analytics",
            "scenario_analysis",
            "copilot_grounded_synthesis",
        ],
        prohibits=[
            "order_placement",
            "order_modification",
            "order_cancellation",
            "account_modification",
            "portfolio_rebalancing_execution",
            "wallet_signing",
            "transaction_submission",
            "arbitrary_strategy_code_execution",
        ],
        hard_operator_locks=[
            "TWS API read-only configuration is the hard operator-side execution lock for IBKR sessions.",
        ],
        app_boundary_notes=[
            "Gamma exposes data and research services only; no backend route or Copilot tool is an execution path.",
            "IBKR/TWS access in Gamma is limited to market data, portfolio inspection, account summary, historical data, FX, and options surface inspection.",
            "Read-only provider capability records are metadata and must not be interpreted as execution permissions.",
        ],
        copilot_notes=[
            "Copilot consumes Gamma-owned context and read-only tools only.",
            "Copilot must not mutate application state, place orders, submit transactions, or request execution authority.",
        ],
        ibkr_tws_notes=[
            "Gamma requests a read-only TWS connection where the installed ib_insync version supports the readonly flag.",
            "Gamma still relies on the operator's TWS API read-only setting as the hard external lock.",
            "If an older client library cannot pass the readonly flag, Gamma's app-side boundary still exposes no order placement, order management, or account modification code path.",
        ],
        retrieved_at=generated_at,
        transformation_note="Static Workstream 1 platform metadata describing Gamma's data-only application boundary.",
    )
