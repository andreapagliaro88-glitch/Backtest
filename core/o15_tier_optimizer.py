"""Ottimizzazione tier O15 — wrapper."""
from core.tier_optimizer import (
    optimize_pattern_tiers,
    tier_rules_from_dict,
    tier_rules_to_dict,
)


def optimize_o15_pattern_tiers(
    df_raw,
    min_trades: int = 10,
    t3_quantile: float = 0.70,
    t4_quantile: float = 0.35,
):
    return optimize_pattern_tiers(
        df_raw, "O15",
        min_trades=min_trades,
        t3_quantile=t3_quantile,
        t4_quantile=t4_quantile,
    )
