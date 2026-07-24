from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.utils.time import now_utc

SITREP_FOLLOW_UP_STATUSES = ("open", "resolved")


@dataclass(frozen=True)
class SitrepFollowUp:
    """A saved SITREP triage row with optional note and resolved state.

    ``handoff`` stores the frontend ``SitrepHandoffRequest`` shape as an opaque
    dict so saved rows can reopen their originating tab/mode without the
    backend depending on frontend routing vocabulary.
    """

    id: str
    row_id: str
    title: str
    source: str = ""
    tone: str = "neutral"
    detail: str = ""
    meta: str = ""
    note: str = ""
    status: str = "open"
    handoff: dict[str, Any] | None = None
    saved_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not str(self.id or "").strip():
            raise ValueError("follow-up id is required.")
        if not str(self.row_id or "").strip():
            raise ValueError("follow-up row_id is required.")
        if not str(self.title or "").strip():
            raise ValueError("follow-up title is required.")
        if self.status not in SITREP_FOLLOW_UP_STATUSES:
            raise ValueError(
                f"follow-up status must be one of {SITREP_FOLLOW_UP_STATUSES}, got {self.status!r}."
            )


@dataclass(frozen=True)
class SitrepFollowUpCreateRequest:
    row_id: str
    title: str
    source: str = ""
    tone: str = "neutral"
    detail: str = ""
    meta: str = ""
    note: str = ""
    handoff: dict[str, Any] | None = None
    saved_at: datetime | None = None


@dataclass(frozen=True)
class SitrepFollowUpUpdateRequest:
    note: str | None = None
    status: str | None = None
