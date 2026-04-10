from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FundamentalsResearchStore:
    def __init__(self, base_dir: str | Path = "data/fundamentals") -> None:
        self.base_dir = Path(base_dir)
        self.peer_dir = self.base_dir / "peer_baskets"
        self.dcf_dir = self.base_dir / "dcf_models"
        self.peer_dir.mkdir(parents=True, exist_ok=True)
        self.dcf_dir.mkdir(parents=True, exist_ok=True)

    def load_peer_basket(self, ticker: str) -> dict[str, Any] | None:
        return self._load_json(self.peer_dir / f"{self._safe_key(ticker)}.json")

    def save_peer_basket(self, ticker: str, payload: dict[str, Any]) -> None:
        self._write_json(self.peer_dir / f"{self._safe_key(ticker)}.json", payload)

    def load_dcf_model(self, ticker: str) -> dict[str, Any] | None:
        return self._load_json(self.dcf_dir / f"{self._safe_key(ticker)}.json")

    def save_dcf_model(self, ticker: str, payload: dict[str, Any]) -> None:
        self._write_json(self.dcf_dir / f"{self._safe_key(ticker)}.json", payload)

    def _load_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _safe_key(self, ticker: str) -> str:
        return str(ticker or "").strip().upper().replace("/", "_").replace("\\", "_")
