"""Maschere per scenari live (stato partita al minuto X)."""
from __future__ import annotations

import pandas as pd

from core.market_registry import LIVE_MARKET_DEFS


def apply_live_state_mask(df: pd.DataFrame, live_market_id: str) -> pd.Series:
    cfg = LIVE_MARKET_DEFS[live_market_id]
    mask = pd.Series(True, index=df.index)
    for col, op, val in cfg.get("live_rules", []):
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        if op == "eq":
            mask &= df[col].astype(int) == val
        elif op == "gt":
            mask &= df[col] > val
        else:
            mask &= df[col] < val
    return mask
