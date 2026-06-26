"""Logica condivisa 0/1/2 SH — dedup partite, quota 1.3, Composta Controllata."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.backtest_metrics import backtest_metrics

# Quota 1.3: ogni trade rischia 1U → +0.3U se vince, -1U se perde
SH_DECIMAL_ODDS = 1.3
SH_PROFIT_WIN = 0.3
SH_PROFIT_LOSS = -1.0
SH_STAKE_U = 1.0
SH_FULL_STOP_DD = -18.0
SH_SHOCK_TRADES = 5
SH_LOSS_STREAK_TRIGGER = 3


@dataclass
class SHControlledParams:
    shock_trades: int = SH_SHOCK_TRADES
    loss_streak_trigger: int = SH_LOSS_STREAK_TRIGGER
    full_stop_dd: float = SH_FULL_STOP_DD


class SHState:
    def __init__(self):
        self.equity = 0.0
        self.peak = 0.0
        self.profits: list[float] = []
        self.equity_history: list[float] = []
        self.loss_streak = 0
        self.shock_mode = 0


def prepare_sh_grouped(
    df: pd.DataFrame,
    patterns: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    """
    Unisce i pattern selezionati senza duplicare partite:
    stessa partita da più file → 1 solo segnale (max), 1 solo trade.
    """
    data = df.copy()
    if data.empty:
        return data

    if patterns:
        data = data[data["pattern"].isin(patterns)]

    if data.empty:
        return pd.DataFrame(columns=["match_id", "date", "goals_ft", "signals", "vinto"])

    grouped = data.groupby(["match_id", "date"], as_index=False).agg({
        "signal": "sum",
        "vinto": "max",
    })
    grouped = grouped.rename(columns={"signal": "signals"})
    grouped = grouped[grouped["signals"] > 0]
    grouped["date"] = pd.to_datetime(grouped["date"])
    return grouped


def prepare_sh_data(
    df: pd.DataFrame,
    system: str,
    patterns: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    if "system" in df.columns:
        data = df[df["system"] == system].drop(columns="system", errors="ignore")
    else:
        data = df

    if "pattern" in data.columns:
        return prepare_sh_grouped(data, patterns)

    grouped = data.groupby(["match_id", "date"]).agg({
        "signal": "sum",
        "vinto": "max",
    }).reset_index()
    grouped = grouped.rename(columns={"signal": "signals"})
    grouped = grouped[grouped["signals"] > 0]
    grouped["date"] = pd.to_datetime(grouped["date"])
    return grouped


def preview_sh_stake(row, state: SHState, params: SHControlledParams | None = None) -> float:
    """Calcolo stake per Trade Giornaliero — senza applicare P&L (come plan_match)."""
    p = params or SHControlledParams()
    if row["signals"] < 1:
        return 0.0
    if state.shock_mode > 0:
        return 0.0
    drawdown = state.equity - state.peak
    if drawdown - p.full_stop_dd < SH_STAKE_U:
        return 0.0
    return SH_STAKE_U


def sh_settlement_profit_u(stake_u: float, vinto: bool) -> float:
    """Stesso calcolo di apply_settlement in daily_trades (quota 1.3)."""
    if vinto:
        return round(stake_u * SH_PROFIT_WIN, 2)
    return -round(stake_u, 2)


def process_sh_controlled_trade(
    row,
    state: SHState,
    params: SHControlledParams | None = None,
) -> tuple[float, float, float]:
    """Composta controllata: 1U fissa, +0.3 / -1, stop a DD -18U."""
    p = params or SHControlledParams()

    if row["signals"] < 1:
        return 0.0, 0.0, state.equity

    if state.shock_mode > 0:
        state.shock_mode -= 1
        state.profits.append(0.0)
        state.equity_history.append(state.equity)
        return 0.0, 0.0, state.equity

    drawdown = state.equity - state.peak
    room = drawdown - p.full_stop_dd
    if room < SH_STAKE_U:
        state.profits.append(0.0)
        state.equity_history.append(state.equity)
        return 0.0, 0.0, state.equity

    stake = SH_STAKE_U
    won = row["vinto"] == 1 or row["vinto"] is True
    profit = SH_PROFIT_WIN if won else SH_PROFIT_LOSS

    if won:
        state.loss_streak = 0
    else:
        state.loss_streak += 1
        if state.loss_streak >= p.loss_streak_trigger:
            state.shock_mode = p.shock_trades
            state.loss_streak = 0

    state.equity += profit
    state.peak = max(state.peak, state.equity)
    state.profits.append(profit)
    state.equity_history.append(state.equity)
    return stake, profit, state.equity


def run_sh_backtest_params(
    data: pd.DataFrame,
    system: str,
    params: SHControlledParams | None = None,
) -> dict:
    p = params or SHControlledParams()
    data = data.copy()
    data = data[data["signals"] > 0].sort_values(["date", "signals"]).reset_index(drop=True)

    state = SHState()
    profits: list[float] = []
    stakes: list[float] = []

    for _, row in data.iterrows():
        stake, profit, _ = process_sh_controlled_trade(row, state, p)
        stakes.append(stake)
        profits.append(profit)

    if not profits:
        return {"profit": 0, "max_dd": 0, "trades": 0, "winrate": 0, "score": 0, "calmar": 0}

    import numpy as np
    equity = np.cumsum(profits)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    active = [s for s in stakes if s > 0]
    wins = [pr for pr, s in zip(profits, stakes) if s > 0 and pr > 0]

    profit = float(sum(profits))
    max_dd = float(dd.min())
    trades = len(active)
    winrate = len(wins) / trades if trades else 0
    score = profit + max_dd * 0.6

    return {
        "profit": profit,
        "max_dd": max_dd,
        "trades": trades,
        "winrate": winrate,
        "score": score,
        "calmar": profit / abs(max_dd) if max_dd < 0 else profit,
    }


def run_sh_backtest_on_data(data: pd.DataFrame, system: str) -> pd.DataFrame:
    data = data.copy()
    data = data[data["signals"] > 0].sort_values(["date", "signals"]).reset_index(drop=True)

    state = SHState()
    records = []
    for _, row in data.iterrows():
        stake, profit, equity = process_sh_controlled_trade(row, state)
        records.append([row["date"], system, stake, profit, equity])

    df_trades = pd.DataFrame(records, columns=["date", "system", "stake", "profit", "equity"])
    if df_trades.empty:
        df_trades["peak"] = []
        df_trades["dd"] = []
        return df_trades

    df_trades["peak"] = df_trades["equity"].cummax()
    df_trades["dd"] = df_trades["equity"] - df_trades["peak"]
    return df_trades


def print_sh_stats(df_trades: pd.DataFrame, label: str):
    m = backtest_metrics(df_trades)
    print(f"\n===== {label} =====")
    print(f"  Profit: {m['profit']:.2f} U")
    print(f"  Max DD: {m['max_dd']:.2f} U")
    print(f"  Trade attivi: {m['trades']}")
    print(f"  Winrate: {m['winrate'] * 100:.2f}%")
