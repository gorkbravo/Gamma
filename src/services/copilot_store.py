from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.copilot import (
    CopilotContextSnapshot,
    CopilotMemo,
    CopilotResearchCardResult,
    CopilotSession,
    CopilotSourceRef,
    CopilotToolTrace,
    CopilotTurn,
    ResearchCard,
    ResearchClaim,
    new_copilot_id,
)
from src.utils.time import now_utc


CURRENT_COPILOT_STORE_SCHEMA_VERSION = 1


class CopilotStore:
    def __init__(self, base_dir: str | Path = "data/copilot") -> None:
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.turns_dir = self.base_dir / "turns"
        self.memos_dir = self.base_dir / "memos"
        for directory in (self.sessions_dir, self.snapshots_dir, self.turns_dir, self.memos_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_sessions(self, *, include_archived: bool = False, search: str | None = None) -> list[CopilotSession]:
        with self._lock:
            sessions = [item for path in self.sessions_dir.glob("*.json") if (item := self._load_session_path(path))]
        if not include_archived:
            sessions = [session for session in sessions if session.archived_at is None]
        query = str(search or "").strip().lower()
        if query:
            sessions = [
                session
                for session in sessions
                if query in session.title.lower()
                or query in session.session_id.lower()
                or query in str(session.active_domain or "").lower()
                or any(query in warning.lower() for warning in session.warnings)
            ]
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def get_session(self, session_id: str) -> CopilotSession | None:
        safe_id = self._safe_id(session_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_session_path(self.sessions_dir / f"{safe_id}.json")

    def list_turns(self, session_id: str) -> list[CopilotTurn]:
        safe_id = self._safe_id(session_id)
        if not safe_id:
            return []
        turns_dir = self.turns_dir / safe_id
        with self._lock:
            turns = [item for path in turns_dir.glob("*.json") if (item := self._load_turn_path(path))]
        return sorted(turns, key=lambda item: item.turn_index)

    def list_memos(self, session_id: str | None = None) -> list[CopilotMemo]:
        safe_session_id = self._safe_id(session_id) if session_id else None
        with self._lock:
            memos = [item for path in self.memos_dir.glob("*.json") if (item := self._load_memo_path(path))]
        if safe_session_id:
            memos = [memo for memo in memos if memo.session_id == safe_session_id]
        return sorted(memos, key=lambda item: item.updated_at, reverse=True)

    def record_turn(
        self,
        *,
        session_id: str | None,
        title: str | None,
        domain: str,
        current_tab: str,
        workspace_mode: str | None,
        prompt: str | None,
        context_fingerprint: str | None,
        context_summary: dict[str, Any],
        result: CopilotResearchCardResult,
    ) -> tuple[CopilotSession, CopilotContextSnapshot, CopilotTurn]:
        now = now_utc()
        safe_session_id = self._safe_id(session_id) or new_copilot_id("session")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            existing_turns = self._load_turns_unlocked(safe_session_id)
            if session is None:
                session = CopilotSession(
                    session_id=safe_session_id,
                    title=self._session_title(title, domain, result, prompt),
                    created_at=now,
                    updated_at=now,
                )

            snapshot = CopilotContextSnapshot(
                snapshot_id=new_copilot_id("ctx"),
                domain=domain,
                context_fingerprint=context_fingerprint,
                current_tab=current_tab,
                workspace_mode=workspace_mode,
                summary=context_summary,
                source_ids=[source.source_id for source in result.sources],
                warnings=list(result.warnings),
                created_at=now,
            )
            turn = CopilotTurn(
                turn_id=new_copilot_id("turn"),
                session_id=safe_session_id,
                turn_index=len(existing_turns),
                domain=domain,
                prompt=str(prompt or "").strip(),
                context_snapshot_id=snapshot.snapshot_id,
                result=result,
                created_at=now,
            )
            memo_count = len([memo for memo in self._load_memos_unlocked() if memo.session_id == safe_session_id])
            next_session = CopilotSession(
                session_id=safe_session_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=now,
                active_domain=domain,
                active_context_fingerprint=context_fingerprint,
                turn_count=len(existing_turns) + 1,
                memo_count=memo_count,
                warnings=list(dict.fromkeys([*session.warnings, *result.warnings])),
                archived_at=None,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(next_session))
            self._write_json(self.snapshots_dir / f"{snapshot.snapshot_id}.json", self._snapshot_to_json(snapshot))
            self._write_json(self.turns_dir / safe_session_id / f"{turn.turn_id}.json", self._turn_to_json(turn))
        return next_session, snapshot, turn

    def create_memo(
        self,
        *,
        session_id: str,
        title: str | None = None,
        notes: str | None = None,
        source_turn_ids: list[str] | None = None,
    ) -> CopilotMemo:
        safe_session_id = self._safe_id(session_id)
        if not safe_session_id:
            raise ValueError("session_id is required.")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            if session is None:
                raise ValueError(f"Copilot session not found: {session_id}")
            turns = self._load_turns_unlocked(safe_session_id)
            selected_ids = [self._safe_id(item) for item in source_turn_ids or [] if self._safe_id(item)]
            selected_turns = [turn for turn in turns if not selected_ids or turn.turn_id in selected_ids]
            if not selected_turns:
                raise ValueError("No Copilot turns are available for memo generation.")
            now = now_utc()
            memo_title = str(title or "").strip() or f"{session.title} Memo"
            memo = CopilotMemo(
                memo_id=new_copilot_id("memo"),
                session_id=safe_session_id,
                title=memo_title,
                body=self._build_memo_body(memo_title, selected_turns, notes),
                source_turn_ids=[turn.turn_id for turn in selected_turns],
                source_snapshot_ids=[turn.context_snapshot_id for turn in selected_turns],
                created_at=now,
                updated_at=now,
                warnings=list(dict.fromkeys(warning for turn in selected_turns for warning in turn.result.warnings)),
            )
            self._write_json(self.memos_dir / f"{memo.memo_id}.json", self._memo_to_json(memo))
            updated_session = CopilotSession(
                session_id=session.session_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=now,
                active_domain=session.active_domain,
                active_context_fingerprint=session.active_context_fingerprint,
                turn_count=session.turn_count,
                memo_count=len([item for item in self._load_memos_unlocked() if item.session_id == safe_session_id]),
                warnings=session.warnings,
                archived_at=session.archived_at,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(updated_session))
        return memo

    def archive_session(self, session_id: str) -> CopilotSession:
        safe_session_id = self._safe_id(session_id)
        if not safe_session_id:
            raise ValueError("session_id is required.")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            if session is None:
                raise ValueError(f"Copilot session not found: {session_id}")
            now = now_utc()
            archived = CopilotSession(
                session_id=session.session_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=now,
                active_domain=session.active_domain,
                active_context_fingerprint=session.active_context_fingerprint,
                turn_count=session.turn_count,
                memo_count=session.memo_count,
                warnings=session.warnings,
                archived_at=now,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(archived))
        return archived

    def update_memo(self, memo_id: str, *, title: str | None = None, body: str | None = None) -> CopilotMemo:
        safe_memo_id = self._safe_id(memo_id)
        if not safe_memo_id:
            raise ValueError("memo_id is required.")
        with self._lock:
            memo = self._load_memo_path(self.memos_dir / f"{safe_memo_id}.json")
            if memo is None:
                raise ValueError(f"Copilot memo not found: {memo_id}")
            next_title = str(title or "").strip() or memo.title
            next_body = str(body if body is not None else memo.body).strip()
            if not next_body:
                raise ValueError("memo body cannot be empty.")
            updated = CopilotMemo(
                memo_id=memo.memo_id,
                session_id=memo.session_id,
                title=next_title[:140],
                body=next_body,
                source_turn_ids=memo.source_turn_ids,
                source_snapshot_ids=memo.source_snapshot_ids,
                created_at=memo.created_at,
                updated_at=now_utc(),
                warnings=memo.warnings,
                source_provider=memo.source_provider,
                origin=memo.origin,
                transformation_note=memo.transformation_note,
            )
            self._write_json(self.memos_dir / f"{safe_memo_id}.json", self._memo_to_json(updated))
        return updated

    def get_memo(self, memo_id: str) -> CopilotMemo | None:
        safe_memo_id = self._safe_id(memo_id)
        if not safe_memo_id:
            return None
        with self._lock:
            return self._load_memo_path(self.memos_dir / f"{safe_memo_id}.json")

    def _load_turns_unlocked(self, session_id: str) -> list[CopilotTurn]:
        turns_dir = self.turns_dir / session_id
        turns = [item for path in turns_dir.glob("*.json") if (item := self._load_turn_path(path))]
        return sorted(turns, key=lambda item: item.turn_index)

    def _load_memos_unlocked(self) -> list[CopilotMemo]:
        return [item for path in self.memos_dir.glob("*.json") if (item := self._load_memo_path(path))]

    def _load_session_path(self, path: Path) -> CopilotSession | None:
        payload = self._load_json(path)
        if payload is None:
            return None
        return CopilotSession(
            session_id=str(payload.get("session_id") or path.stem),
            title=str(payload.get("title") or "Copilot Session"),
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
            active_domain=payload.get("active_domain"),
            active_context_fingerprint=payload.get("active_context_fingerprint"),
            turn_count=int(payload.get("turn_count") or 0),
            memo_count=int(payload.get("memo_count") or 0),
            warnings=list(payload.get("warnings") or []),
            archived_at=self._parse_datetime(payload.get("archived_at")),
        )

    def _load_turn_path(self, path: Path) -> CopilotTurn | None:
        payload = self._load_json(path)
        if payload is None:
            return None
        result = self._result_from_json(dict(payload.get("result") or {}))
        return CopilotTurn(
            turn_id=str(payload.get("turn_id") or path.stem),
            session_id=str(payload.get("session_id") or path.parent.name),
            turn_index=int(payload.get("turn_index") or 0),
            domain=str(payload.get("domain") or result.domain),
            prompt=str(payload.get("prompt") or ""),
            context_snapshot_id=str(payload.get("context_snapshot_id") or ""),
            result=result,
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
        )

    def _load_memo_path(self, path: Path) -> CopilotMemo | None:
        payload = self._load_json(path)
        if payload is None:
            return None
        return CopilotMemo(
            memo_id=str(payload.get("memo_id") or path.stem),
            session_id=str(payload.get("session_id") or ""),
            title=str(payload.get("title") or "Copilot Memo"),
            body=str(payload.get("body") or ""),
            source_turn_ids=list(payload.get("source_turn_ids") or []),
            source_snapshot_ids=list(payload.get("source_snapshot_ids") or []),
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
            warnings=list(payload.get("warnings") or []),
            source_provider=str(payload.get("source_provider") or "gamma_copilot"),
            origin=str(payload.get("origin") or "copilot_store.memo"),
            transformation_note=payload.get("transformation_note"),
        )

    def _load_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    @staticmethod
    def _session_to_json(session: CopilotSession) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "active_domain": session.active_domain,
            "active_context_fingerprint": session.active_context_fingerprint,
            "turn_count": session.turn_count,
            "memo_count": session.memo_count,
            "warnings": list(session.warnings),
            "archived_at": session.archived_at.isoformat() if session.archived_at else None,
        }

    @staticmethod
    def _snapshot_to_json(snapshot: CopilotContextSnapshot) -> dict[str, Any]:
        payload = asdict(snapshot)
        payload["schema_version"] = CURRENT_COPILOT_STORE_SCHEMA_VERSION
        payload["created_at"] = snapshot.created_at.isoformat()
        return payload

    @classmethod
    def _turn_to_json(cls, turn: CopilotTurn) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "turn_id": turn.turn_id,
            "session_id": turn.session_id,
            "turn_index": turn.turn_index,
            "domain": turn.domain,
            "prompt": turn.prompt,
            "context_snapshot_id": turn.context_snapshot_id,
            "result": cls._result_to_json(turn.result),
            "created_at": turn.created_at.isoformat(),
        }

    @staticmethod
    def _memo_to_json(memo: CopilotMemo) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "memo_id": memo.memo_id,
            "session_id": memo.session_id,
            "title": memo.title,
            "body": memo.body,
            "source_turn_ids": list(memo.source_turn_ids),
            "source_snapshot_ids": list(memo.source_snapshot_ids),
            "created_at": memo.created_at.isoformat(),
            "updated_at": memo.updated_at.isoformat(),
            "warnings": list(memo.warnings),
            "source_provider": memo.source_provider,
            "origin": memo.origin,
            "transformation_note": memo.transformation_note,
        }

    @staticmethod
    def _result_to_json(result: CopilotResearchCardResult) -> dict[str, Any]:
        return {
            "domain": result.domain,
            "current_tab": result.current_tab,
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "response_id": result.response_id,
            "message": result.message,
            "card": asdict(result.card) if result.card else None,
            "sources": [
                {
                    **asdict(source),
                    "retrieved_at": source.retrieved_at.isoformat() if source.retrieved_at else None,
                }
                for source in result.sources
            ],
            "tool_traces": [asdict(trace) for trace in result.tool_traces],
            "warnings": list(result.warnings),
        }

    @classmethod
    def _result_from_json(cls, payload: dict[str, Any]) -> CopilotResearchCardResult:
        return CopilotResearchCardResult(
            domain=str(payload.get("domain") or "synthesis"),
            current_tab=str(payload.get("current_tab") or payload.get("domain") or "copilot"),
            status=str(payload.get("status") or "ready"),
            provider=str(payload.get("provider") or "unknown"),
            model=payload.get("model"),
            response_id=payload.get("response_id"),
            message=payload.get("message"),
            card=cls._card_from_json(payload.get("card")),
            sources=[cls._source_from_json(item) for item in list(payload.get("sources") or []) if isinstance(item, dict)],
            tool_traces=[cls._trace_from_json(item) for item in list(payload.get("tool_traces") or []) if isinstance(item, dict)],
            warnings=list(payload.get("warnings") or []),
        )

    @staticmethod
    def _card_from_json(payload: Any) -> ResearchCard | None:
        if not isinstance(payload, dict):
            return None
        return ResearchCard(
            title=str(payload.get("title") or ""),
            hypothesis=str(payload.get("hypothesis") or ""),
            rationale=str(payload.get("rationale") or ""),
            required_data=list(payload.get("required_data") or []),
            proposed_test=str(payload.get("proposed_test") or ""),
            confounders=list(payload.get("confounders") or []),
            next_steps=list(payload.get("next_steps") or []),
            caveats=list(payload.get("caveats") or []),
            source_backed_claims=[
                ResearchClaim(claim=str(item.get("claim") or ""), evidence_refs=list(item.get("evidence_refs") or []))
                for item in list(payload.get("source_backed_claims") or [])
                if isinstance(item, dict)
            ],
            inferred_claims=list(payload.get("inferred_claims") or []),
        )

    @classmethod
    def _source_from_json(cls, payload: dict[str, Any]) -> CopilotSourceRef:
        return CopilotSourceRef(
            source_id=str(payload.get("source_id") or ""),
            label=str(payload.get("label") or ""),
            kind=str(payload.get("kind") or ""),
            provider=str(payload.get("provider") or ""),
            origin=str(payload.get("origin") or ""),
            description=payload.get("description"),
            retrieved_at=cls._parse_datetime(payload.get("retrieved_at")),
        )

    @staticmethod
    def _trace_from_json(payload: dict[str, Any]) -> CopilotToolTrace:
        return CopilotToolTrace(
            tool_name=str(payload.get("tool_name") or ""),
            summary=str(payload.get("summary") or ""),
            arguments=dict(payload.get("arguments") or {}),
            source_ids=list(payload.get("source_ids") or []),
        )

    @staticmethod
    def _build_memo_body(title: str, turns: list[CopilotTurn], notes: str | None) -> str:
        lines = [f"# {title}", "", "## Source Turns"]
        if notes:
            lines.extend(["", str(notes).strip(), ""])
        for turn in turns:
            card = turn.result.card
            lines.append(f"### Turn {turn.turn_index + 1} / {turn.domain}")
            if turn.prompt:
                lines.append(f"Prompt: {turn.prompt}")
            if card:
                lines.extend(
                    [
                        f"Hypothesis: {card.hypothesis}",
                        f"Rationale: {card.rationale}",
                        f"Proposed test: {card.proposed_test}",
                    ]
                )
                if card.next_steps:
                    lines.append("Next steps:")
                    lines.extend(f"- {item}" for item in card.next_steps)
            if turn.result.warnings:
                lines.append("Warnings:")
                lines.extend(f"- {item}" for item in turn.result.warnings)
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _session_title(
        title: str | None,
        domain: str,
        result: CopilotResearchCardResult,
        prompt: str | None = None,
    ) -> str:
        explicit = str(title or "").strip()
        if explicit:
            return explicit[:96]
        card_title = result.card.title if result.card else ""
        prompt_title = str(prompt or "").strip().replace("\n", " ")
        if prompt_title:
            return prompt_title[:96]
        return (card_title or f"{domain.replace('_', ' ').title()} Copilot Session")[:96]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _safe_id(value: str | None) -> str:
        return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"_", "-"})
