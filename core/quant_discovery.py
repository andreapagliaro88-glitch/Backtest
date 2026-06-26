"""Motore quantitativo v2 — discovery autonoma completa."""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import asdict
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy import stats

from compound_config import INITIAL_BANKROLL
from core.compound_pattern_sim import simulate_compound_controlled
from core.live_states import apply_live_state_mask
from core.market_registry import LIVE_MARKET_DEFS, MARKET_DEFS
from core.league_features import (
    available_bool_features,
    available_features,
    build_league_features,
    market_odds_for_frame,
)
from core.league_pattern_discovery import (
    PatternResult,
    Rule,
    _make_result,
    _pattern_id,
    apriori_candidates,
    cluster_candidates,
    diversify_patterns,
    max_drawdown,
    monthly_stability,
    wilson_ci,
)
from core.pattern_search import (
    grid_search_candidates,
    ml_boosted_candidates,
    mutual_info_ranking,
    random_search_candidates,
)

MIN_N_FULL = 200
MIN_N_OOS = 50
TRAIN_RATIO = 0.70
MAX_P_VALUE = 0.05
MIN_MONTHLY_POS_FRAC = 0.55
MAX_TRAIN_TEST_ROI_GAP = 20.0
MIN_OOS_ROI = 0.0
MAX_DD_UNITS = -25.0
WALK_FORWARD_FOLDS = 4
MAX_CANDIDATE_EVAL = 25_000


def _cap_candidates(candidates: list, cap: int = MAX_CANDIDATE_EVAL) -> list:
    if len(candidates) <= cap:
        return candidates
    rng = np.random.default_rng(42)
    idx = rng.choice(len(candidates), size=cap, replace=False)
    return [candidates[i] for i in idx]


def _market_cfg(market_id: str) -> dict:
    return MARKET_DEFS.get(market_id) or LIVE_MARKET_DEFS.get(market_id, {})


def _discovery_markets() -> list[str]:
    return list(MARKET_DEFS.keys()) + list(LIVE_MARKET_DEFS.keys())


def _market_ycols() -> dict[str, str]:
    out = {}
    for mid, cfg in {**MARKET_DEFS, **LIVE_MARKET_DEFS}.items():
        if cfg.get("y"):
            out[mid] = cfg["y"]
    return out


def _train_base_rates(train: pd.DataFrame) -> dict[str, float]:
    rates = {}
    for mid, ycol in _market_ycols().items():
        if ycol in train.columns:
            rates[mid] = float(train[ycol].astype(bool).mean())
    return rates


def _odds_series(df: pd.DataFrame, market_id: str, rates: dict[str, float]) -> pd.Series:
    s, _ = market_odds_for_frame(df, market_id, rates)
    return s


def evaluate_pattern(
    df: pd.DataFrame,
    rules: list[Rule],
    market_id: str,
    train_rates: dict[str, float] | None = None,
    initial_bankroll: float | None = None,
) -> dict[str, Any] | None:
    cfg = _market_cfg(market_id)
    ycol = cfg.get("y")
    if not ycol or ycol not in df.columns:
        return None

    mask = pd.Series(True, index=df.index)
    for r in rules:
        if r.feature not in df.columns:
            return None
        mask &= r.mask(df)

    if market_id in LIVE_MARKET_DEFS:
        mask &= apply_live_state_mask(df, market_id)

    sub = df.loc[mask]
    if len(sub) < 20:
        return None

    odds = _odds_series(sub, market_id, train_rates or {})
    valid = odds.notna() & (odds > 1.01)
    if valid.sum() < 20:
        return None

    sub = sub.loc[valid]
    wins = sub[ycol].astype(bool)
    odds = odds.loc[valid]

    n = len(sub)
    w = int(wins.sum())
    avg_odd = float(odds.mean())
    profits = np.where(wins, odds - 1.0, -1.0)
    profit_u = float(profits.sum())
    roi_pct = 100.0 * profit_u / n
    wr = w / n
    be = 1.0 / avg_odd
    pval = float(stats.binomtest(w, n, be, alternative="greater").pvalue)
    ci_low, ci_high = wilson_ci(w, n)

    sub = sub.sort_values("date")
    wins_ord = wins.loc[sub.index].astype(bool).values
    odds_ord = odds.loc[sub.index].values
    compound = simulate_compound_controlled(
        wins_ord, odds_ord, initial_bankroll=initial_bankroll or INITIAL_BANKROLL
    )

    return {
        "n": n, "wins": w, "winrate": wr, "roi_pct": roi_pct, "profit_u": profit_u,
        "yield_pct": roi_pct, "ci_low": ci_low, "ci_high": ci_high, "p_value": pval,
        "max_dd_u": max_drawdown(profits),
        "monthly_stability": monthly_stability(sub, wins, pd.Series(profits, index=sub.index)),
        "avg_odd": avg_odd,
        "ev_per_trade": float(np.mean(profits)),
        **compound,
    }


