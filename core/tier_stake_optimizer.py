"""Simulazione stake tier — confronto combinazioni pattern con stake attuali."""
from __future__ import annotations

from dataclasses import asdict, replace
import random

import numpy as np
import pandas as pd

from core.tier_backtest import TierState, prepare_tier_records
from core.tier_config import default_tier_risk, profit_odds_for
from core.pattern_combo_optimizer import combo_label, enumerate_pattern_combos
from core.tier_engine import TierRules, classify_tier, rules_for_pattern_combo
from core.tier_optimizer import list_patterns_for_system


def balanced_score(profit: float, max_dd: float, dd_weight: float = 0.6) -> float:
    return profit + max_dd * dd_weight


def _record_tier_events_from_records(
    match_records: list,
    combo: tuple[str, ...],
    rules: TierRules,
    system: str,
) -> list[dict]:
    """Stessa logica del tab Combinazioni pattern — 1 passata dati, N combo."""
    combo_set = set(combo)
    risk = default_tier_risk(system)
    state = TierState()
    events: list[dict] = []

    for pats, vinto, _date in match_records:
        active = [p for p in pats if p in combo_set]
        if not active:
            continue

        tier = classify_tier(active, rules)
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

        events.append({"tier": tier, "vinto": vinto, "mult": mult})

        stake_placeholder = 1.0 * mult
        if vinto:
            profit = round(stake_placeholder * profit_odds_for(system), 4)
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
            "params": {
                "stake_t1": rules.stake_t1, "stake_t2": rules.stake_t2,
                "stake_t3": rules.stake_t3, "stake_t4": rules.stake_t4,
            },
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
        "params": {
            "stake_t1": rules.stake_t1, "stake_t2": rules.stake_t2,
            "stake_t3": rules.stake_t3, "stake_t4": rules.stake_t4,
        },
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


def _append_stake_trials(
    events: list[dict],
    rules: TierRules,
    po: float,
    dd_weight: float,
    seen: set[tuple[float, float, float, float]],
    rows: list[dict],
    *,
    include_random: bool,
    random_iterations: int,
    rng: random.Random | None,
) -> None:
    for s1, s2, s3, s4 in _stake_grid():
        key = (s1, s2, s3, s4)
        if key in seen:
            continue
        seen.add(key)
        trial = replace(rules, stake_t1=s1, stake_t2=s2, stake_t3=s3, stake_t4=s4)
        row = _metrics_from_events(events, trial, po, dd_weight)
        rows.append(row)

    if include_random and rng and random_iterations > 0:
        for _ in range(random_iterations):
            s1, s2, s3, s4 = _random_stakes(rng)
            key = (s1, s2, s3, s4)
            if key in seen:
                continue
            seen.add(key)
            trial = replace(rules, stake_t1=s1, stake_t2=s2, stake_t3=s3, stake_t4=s4)
            row = _metrics_from_events(events, trial, po, dd_weight)
            rows.append(row)


