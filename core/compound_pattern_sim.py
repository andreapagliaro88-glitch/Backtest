"""Simulazione composta controllata su sequenza di pick (edge discovery)."""
from __future__ import annotations

import numpy as np

from compound_config import INITIAL_BANKROLL
from core.controlled_compounding import ControlledCompounding


def simulate_compound_controlled(
    wins: np.ndarray,
    odds: np.ndarray,
    initial_bankroll: float = INITIAL_BANKROLL,
    stake_u: float = 1.0,
) -> dict[str, float]:
    """
    Replica logica CCS: scaglioni fissi, stake max 1U.
    Win: profitto = stake × (quota - 1). Lose: -stake.
    """
    ccs = ControlledCompounding(initial_bankroll)
    max_dd_pct = 0.0

    for win, odd in zip(wins, odds):
        if not np.isfinite(odd) or odd <= 1.01:
            continue

        profit_odds = float(odd) - 1.0
        ccs.settle_trade(bool(win), profit_odds)
        max_dd_pct = min(max_dd_pct, ccs.drawdown_pct)

    s = ccs.summary()
    return {
        "compound_profit_eur": float(s["total_profit_eur"]),
        "compound_roi_pct": float(s["roi_pct"]),
        "compound_max_dd_pct": float(max_dd_pct),
        "compound_final_bankroll": float(s["final_bankroll"]),
        "compound_stake_eur": float(ccs.stake_eur()),
    }
