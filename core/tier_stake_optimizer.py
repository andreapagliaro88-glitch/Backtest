"""Simulazione stake tier — tutte le strategie, bilancio profit/DD."""
from __future__ import annotations

from dataclasses import asdict, replace
import random

import numpy as np
import pandas as pd

from core.tier_backtest import TierState, prepare_tier_data, process_tier_trade
from core.tier_config import default_tier_risk, profit_odds_for
from core.tier_engine import TierRules, rules_with_all_patterns
from core.tier_optimizer import list_patterns_for_system


def balanced_score(profit: float, max_dd: float, dd_weight: float = 0.6) -> float:
    return profit + max_dd * dd_weight


def _record_tier_events(df_raw: pd.DataFrame, system: str, rules: TierRules) -> list[dict]:
    data = prepare_tier_data(df_raw, system, patterns=None)
    if data.empty:
        return []

    state = TierState()
    risk = default_tier_risk(system)
    profit_odds = profit_odds_for(system)
    events: list[dict] = []

    for row in data.itertuples(index=False):
        patterns = list(row.patterns)
        from core.tier_engine import classify_tier

        tier = classify_tier(patterns, rules)
        if tier is None:
            state.profits.append(0)
            state.equity_history.append(state.equity)
            continue
        if tier == 4 and state.tier4_blocked > 0:
            state.tier4_blocked -= 1
            state.profits.append(0)
            state.equity_history.append(state.equity)
            continue

        mult = 1.0
        if state.t23_reduced and tier in (2, 3):
            mult *= risk.reduce_t23_factor
        if state.shock_mode > 0:
            mult *= risk.shock_factor
            state.shock_mode -= 1

        vinto = bool(row.vinto)
        events.append({"tier": tier, "vinto": vinto, "mult": mult})

        stake_placeholder = 1.0 * mult
        if vinto:
            profit = round(stake_placeholder * profit_odds, 4)
            state.loss_streak = 0
            state.t23_reduced = False
        else:
            profit = round(-stake_placeholder, 4)
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

    return events


def _metrics_from_events(
    events: list[dict],
    rules: TierRules,
    profit_odds: float,
    dd_weight: float,
) -> dict:
    stake_map = {1: rules.stake_t1, 2: rules.stake_t2, 3: rules.stake_t3, 4: rules.stake_t4}
    if not events:
        return {
            "profit": 0.0, "max_dd": 0.0, "trades": 0, "winrate": 0.0,
            "score": 0.0, "calmar": 0.0,
            "stake_t1": rules.stake_t1, "stake_t2": rules.stake_t2,
            "stake_t3": rules.stake_t3, "stake_t4": rules.stake_t4,
            "rules": asdict(rules),
        }

    profits = []
    for ev in events:
        stake = stake_map[ev["tier"]] * ev["mult"]
        profits.append(round(stake * profit_odds, 4) if ev["vinto"] else round(-stake, 4))

    arr = np.array(profits, dtype=float)
    equity = np.cumsum(arr)
    dd = equity - np.maximum.accumulate(equity)
    profit = float(arr.sum())
    max_dd = float(dd.min())
    trades = len(events)
    winrate = sum(1 for p in profits if p > 0) / trades if trades else 0.0
    score = balanced_score(profit, max_dd, dd_weight)
    calmar = profit / abs(max_dd) if max_dd < 0 else profit

    return {
        "profit": profit, "max_dd": max_dd, "trades": trades, "winrate": winrate,
        "score": score, "calmar": calmar,
        "stake_t1": rules.stake_t1, "stake_t2": rules.stake_t2,
        "stake_t3": rules.stake_t3, "stake_t4": rules.stake_t4,
        "rules": asdict(rules),
    }


def _stake_grid() -> list[tuple[float, float, float, float]]:
    t1_vals = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    t2_vals = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    t3_vals = [0.8, 1.0, 1.2, 1.5, 2.0, 2.5]
    t4_vals = [0.4, 0.6, 0.8, 1.0, 1.2, 1.5]
    combos: list[tuple[float, float, float, float]] = []
    for s1 in t1_vals:
        for s2 in t2_vals:
            if s2 > s1:
                continue
            for s3 in t3_vals:
                if s3 > s2:
                    continue
                for s4 in t4_vals:
                    if s4 > s3:
                        continue
                    combos.append((s1, s2, s3, s4))
    return combos


def _random_stakes(rng: random.Random) -> tuple[float, float, float, float]:
    s1 = rng.choice([3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    s2 = rng.uniform(1.5, s1)
    s3 = rng.uniform(0.6, min(s2, 3.0))
    s4 = rng.uniform(0.3, min(s3, 1.5))
    return round(s1, 2), round(s2, 2), round(s3, 2), round(s4, 2)


def simulate_all_patterns_stakes(
    df_raw: pd.DataFrame,
    system: str,
    base_rules: TierRules,
    *,
    dd_weight: float = 0.6,
    max_dd_limit: float | None = None,
    include_random: bool = True,
    random_iterations: int = 500,
    seed: int = 42,
) -> tuple[dict, pd.DataFrame, TierRules]:
    patterns = list_patterns_for_system(df_raw, system)
    if not patterns:
        return {}, pd.DataFrame(), base_rules

    rules_all = rules_with_all_patterns(patterns, base_rules)
    events = _record_tier_events(df_raw, system, rules_all)
    po = profit_odds_for(system)
    baseline = _metrics_from_events(events, rules_all, po, dd_weight)

    seen: set[tuple[float, float, float, float]] = set()
    rows: list[dict] = []

    for s1, s2, s3, s4 in _stake_grid():
        key = (s1, s2, s3, s4)
        if key in seen:
            continue
        seen.add(key)
        trial = replace(rules_all, stake_t1=s1, stake_t2=s2, stake_t3=s3, stake_t4=s4)
        rows.append(_metrics_from_events(events, trial, po, dd_weight))

    if include_random:
        rng = random.Random(seed)
        for _ in range(random_iterations):
            s1, s2, s3, s4 = _random_stakes(rng)
            key = (s1, s2, s3, s4)
            if key in seen:
                continue
            seen.add(key)
            trial = replace(rules_all, stake_t1=s1, stake_t2=s2, stake_t3=s3, stake_t4=s4)
            rows.append(_metrics_from_events(events, trial, po, dd_weight))

    df = pd.DataFrame(rows)
    if df.empty:
        return baseline, df, rules_all
    if max_dd_limit is not None:
        df = df[df["max_dd"] >= max_dd_limit]
    df = df.sort_values(["score", "profit"], ascending=False).reset_index(drop=True)
    return baseline, df, rules_all


def format_stake_combo(row) -> str:
    return (
        f"T1={row['stake_t1']:.2f} · T2={row['stake_t2']:.2f} · "
        f"T3={row['stake_t3']:.2f} · T4={row['stake_t4']:.2f}"
    )