def walk_forward_check(
    df: pd.DataFrame,
    rules: list[Rule],
    market_id: str,
    train_rates: dict[str, float],
    n_folds: int = WALK_FORWARD_FOLDS,
) -> bool:
    n = len(df)
    fold_size = n // (n_folds + 1)
    if fold_size < MIN_N_OOS:
        return False
    wins = 0
    for i in range(1, n_folds + 1):
        test = df.iloc[i * fold_size : (i + 1) * fold_size]
        if len(test) < MIN_N_OOS // 2:
            continue
        res = evaluate_pattern(test, rules, market_id, train_rates)
        if res and res["roi_pct"] > 0 and res["p_value"] <= MAX_P_VALUE:
            wins += 1
    return wins >= max(2, n_folds // 2)


def passes_robustness(full: dict, oos: dict | None, wf_ok: bool) -> bool:
    if full["n"] < MIN_N_FULL:
        return False
    if full["p_value"] > MAX_P_VALUE or full["roi_pct"] <= 0:
        return False
    if full["monthly_stability"] < MIN_MONTHLY_POS_FRAC:
        return False
    if full["max_dd_u"] < MAX_DD_UNITS:
        return False
    if oos is None or oos["n"] < MIN_N_OOS:
        return False
    if oos["roi_pct"] < MIN_OOS_ROI or oos["p_value"] > MAX_P_VALUE:
        return False
    if abs(full["roi_pct"] - oos["roi_pct"]) > MAX_TRAIN_TEST_ROI_GAP:
        return False
    if not wf_ok:
        return False
    return True


def live_grid_candidates(train: pd.DataFrame, features: list[str]) -> list[tuple[list[Rule], str, str]]:
    """Cerca edge live: stato live fisso + filtri pre-match aggiuntivi."""
    out: list[tuple[list[Rule], str, str]] = []
    live_feats = [f for f in features if f.startswith("live_") or f in (
        "odd_over25", "pre_over25_pct", "pre_btts_pct", "xg_sum_pre", "ppg_sum"
    )]
    for live_id in LIVE_MARKET_DEFS:
        out.extend(grid_search_candidates(train, live_feats, [live_id], max_combo=3))
        out.extend(random_search_candidates(train, live_feats, [live_id], n_iter=200, max_rules=4))
    return out


def discover_league_patterns(
    path: str,
    min_n: int = MIN_N_FULL,
    initial_bankroll: float | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    global MIN_N_FULL
    MIN_N_FULL = max(min_n, 200)

    def log(msg: str):
        if progress_cb:
            progress_cb(msg)

    log("Caricamento database + minuti gol + stati live...")
    df = build_league_features(path)
    if len(df) < MIN_N_FULL * 2:
        return pd.DataFrame(), {"error": "Campione troppo piccolo (servono almeno 400 partite)", "n_matches": len(df)}

    features = available_features(df, include_live=True, numeric_only=True)
    bool_feats = available_bool_features(df)
    all_search_feats = list(dict.fromkeys(features + bool_feats))
    markets = _discovery_markets()
    ycols = _market_ycols()
    split = int(len(df) * TRAIN_RATIO)
    train, test = df.iloc[:split].copy(), df.iloc[split:].copy()
    train_rates = _train_base_rates(train)

    log("Mutual Information su mercati chiave...")
    mi_feats: list[str] = []
    for m in ["over25", "under25", "btts", "goal_after_70", "over05_ht", "home_win"]:
        if m in ycols:
            mi_feats.extend(mutual_info_ranking(train, features, ycols[m]))
    top_mi = list(dict.fromkeys(mi_feats))[:20]

    log("Generazione candidati (grid adattivo, random, ML, live)...")
    candidates: list[tuple[list[Rule], str, str]] = []
    prematch = [m for m in markets if m in MARKET_DEFS]
    prematch_core = [
        "over25", "under25", "over15", "under15", "btts", "btts_no",
        "home_win", "goal_after_70", "over05_ht", "over05_2h",
    ]
    prematch_core = [m for m in prematch_core if m in prematch]
    timing_mkts = [m for m in prematch if MARKET_DEFS.get(m, {}).get("group") == "Timing"]

    candidates.extend(grid_search_candidates(train, all_search_feats, prematch_core, top_mi, max_combo=3))
    candidates.extend(random_search_candidates(train, all_search_feats, prematch, n_iter=500, max_rules=5))
    candidates.extend(random_search_candidates(train, features, timing_mkts, n_iter=150, max_rules=4))
    candidates.extend(ml_boosted_candidates(train, features, prematch_core[:6], ycols))
    candidates.extend(cluster_candidates(train, features, prematch_core))
    candidates.extend(apriori_candidates(train, features, prematch_core))
    candidates.extend(live_grid_candidates(train, all_search_feats))
    candidates = _cap_candidates(candidates)

    try:
        import xgboost as xgb
        for market_id in ["over25", "over15", "btts", "under25"]:
            ycol = ycols.get(market_id)
            if not ycol:
                continue
            cols = [c for c in features if c in train.columns][:22]
            X = train[cols].fillna(train[cols].median())
            y = train[ycol].astype(int)
            if len(X) < 200:
                continue
            model = xgb.XGBClassifier(n_estimators=80, max_depth=4, min_child_weight=30, random_state=42)
            model.fit(X, y)
            top = [c for c, _ in sorted(zip(cols, model.feature_importances_), key=lambda x: -x[1])[:8]]
            candidates.extend(grid_search_candidates(train, features, [market_id], top, max_combo=3))
    except ImportError:
        pass

    log(f"Validazione {len(candidates)} candidati (min {MIN_N_FULL} partite, walk-forward)...")
    seen: set[str] = set()
    validated: list[PatternResult] = []

    for rules, market_id, method in candidates:
        key = _pattern_id(rules, market_id)
        if key in seen:
            continue
        seen.add(key)

        full_tr = evaluate_pattern(train, rules, market_id, train_rates, initial_bankroll)
        if not full_tr or full_tr["n"] < MIN_N_FULL:
            continue
        oos = evaluate_pattern(test, rules, market_id, train_rates, initial_bankroll)
        wf = walk_forward_check(train, rules, market_id, train_rates)
        if not passes_robustness(full_tr, oos, wf):
            continue
        validated.append(_make_result(rules, market_id, full_tr, oos, [method]))

    best: dict[tuple, PatternResult] = {}
    for p in validated:
        sig = (p.market, tuple(sorted(r.feature for r in p.rules)))
        if sig not in best or p.oos_roi_pct > best[sig].oos_roi_pct:
            best[sig] = p

    final = diversify_patterns(list(best.values()), max_per_market=4, max_total=25)
    rows = [p.to_dict() for p in final]
    result_df = pd.DataFrame(rows) if rows else pd.DataFrame()

    if not result_df.empty:
        from core.edge_analytics import enrich_patterns_dataframe
        log("Edge Score, Monte Carlo, spiegazione statistica...")
        result_df = enrich_patterns_dataframe(result_df, df)

    meta = {
        "n_matches": len(df),
        "n_train": len(train),
        "n_test": len(test),
        "n_features": len(features),
        "n_candidates": len(candidates),
        "n_validated": len(final),
        "markets_analyzed": len(markets),
        "min_sample": MIN_N_FULL,
        "methods": ["grid_adaptive", "random", "mutual_info", "decision_tree", "random_forest",
                    "hist_gradient_boosting", "kmeans", "apriori", "live_states", "walk_forward"],
        "features_used": features,
    }
    log(f"Completato: {len(final)} edge robusti su {len(markets)} mercati.")
    return result_df, meta
