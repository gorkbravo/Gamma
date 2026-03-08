from __future__ import annotations


def normalize_market_data_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"delayed", "live", "auto"}:
        return mode
    return "delayed"


def market_data_mode_label(mode: str | None, mock_mode: bool) -> str:
    if mock_mode:
        return "Mock"
    return "Live" if normalize_market_data_mode(mode) == "live" else "Delayed"
