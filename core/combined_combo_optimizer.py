"""Ottimizzazione combinazioni pattern per strategia Combined (HT + O15 + O25)."""
from __future__ import annotations

import itertools

import pandas as pd

from core.backtest import prepare_grouped
from core.backtest_metrics import backtest_metrics
from core.combined_optimizer import score_metrics
from core.pattern_combo_optimizer import combo_label, enumerate_pattern_combos, list_available_patterns
from core.pattern_loader import filter_by_patterns
from core.strategy_engine import prepare_combined_context, run_combined_metrics


def _metrics_combined(
    df_raw: pd.DataFrame,
    ht_patterns=None,
    o15_patterns=None,
    o25_patterns=None,
) -> dict:
    filtered = filter_by_patterns(df_raw, ht=ht_patterns, o15=o15_patterns, o25=o25_patterns)
    if filtered.empty:
        return backtest_metrics(pd.DataFrame())
    grouped = prepare_grouped(filtered)
    context = prepare_combined_context(grouped, filtered)
    return score_metrics(run_combined_metrics(grouped, filtered, context=context))



def _metrics_row(
    metrics: dict,
    combo: str,
    ht: tuple[str, ...] = (),
    o15: tuple[str, ...] = (),
    o25: tuple[str, ...] = (),
) -> dict:
    row = dict(metrics)
    row["combo"] = combo
    row["ht_patterns"] = ht
    row["o15_patterns"] = o15
    row["o25_patterns"] = o25
    row["n_patterns"] = len(ht) + len(o15) + len(o25)
    return row


def optimize_combined_combos(df_raw: pd.DataFrame, max_full_grid: int = 2500) -> pd.DataFrame:
    systems = {
        "HT": list_available_patterns(df_raw, "HT"),
        "O15": list_available_patterns(df_raw, "O15"),
        "O25": list_available_patterns(df_raw, "O25"),
    }
    combos_map = {s: enumerate_pattern_combos(p) if p else [tuple()] for s, p in systems.items()}
    total = len(combos_map["HT"]) * len(combos_map["O15"]) * len(combos_map["O25"])

    rows: list[dict] = []
    best_per_system: dict[str, tuple[str, ...]] = {}

    if total <= max_full_grid and total > 0:
        for ht, o15, o25 in itertools.product(combos_map["HT"], combos_map["O15"], combos_map["O25"]):
            m = _metrics_combined(df_raw, ht or None, o15 or None, o25 or None)
            label = f"HT[{combo_label(ht)}] · O15[{combo_label(o15)}] · O25[{combo_label(o25)}]"
            rows.append(_metrics_row(m, label, ht, o15, o25))
        return pd.DataFrame(rows).sort_values(["score", "profit"], ascending=[False, False]).reset_index(drop=True)

    for system, combos in combos_map.items():
        if not combos or combos == [tuple()]:
            continue
        best_score = float("-inf")
        best_combo = combos[0]
        for combo in combos:
            ht = combo if system == "HT" else None
            o15 = combo if system == "O15" else None
            o25 = combo if system == "O25" else None
            m = _metrics_combined(df_raw, ht, o15, o25)
            rows.append(_metrics_row(
                m,
                f"{system}: {combo_label(combo)} (altri = tutti)",
                ht or (), o15 or (), o25 or (),
            ))
            if m["score"] > best_score:
                best_score = m["score"]
                best_combo = combo
        best_per_system[system] = best_combo

    if len(best_per_system) == 3:
        ht_b = best_per_system["HT"]
        o15_b = best_per_system["O15"]
        o25_b = best_per_system["O25"]
        m = _metrics_combined(df_raw, ht_b, o15_b, o25_b)
        rows.append(_metrics_row(
            m,
            f"★ Miglior mix: HT[{combo_label(ht_b)}] · O15[{combo_label(o15_b)}] · O25[{combo_label(o25_b)}]",
            ht_b, o15_b, o25_b,
        ))

    if not rows:
        m = _metrics_combined(df_raw)
        rows.append(_metrics_row(m, "Tutti i file"))

    df = pd.DataFrame(rows).drop_duplicates(subset=["combo"])
    return df.sort_values(["score", "profit"], ascending=[False, False]).reset_index(drop=True)


def run_combined_with_patterns(
    df_raw: pd.DataFrame,
    ht_patterns=None,
    o15_patterns=None,
    o25_patterns=None,
) -> pd.DataFrame:
    from core.backtest import prepare_grouped, run_backtest

    filtered = filter_by_patterns(df_raw, ht=ht_patterns, o15=o15_patterns, o25=o25_patterns)
    if filtered.empty:
        return pd.DataFrame()
    grouped = prepare_grouped(filtered)
    return run_backtest(grouped, df_raw=filtered)
