"""Ottimizzazione combinazioni di pattern (file Excel) per qualsiasi strategia."""
from __future__ import annotations

import itertools
from typing import Callable, Iterable

import pandas as pd

from core.backtest_metrics import backtest_metrics


def combo_label(patterns: tuple[str, ...]) -> str:
    return " + ".join(patterns)


def enumerate_pattern_combos(patterns: Iterable[str]) -> list[tuple[str, ...]]:
    pats = list(patterns)
    combos = []
    for size in range(1, len(pats) + 1):
        combos.extend(itertools.combinations(pats, size))
    return combos


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
    Testa tutte le combinazioni di pattern.
    Per SH: le partite duplicate tra pattern vengono unite (1 trade per match).
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
