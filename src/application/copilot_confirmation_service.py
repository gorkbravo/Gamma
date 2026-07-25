from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import timedelta
from typing import Any

from src.models.copilot import CopilotDraftMutation
from src.services.copilot_store import CopilotStore
from src.utils.time import now_utc


class CopilotConfirmationError(ValueError):
    pass


class CopilotConfirmationService:
    """Issues and consumes single-use, context-bound local mutation confirmations."""

    DEFAULT_TTL_SECONDS = 15 * 60

    def __init__(
        self,
        store: CopilotStore,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.store = store
        self.ttl_seconds = max(1, int(ttl_seconds))

    @staticmethod
    def proposal_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def bind(self, mutation: CopilotDraftMutation) -> CopilotDraftMutation:
        issued_at = mutation.created_at or now_utc()
        bound = replace(
            mutation,
            proposal_hash=mutation.proposal_hash or self.proposal_hash(mutation.proposed_payload),
            expires_at=mutation.expires_at or issued_at + timedelta(seconds=self.ttl_seconds),
        )
        self.store.save_mutation(bound)
        return bound

    def consume(
        self,
        *,
        mutation_id: str,
        confirmation_token: str,
        session_id: str | None,
        context_fingerprint: str | None,
        proposal_hash: str | None,
        apply_tool_id: str,
    ) -> CopilotDraftMutation:
        now = now_utc()
        expired = False

        def validate_and_consume(mutation: CopilotDraftMutation) -> CopilotDraftMutation:
            nonlocal expired
            if mutation.status != "pending":
                raise CopilotConfirmationError(
                    f"Copilot mutation confirmation is not active: {mutation.status}"
                )
            if mutation.expires_at is not None and now >= mutation.expires_at:
                expired = True
                return replace(mutation, status="expired")
            if not confirmation_token or not hmac.compare_digest(
                confirmation_token,
                mutation.confirmation_token,
            ):
                raise CopilotConfirmationError(
                    "Confirmation token does not match the pending Copilot mutation."
                )
            if mutation.apply_tool_id and mutation.apply_tool_id != apply_tool_id:
                raise CopilotConfirmationError(
                    "Confirmation token is not valid for the requested mutation action."
                )
            if mutation.session_id is not None and session_id != mutation.session_id:
                raise CopilotConfirmationError(
                    "Confirmation token is not valid for this Copilot session."
                )
            if (
                mutation.context_fingerprint is not None
                and context_fingerprint != mutation.context_fingerprint
            ):
                raise CopilotConfirmationError(
                    "Copilot context changed after the mutation was drafted."
                )
            expected_hash = mutation.proposal_hash or self.proposal_hash(mutation.proposed_payload)
            if proposal_hash is not None and proposal_hash != expected_hash:
                raise CopilotConfirmationError(
                    "Mutation proposal changed after confirmation was requested."
                )
            if (
                mutation.proposal_hash is not None
                and proposal_hash is None
                and (
                    mutation.session_id is not None
                    or mutation.context_fingerprint is not None
                )
            ):
                raise CopilotConfirmationError(
                    "Mutation proposal hash is required for this confirmation."
                )
            return replace(
                mutation,
                status="confirmed",
                confirmed_at=now,
                proposal_hash=expected_hash,
            )

        consumed = self.store.update_mutation(mutation_id, validate_and_consume)
        if expired:
            self.store.sync_mutation_resolution(consumed)
            raise CopilotConfirmationError("Copilot mutation confirmation has expired.")
        return consumed

    def reject(
        self,
        *,
        mutation_id: str,
        session_id: str | None,
    ) -> CopilotDraftMutation:
        now = now_utc()

        def reject_pending(mutation: CopilotDraftMutation) -> CopilotDraftMutation:
            if mutation.status != "pending":
                raise CopilotConfirmationError(
                    f"Copilot mutation confirmation is not active: {mutation.status}"
                )
            if mutation.session_id is not None and mutation.session_id != session_id:
                raise CopilotConfirmationError(
                    "Confirmation token is not valid for this Copilot session."
                )
            return replace(mutation, status="rejected", rejected_at=now)

        return self.store.update_mutation(mutation_id, reject_pending)
