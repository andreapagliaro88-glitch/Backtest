"""Simulazione stake O15 — wrapper."""
from core.tier_stake_optimizer import format_stake_combo, simulate_all_patterns_stakes


def simulate_o15_all_patterns_stakes(df_raw, base_rules, **kwargs):
    return simulate_all_patterns_stakes(df_raw, "O15", base_rules, **kwargs)
