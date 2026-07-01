"""Smoke test: tier → simula stake → ottimizza stake → combinazioni pattern (2 SH)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback

import pandas as pd

from core.pattern_combo_optimizer import count_pattern_combos, combos_per_size, optimize_tier_pattern_combos
from core.sh2_loader import load_sh2_data
from core.tier_config import default_tier_rules
from core.tier_optimizer import list_patterns_for_system, optimize_pattern_tiers, tier_rules_from_dict, tier_rules_to_dict
from core.tier_stake_optimizer import optimize_tier_stakes, simulate_stakes_by_pattern_combos

SYSTEM = "SH2"
CFG_KEY = "sh2"

REQUIRED_COLS = {
    "tier": {"pattern", "suggested_tier", "trades", "profit", "max_dd", "score", "winrate_pct"},
    "sim": {"combo", "n_patterns", "profit", "max_dd", "score", "calmar", "trades", "winrate"},
    "opt": {"profit", "max_dd", "score", "calmar", "trades", "winrate"},
    "combo": {"combo", "n_patterns", "profit", "max_dd", "score", "calmar", "trades", "winrate", "patterns"},
}


def ok(msg: str):
    print(f"  OK  {msg}")


def fail(msg: str):
    print(f"  FAIL  {msg}")
    return False


def check_cols(name: str, df: pd.DataFrame, required: set[str]) -> bool:
    missing = required - set(df.columns)
    if missing:
        fail(f"{name}: colonne mancanti {missing}")
        return False
    if df.empty:
        fail(f"{name}: DataFrame vuoto")
        return False
    ok(f"{name}: {len(df)} righe, colonne OK")
    return True


def check_sorted(name: str, df: pd.DataFrame, col: str = "score") -> bool:
    if col not in df.columns:
        return True
    vals = df[col].tolist()
    if vals != sorted(vals, reverse=True):
        fail(f"{name}: non ordinato per {col} decrescente")
        return False
    ok(f"{name}: ordinato per {col}")
    return True


def check_combo_counts(patterns: list[str], df: pd.DataFrame) -> bool:
    n = len(patterns)
    expected = count_pattern_combos(n)
    if len(df) != expected:
        fail(f"combinazioni: attese {expected}, trovate {len(df)}")
        return False
    per_size = combos_per_size(n)
    for size, exp in per_size.items():
        got = len(df[df["n_patterns"] == size])
        if got != exp:
            fail(f"combinazioni size {size}: attese {exp}, trovate {got}")
            return False
    ok(f"combinazioni: {expected} totali, conteggi per dimensione OK")
    return True


def main() -> int:
    print("=== Check workflow 2 SH ===\n")
    all_ok = True

    df_raw = load_sh2_data()
    if df_raw.empty:
        print("ERRORE: nessun dato in data/sh2/")
        return 1
    ok(f"Dati caricati: {len(df_raw):,} righe")

    patterns = list_patterns_for_system(df_raw, SYSTEM)
    if not patterns:
        print("ERRORE: nessun pattern")
        return 1
    ok(f"Pattern: {len(patterns)} ({', '.join(patterns[:3])}...)")

    rules = default_tier_rules(SYSTEM)
    print("\n1) Ottimizza tier")
    try:
        tier_df, suggested = optimize_pattern_tiers(df_raw, SYSTEM, min_trades=10)
        all_ok &= check_cols("tier", tier_df, REQUIRED_COLS["tier"])
        t3 = suggested.tier3_patterns
        t4 = suggested.tier4_patterns
        ok(f"Proposta tier: T3={len(t3)}, T4={len(t4)}, esclusi={len(patterns)-len(t3)-len(t4)}")
        rules_obj = tier_rules_from_dict(tier_rules_to_dict(suggested))
    except Exception as e:
        print(f"  FAIL tier: {e}")
        traceback.print_exc()
        return 1

    print("\n2) Simula stake")
    try:
        baseline, results, best_per_combo, rules_all = simulate_stakes_by_pattern_combos(
            df_raw, SYSTEM, rules_obj, dd_weight=0.6, max_dd_limit=None,
        )
        all_ok &= check_cols("sim", results, REQUIRED_COLS["sim"])
        all_ok &= check_sorted("sim", results)
        ok(f"Baseline profit={baseline['profit']:.1f}U DD={baseline['max_dd']:.1f}U")
        if results.iloc[0]["score"] < results.iloc[-1]["score"]:
            fail("sim: prima riga non è il miglior score")
            all_ok = False
    except Exception as e:
        print(f"  FAIL simula stake: {e}")
        traceback.print_exc()
        all_ok = False

    print("\n3) Ottimizza stake")
    try:
        baseline_o, opt_results = optimize_tier_stakes(
            df_raw, SYSTEM, rules_obj,
            patterns=tuple(patterns),
            dd_weight=0.6,
            max_dd_limit=None,
            include_random=True,
            random_iterations=200,
        )
        all_ok &= check_cols("opt", opt_results, REQUIRED_COLS["opt"])
        all_ok &= check_sorted("opt", opt_results)
        ok(f"Ottimizzazione: {len(opt_results)} config testate, best score={opt_results.iloc[0]['score']:.1f}")
    except Exception as e:
        print(f"  FAIL ottimizza stake: {e}")
        traceback.print_exc()
        all_ok = False

    print("\n4) Combinazioni pattern")
    try:
        sys_df = df_raw[df_raw["system"] == SYSTEM].copy() if "system" in df_raw.columns else df_raw
        combo_df = optimize_tier_pattern_combos(sys_df, SYSTEM, rules_obj, patterns=patterns)
        all_ok &= check_cols("combo", combo_df, REQUIRED_COLS["combo"])
        all_ok &= check_combo_counts(patterns, combo_df)
        all_ok &= check_sorted("combo", combo_df)
        best = combo_df.iloc[0]
        ok(f"Migliore: {best['combo'][:60]}... score={best['score']:.1f}")
    except Exception as e:
        print(f"  FAIL combinazioni: {e}")
        traceback.print_exc()
        all_ok = False

    print("\n5) Coerenza score (profit + 0.6*DD)")
    try:
        row = combo_df.iloc[0]
        expected = row["profit"] + row["max_dd"] * 0.6
        if abs(row["score"] - expected) > 0.05:
            fail(f"score incoerente: {row['score']:.2f} vs atteso {expected:.2f}")
            all_ok = False
        else:
            ok(f"Formula score OK ({row['score']:.2f})")
    except Exception:
        pass

    print("\n" + ("=== TUTTO OK ===" if all_ok else "=== PROBLEMI RILEVATI ==="))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
