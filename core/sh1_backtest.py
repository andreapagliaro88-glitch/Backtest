"""Stake, stato e backtest per strategia 1 SH."""
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

SH1State = SHState

SH1_DECIMAL_ODDS = 1.3
SH1_PROFIT_ODDS = SH_PROFIT_WIN
SH1_FULL_STOP_DD = SH_FULL_STOP_DD
SH1_SHOCK_TRADES = SH_SHOCK_TRADES
SH1_LOSS_STREAK_TRIGGER = SH_LOSS_STREAK_TRIGGER
SH1_BOOST_STAKE = SH_STAKE_U
SH1_BOOST_HISTORY = 60
SH1_BOOST_MIN_SIGNALS = 3


def sh1_base_stake(signals: int) -> float:
    return SH_STAKE_U if signals >= 1 else 0.0


def prepare_sh1_grouped(df: pd.DataFrame, patterns=None):
    return prepare_sh_data(df, "SH1", patterns)


def prepare_sh1_data(df: pd.DataFrame, patterns=None):
    return prepare_sh_data(df, "SH1", patterns)


def process_sh1_trade(row, state):
    from core.sh_common import process_sh_controlled_trade
    return process_sh_controlled_trade(row, state)


def run_sh1_backtest_on_data(data: pd.DataFrame) -> pd.DataFrame:
    return run_sh_backtest_on_data(data, "SH1")


def run_sh1_backtest(df: pd.DataFrame, patterns=None, tier_mode: bool = True, tier_rules=None) -> pd.DataFrame:
    if tier_mode:
        from core.tier_backtest import run_tier_backtest
        return run_tier_backtest(df, "SH1", patterns, rules=tier_rules)
    return run_sh_backtest_on_data(prepare_sh1_data(df, patterns), "SH1")


def print_sh1_stats(df_trades: pd.DataFrame):
    print_sh_stats(df_trades, "1 SH")