def _resolve_pattern_combo(
    df_raw: pd.DataFrame,
    system: str,
    patterns: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    available = list_patterns_for_system(df_raw, system)
    if not available:
        return tuple()
    if patterns:
        return tuple(p for p in patterns if p in available)
    return tuple(available)


def optimize_tier_stakes(
    df_raw: pd.DataFrame,
    system: str,
    base_rules: TierRules,
    patterns: tuple[str, ...] | list[str] | None = None,
    *,
    dd_weight: float = 0.6,
    max_dd_limit: float | None = None,
    include_random: bool = True,
    random_iterations: int = 500,
    seed: int = 42,
) -> tuple[dict, pd.DataFrame]:
    """Ottimizza stake T1/T2/T3/T4 con backtest tier sui pattern attivi."""
    pat_tuple = _resolve_pattern_combo(df_raw, system, patterns)
    if not pat_tuple:
        return {}, pd.DataFrame()

    rules = rules_for_pattern_combo(pat_tuple, base_rules)
    po = profit_odds_for(system)

    if "system" in df_raw.columns:
        sys_df = df_raw[df_raw["system"] == system]
    else:
        sys_df = df_raw
    match_records = prepare_tier_records(sys_df, system)
    events = _record_tier_events_from_records(match_records, pat_tuple, rules, system)

    baseline = _metrics_from_events(events, rules, po, dd_weight)

    seen: set[tuple[float, float, float, float]] = set()
    rows: list[dict] = []
    rng = random.Random(seed) if include_random else None
    _append_stake_trials(
        events, rules, po, dd_weight, seen, rows,
        include_random=include_random,
        random_iterations=random_iterations,
        rng=rng,
    )

    df = pd.DataFrame(rows)
    if df.empty:
        return baseline, df

    if max_dd_limit is not None:
        df = df[df["max_dd"] >= max_dd_limit]
    df = df.sort_values(["score", "profit"], ascending=False).reset_index(drop=True)
    return baseline, df


def simulate_stakes_by_pattern_combos(
    df_raw: pd.DataFrame,
    system: str,
    base_rules: TierRules,
    *,
    dd_weight: float = 0.6,
    max_dd_limit: float | None = None,
    progress_callback=None,
    **_,
) -> tuple[dict, pd.DataFrame, pd.DataFrame, TierRules]:
    """
    Per ogni combinazione di pattern (N, N-1, …, 1) calcola profit/DD
    con le stake T1/T2/T3/T4 attuali (una riga per combinazione).
    """
    patterns = list_patterns_for_system(df_raw, system)
    if not patterns:
        return {}, pd.DataFrame(), pd.DataFrame(), base_rules

    all_patterns = tuple(patterns)
    rules_all = rules_for_pattern_combo(all_patterns, base_rules)
    po = profit_odds_for(system)
    combos = enumerate_pattern_combos(patterns)
    total = len(combos)
    rows: list[dict] = []

    if "system" in df_raw.columns:
        sys_df = df_raw[df_raw["system"] == system]
    else:
        sys_df = df_raw
    match_records = prepare_tier_records(sys_df, system)

    for i, combo in enumerate(combos):
        combo_rules = rules_for_pattern_combo(combo, base_rules)
        events = _record_tier_events_from_records(match_records, combo, combo_rules, system)
        row = _metrics_from_events(events, combo_rules, po, dd_weight)
        row.update({
            "combo": combo_label(combo),
            "n_patterns": len(combo),
            "patterns": list(combo),
        })
        rows.append(row)
        if progress_callback and total:
            progress_callback((i + 1) / total)

    df = pd.DataFrame(rows)
    if df.empty:
        return {}, df, df, rules_all

    if max_dd_limit is not None:
        df = df[df["max_dd"] >= max_dd_limit]
    df = df.sort_values(["score", "profit"], ascending=False).reset_index(drop=True)

    baseline_events = _record_tier_events_from_records(match_records, all_patterns, rules_all, system)
    baseline = _metrics_from_events(baseline_events, rules_all, po, dd_weight)
    baseline.update({
        "combo": combo_label(all_patterns),
        "n_patterns": len(all_patterns),
        "patterns": list(all_patterns),
    })

    return baseline, df, df.copy(), rules_all


def simulate_all_patterns_stakes(
    df_raw: pd.DataFrame,
    system: str,
    base_rules: TierRules,
    *,
    dd_weight: float = 0.6,
    max_dd_limit: float | None = None,
    progress_callback=None,
    **kwargs,
) -> tuple[dict, pd.DataFrame, TierRules]:
    baseline, results, _best, rules_all = simulate_stakes_by_pattern_combos(
        df_raw,
        system,
        base_rules,
        dd_weight=dd_weight,
        max_dd_limit=max_dd_limit,
        progress_callback=progress_callback,
        **kwargs,
    )
    return baseline, results, rules_all


def format_stake_combo(row) -> str:
    return (
        f"T1={row['stake_t1']:.2f} · T2={row['stake_t2']:.2f} · "
        f"T3={row['stake_t3']:.2f} · T4={row['stake_t4']:.2f}"
    )
