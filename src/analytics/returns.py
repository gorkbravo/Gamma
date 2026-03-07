from __future__ import annotations

from typing import Dict

import pandas as pd


def align_prices(prices: Dict[str, pd.Series]) -> pd.DataFrame:
    frames = []
    for symbol, series in prices.items():
        s = series.copy()
        s.name = symbol
        frames.append(s)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, axis=1, join="inner").sort_index()
    return df


def compute_returns(price_df: pd.DataFrame) -> pd.DataFrame:
    if price_df.empty:
        return pd.DataFrame()
    returns = price_df.pct_change().dropna(how="all")
    return returns
