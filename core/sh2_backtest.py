"""Stake, stato e backtest per strategia 2 SH."""
from __future__ import annotations

import pandas as pd

from core.sh_common import (
    SH_FULL_STOP_DD,
    SH_LOSS_STREAK_TRIGGER,
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

SH2State = SHState

SH2_DECIMAL_ODDS = 1.3
SH2_PROFIT_ODDS = SH_PROFIT_WIN
SH2_FULL_STOP_DD = SH_FULL_STOP_DD
SH2_SHOCK_TRADES = SH_SHOCK_TRADES
SH2_LOSS_STREAK_TRIGGER = SH_LOSS_STREAK_TRIGGER
SH2_BOOST_STAKE = SH_STAKE_U
SH2_BOOST_HISTORY = 60
SH2_BOOST_MIN_SIGNALS = 3


def sh2_base_stake(signals: int) -> float:
    return SH_STAKE_U if signals >= 1 else 0.0


def prepare_sh2_grouped(df: pd.DataFrame, patterns=None):
    return prepare_sh_data(df, "SH2", patterns)


def prepare_sh2_data(df: pd.DataFrame, patterns=None):
    return prepare_sh_data(df, "SH2", patterns)


def process_sh2_trade(row, state):
    from core.sh_common import process_sh_controlled_trade
    return process_sh_controlled_trade(row, state)


def run_sh2_backtest_on_data(data: pd.DataFrame) -> pd.DataFrame:
    return run_sh_backtest_on_data(data, "SH2")


def run_sh2_backtest(df: pd.DataFrame, patterns=None, tier_mode: bool = True, tier_rules=None) -> pd.DataFrame:
    if tier_mode:
        from core.tier_backtest import run_tier_backtest
        return run_tier_backtest(df, "SH2", patterns, rules=tier_rules)
    return run_sh_backtest_on_data(prepare_sh2_data(df, patterns), "SH2")


def print_sh2_stats(df_trades: pd.DataFrame):
    print_sh_stats(df_trades, "2 SH")
