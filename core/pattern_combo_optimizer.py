"""Ottimizzazione combinazioni di pattern (file Excel) per qualsiasi strategia."""
from __future__ import annotations

import itertools
import math
from typing import Callable, Iterable

import pandas as pd

from core.backtest_metrics import backtest_metrics
from core.tier_backtest import prepare_tier_records


def combo_label(patterns: tuple[str, ...]) -> str:
    return " + ".join(patterns)


def enumerate_pattern_combos(
    patterns: Iterable[str],
    *,
    max_size: int | None = None,
) -> list[tuple[str, ...]]:
    pats = list(patterns)
    upper = len(pats) if max_size is None else min(len(pats), max_size)
    combos = []
    for size in range(1, upper + 1):
        combos.extend(itertools.combinations(pats, size))
    return combos


def count_pattern_combos(n_patterns: int, *, max_size: int | None = None) -> int:
    upper = n_patterns if max_size is None else min(n_patterns, max_size)
    return sum(
        len(list(itertools.combinations(range(n_patterns), size)))
        for size in range(1, upper + 1)
    )


def list_available_patterns(df: pd.DataFrame, system: str | None = None) -> list[str]:
    if df.empty or "pattern" not in df.columns:
        return []
    data = df if system is None else df[df["system"] == system]
    return sorted(data["pattern"].dropna().unique().tolist())


def optimize_pattern_combos(
    df_raw: pd.DataFrame,
    run_backtest_fn: Callable,
    patterns: list[str] | None = None,
    system: str | None = None,
) -> pd.DataFrame:
    """
    Testa tutte le combinazioni possibili di pattern (da N a 1).
    Es. 5 file → C(5,5)+C(5,4)+C(5,3)+C(5,2)+C(5,1) = 31 backtest.
    """
    available = patterns or list_available_patterns(df_raw, system)
    if not available:
        return pd.DataFrame()

    rows = []
    for combo in enumerate_pattern_combos(available):
        trades = run_backtest_fn(df_raw, combo)
        metrics = backtest_metrics(trades)
        metrics["patterns"] = list(combo)
        metrics["combo"] = combo_label(combo)
        metrics["n_patterns"] = len(combo)
        rows.append(metrics)

    df = pd.DataFrame(rows)
    return df.sort_values(["score", "profit"], ascending=[False, False]).reset_index(drop=True)


def optimize_tier_pattern_combos(
    df_raw: pd.DataFrame,
    system: str,
    rules,
    patterns: list[str] | None = None,
    *,
    max_combo_size: int | None = None,
    progress_callback: Callable[[float], None] | None = None,
    dd_weight: float = 0.6,
) -> pd.DataFrame:
    """
    Ottimizzazione veloce tier: stesso motore di Simula stake
    (regole adattate per combo + eventi tier).
    """
    available = patterns or list_available_patterns(df_raw, system)
    if not available:
        return pd.DataFrame()

    if "system" in df_raw.columns:
        sys_df = df_raw[df_raw["system"] == system]
    else:
        sys_df = df_raw
    match_records = prepare_tier_records(sys_df, system)
    combos = enumerate_pattern_combos(available, max_size=max_combo_size)
    total = len(combos)
    rows = []

    from core.tier_stake_optimizer import evaluate_pattern_combo

    for i, combo in enumerate(combos):
        rows.append(
            evaluate_pattern_combo(match_records, combo, system, rules, dd_weight=dd_weight)
        )
        if progress_callback and total:
            progress_callback((i + 1) / total)

    df = pd.DataFrame(rows)
    return df.sort_values(["score", "profit"], ascending=[False, False]).reset_index(drop=True)


def make_system_combo_optimizer(system: str, run_backtest_fn: Callable):
    """Ottimizza combinazioni usando solo i dati del sistema indicato."""
    def _run(df_raw: pd.DataFrame, patterns: list[str] | None = None) -> pd.DataFrame:
        if df_raw.empty or "system" not in df_raw.columns:
            return pd.DataFrame()
        sys_df = df_raw[df_raw["system"] == system].copy()
        if sys_df.empty:
            return pd.DataFrame()
        return optimize_pattern_combos(
            sys_df,
            lambda d, p: run_backtest_fn(d, p),
            patterns=patterns,
        )

    return _run


def best_combos(df_results: pd.DataFrame) -> dict[str, pd.Series]:
    if df_results.empty:
        return {}
    return {
        "score": df_results.sort_values("score", ascending=False).iloc[0],
        "profit": df_results.sort_values("profit", ascending=False).iloc[0],
        "min_dd": df_results.sort_values("max_dd", ascending=False).iloc[0],
        "calmar": df_results.sort_values("calmar", ascending=False).iloc[0],
    }


def half_pattern_count(n_patterns: int) -> int:
    """Retrocompatibilità — preferire combos_per_size."""
    return max(1, n_patterns // 2) if n_patterns > 1 else 1


def combos_per_size(n_patterns: int) -> dict[int, int]:
    """Quante combinazioni per ogni dimensione (es. 5 file → 5:1, 4:5, 3:10, 2:10, 1:5)."""
    return {k: math.comb(n_patterns, k) for k in range(1, n_patterns + 1)}


def split_combos_by_n(
    combo_df: pd.DataFrame,
    n_patterns: int | None = None,
) -> dict[int, pd.DataFrame]:
    """Raggruppa per n° pattern: tutti, poi n-1, … fino a 1."""
    if combo_df.empty or "n_patterns" not in combo_df.columns:
        return {}

    n = n_patterns if n_patterns is not None else int(combo_df["n_patterns"].max())
    sort_cols = ["score", "profit"]
    groups: dict[int, pd.DataFrame] = {}
    for size in range(n, 0, -1):
        sub = combo_df[combo_df["n_patterns"] == size].sort_values(sort_cols, ascending=False)
        if not sub.empty:
            groups[size] = sub
    return groups


def split_combos_by_size(
    combo_df: pd.DataFrame,
    n_patterns: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Retrocompatibilità — usa split_combos_by_n."""
    groups = split_combos_by_n(combo_df, n_patterns)
    n = n_patterns if n_patterns is not None else (max(groups) if groups else 0)
    empty = pd.DataFrame()
    return {
        "solo": groups.get(1, empty),
        "meta": groups.get(half_pattern_count(n), empty),
        "tutti": groups.get(n, empty),
    }


def combo_display_columns(combo_df: pd.DataFrame, *, stakes_label: str = "") -> pd.DataFrame:
    """Tabella combinazioni formattata per UI."""
    if combo_df.empty:
        return combo_df
    view = combo_df.copy()
    view["winrate"] = (view["winrate"] * 100).round(1)
    if stakes_label:
        view["stakes_used"] = stakes_label
    show_cols = [
        c for c in (
            "combo", "stakes_used", "n_patterns", "profit", "max_dd",
            "score", "calmar", "trades", "winrate",
        )
        if c in view.columns
    ]
    view = view[show_cols]
    col_names = {
        "combo": "Combinazione",
        "stakes_used": "Stake T1/T2/T3/T4",
        "n_patterns": "N° pattern",
        "profit": "Profit (U)",
        "max_dd": "Max DD (U)",
        "score": "Score",
        "calmar": "Calmar",
        "trades": "Trade",
        "winrate": "Winrate %",
    }
    view.columns = [col_names.get(c, c) for c in show_cols]
    return view
