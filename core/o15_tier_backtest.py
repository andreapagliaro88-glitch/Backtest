"""Backtest Over 1.5 con Metodo Tier — wrapper su tier_backtest generico."""
from __future__ import annotations

from core.tier_backtest import (
    TierState as O15TierState,
    prepare_tier_data,
    process_tier_trade as process_o15_tier_trade,
    run_tier_backtest,
    tier_summary,
)
from core.tier_engine import O15_TIER_RISK, O15_TIER_RULES


def prepare_o15_tier_data(df, patterns=None):
    return prepare_tier_data(df, "O15", patterns)


def run_o15_tier_backtest(df, patterns=None, rules=None):
    return run_tier_backtest(
        df, "O15", patterns, rules=rules or O15_TIER_RULES,
    )
