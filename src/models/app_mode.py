from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AppMode(str, Enum):
    PORTFOLIO = "portfolio"
    RESEARCH = "research"


class ResearchScopeType(str, Enum):
    NONE = "none"
    SINGLE_TICKER = "single_ticker"
    SYNTHETIC_PORTFOLIO = "synthetic_portfolio"


@dataclass(frozen=True)
class SyntheticPosition:
    symbol: str
    weight: float
