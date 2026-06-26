"""Backtest con Metodo Tier — qualsiasi strategia con pattern."""
from __future__ import annotations

import pandas as pd

from core.match_grouping import group_by_fixture
from core.tier_config import default_tier_risk, default_tier_rules, profit_odds_for
from core.tier_engine import (
    TierRules,
    classify_tier,
    stake_u_for_tier,
    tier_label,
)


class TierState:
    def __init__(self):
        self.equity = 0.0
        self.peak = 0.0
        self.profits: list[float] = []
        self.equity_history: list[float] = []
        self.loss_streak = 0
        self.shock_mode = 0
        self.tier4_blocked = 0
        self.t23_reduced = False


def prepare_tier_data(
    df: pd.DataFrame,
    system: str,
    patterns: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    """Una riga per partita — più file → 1 giocata, pattern aggregati."""
    return group_by_fixture(
        df,
        patterns,
        system=system,
        include_pattern_list=True,
    )


def process_tier_trade(row, state: TierState, rules: TierRules, risk, profit_odds: float):
    patterns = list(row.patterns) if hasattr(row, "patterns") else list(row["patterns"])
    tier = classify_tier(patterns, rules)
    if tier is None:
        state.profits.append(0)
        state.equity_history.append(state.equity)
        return 0, 0, state.equity, None, patterns

    if tier == 4 and state.tier4_blocked > 0:
        state.tier4_blocked -= 1
        state.profits.append(0)
        state.equity_history.append(state.equity)
        return 0, 0, state.equity, tier, patterns

    stake = stake_u_for_tier(tier, rules)
    if state.t23_reduced and tier in (2, 3):
        stake *= risk.reduce_t23_factor
    if state.shock_mode > 0:
        stake *= risk.shock_factor
        state.shock_mode -= 1

    vinto = bool(row.vinto)
    if vinto:
        profit = round(stake * profit_odds, 4)
        state.loss_streak = 0
        state.t23_reduced = False
    else:
        profit = round(-stake, 4)
        state.loss_streak += 1
        if state.loss_streak >= risk.loss_streak_trigger:
            state.tier4_blocked = max(state.tier4_blocked, risk.block_tier4_trades)
            state.t23_reduced = True
        if state.loss_streak >= risk.loss_streak_shock:
            state.shock_mode = risk.shock_trades
            state.loss_streak = 0

    state.equity = round(state.equity + profit, 4)
    state.peak = max(state.peak, state.equity)
    state.profits.append(profit)
    state.equity_history.append(state.equity)
    return stake, profit, state.equity, tier, patterns


def run_tier_backtest(
    df: pd.DataFrame,
    system: str,
    patterns=None,
    rules: TierRules | None = None,
) -> pd.DataFrame:
    rules = rules or default_tier_rules(system)
    risk = default_tier_risk(system)
    profit_odds = profit_odds_for(system)
    data = prepare_tier_data(df, system, patterns)
    if data.empty:
        return pd.DataFrame(columns=[
            "date", "system", "stake", "profit", "equity", "peak", "dd",
            "tier", "tier_label", "patterns", "patterns_str", "n_engines", "vinto",
        ])

    state = TierState()
    records = []
    for row in data.itertuples(index=False):
        stake, profit, equity, tier, pats = process_tier_trade(
            row, state, rules=rules, risk=risk, profit_odds=profit_odds,
        )
        patterns_str = " + ".join(pats) if pats else ""
        vinto = bool(row.vinto) if stake > 0 else False
        records.append([
            row.date, system, stake, profit, equity,
            tier if tier is not None else 0,
            tier_label(tier) if tier else "SKIP",
            patterns_str, len(pats), vinto,
        ])

    df_trades = pd.DataFrame(records, columns=[
        "date", "system", "stake", "profit", "equity",
        "tier", "tier_label", "patterns_str", "n_engines", "vinto",
    ])
    df_trades["patterns"] = df_trades["patterns_str"]
    df_trades["peak"] = df_trades["equity"].cummax()
    df_trades["dd"] = df_trades["equity"] - df_trades["peak"]
    return df_trades


def tier_summary(df_trades: pd.DataFrame) -> pd.DataFrame:
    active = df_trades[df_trades["stake"] > 0].copy()
    if active.empty or "tier" not in active.columns:
        return pd.DataFrame()

    rows = []
    for tier in sorted(active["tier"].unique()):
        sub = active[active["tier"] == tier]
        profit = float(sub["profit"].sum())
        max_dd = float(sub["dd"].min()) if "dd" in sub.columns else 0.0
        trades = len(sub)
        wr = float((sub["profit"] > 0).mean()) if trades else 0.0
        rows.append({
            "Tier": tier_label(int(tier)),
            "Trade": trades,
            "Profit (U)": round(profit, 2),
            "Max DD (U)": round(max_dd, 2),
            "Winrate": f"{wr * 100:.1f}%",
            "Stake medio (U)": round(float(sub["stake"].mean()), 2),
        })
    return pd.DataFrame(rows)
