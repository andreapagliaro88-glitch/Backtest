"""Stake, stato e backtest per strategia 0 SH."""
from __future__ import annotations

import pandas as pd

from core.sh_common import (
    SH_FULL_STOP_DD,
    SH_LOSS_STREAK_TRIGGER,
    SH_PROFIT_LOSS,
    SH_PROFIT_WIN,
    SH_SHOCK_TRADES,
    SH_STAKE_U,
    SHState,
    preview_sh_stake,
    prepare_sh_data,
    print_sh_stats,
    run_sh_backtest_on_data,
    sh_settlement_profit_u,
)

# Alias retrocompatibilità
SH0State = SHState
SH0_DECIMAL_ODDS = 1.3
SH0_PROFIT_ODDS = SH_PROFIT_WIN
SH0_FULL_STOP_DD = SH_FULL_STOP_DD
SH0_SHOCK_TRADES = SH_SHOCK_TRADES
SH0_LOSS_STREAK_TRIGGER = SH_LOSS_STREAK_TRIGGER
SH0_BOOST_STAKE = SH_STAKE_U
SH0_BOOST_HISTORY = 60
SH0_BOOST_MIN_SIGNALS = 3


def sh0_base_stake(signals: int) -> float:
    return SH_STAKE_U if signals >= 1 else 0.0


def prepare_sh0_grouped(df: pd.DataFrame, patterns=None):
    return prepare_sh_data(df, "SH0", patterns)


def prepare_sh0_data(df: pd.DataFrame, patterns=None):
    return prepare_sh_data(df, "SH0", patterns)


def process_sh0_trade(row, state):
    from core.sh_common import process_sh_controlled_trade
    return process_sh_controlled_trade(row, state)


def run_sh0_backtest_on_data(data: pd.DataFrame) -> pd.DataFrame:
    return run_sh_backtest_on_data(data, "SH0")


def run_sh0_backtest(df: pd.DataFrame, patterns=None, tier_mode: bool = True, tier_rules=None) -> pd.DataFrame:
    if tier_mode:
        from core.tier_backtest import run_tier_backtest
        return run_tier_backtest(df, "SH0", patterns, rules=tier_rules)
    return run_sh_backtest_on_data(prepare_sh0_data(df, patterns), "SH0")


def print_sh0_stats(df_trades: pd.DataFrame):
    print_sh_stats(df_trades, "0 SH")
