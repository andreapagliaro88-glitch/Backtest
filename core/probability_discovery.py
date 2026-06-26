"""Probability Pattern Engine — discovery autonoma senza quote/ROI."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Callable

import numpy as np
import pandas as pd

from core.league_features import POST_MATCH_COLS, build_league_features, available_features
from core.league_pattern_discovery import apriori_candidates, cluster_candidates
from core.pattern_rules import Rule
from core.pattern_search import (
    grid_search_candidates,
    ml_boosted_candidates,
    mutual_info_ranking,
    random_search_candidates,
)
from core.probability_events import EVENT_DEFS, events_for_discovery
from core.probability_metrics import (
    evaluate_probability_pattern,
    explain_pattern,
    robustness_score,
    serialize_pattern_row,
)
from core.trading_opportunities import suggest_markets

MIN_N_DEFAULT = 200
MIN_N_OOS = 50
MAX_P_VALUE = 0.05
MIN_LIFT = 1.08
MIN_MONTHLY_STAB = 0.52
MAX_PROB_GAP = 0.18

MODE_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "label": "Pattern veloci (~2-4 min)",
        "max_candidates": 4_000,
        "grid_max_out": 600,
        "grid_max_combo": 3,
        "random_iter": 500,
        "random_max_rules": 4,
        "ml_events": 6,
        "mi_events": 6,
        "grid_mi_max_out": 150,
        "cluster_events": 8,
        "apriori_events": 0,
        "use_cluster": False,
        "use_apriori": False,
        "use_ml": True,
        "prelim_cap": 35,
        "final_cap": 15,
        "walk_forward_folds": 2,
        "event_groups": ("Goal", "Primo Tempo", "BTTS", "Timing"),
    },
    "full": {
        "label": "Full pattern (~10-20 min)",
        "max_candidates": 25_000,
        "grid_max_out": 3_500,
        "grid_max_combo": 4,
        "random_iter": 2_500,
        "random_max_rules": 6,
        "ml_events": 24,
        "mi_events": 20,
        "grid_mi_max_out": 400,
        "cluster_events": 20,
        "apriori_events": 15,
        "use_cluster": True,
        "use_apriori": True,
        "use_ml": True,
        "prelim_cap": 120,
        "final_cap": 40,
        "walk_forward_folds": 4,
        "event_groups": (
            "Goal", "Primo Tempo", "Secondo Tempo", "Timing",
            "Ultimi minuti", "BTTS", "Squadra Casa", "Squadra Ospite", "Sequenza gol",
        ),
    },
}


def prematch_features(df: pd.DataFrame) -> list[str]:
    """Solo variabili note pre-kickoff (quote, xG, forma, % storiche)."""
    exclude = POST_MATCH_COLS | {c for c in df.columns if c.startswith("y_") or c.startswith("live_")}
    feats = available_features(df, include_live=False, numeric_only=True)
    return [f for f in feats if f not in exclude]


def _pattern_id(rules: list[Rule], event_id: str) -> str:
    raw = event_id + "|" + "|".join(r.key() for r in rules)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _rules_description(rules: list[Rule]) -> str:
    return " AND ".join(r.describe() for r in rules)


def _base_rates(df: pd.DataFrame) -> dict[str, float]:
    rates = {}
    for eid, cfg in EVENT_DEFS.items():
        ycol = cfg["y"]
        if ycol in df.columns:
            rates[eid] = float(df[ycol].astype(bool).mean())
    return rates


def walk_forward_pass(
    df: pd.DataFrame,
    rules: list[Rule],
    event_id: str,
    ycol: str,
    base_rate: float,
    total_n: int,
    n_folds: int = 3,
    min_n_oos: int = MIN_N_OOS,
) -> bool:
    n = len(df)
    fold = n // (n_folds + 1)
    if fold < min_n_oos // 2:
        return False
    ok = 0
    for i in range(1, n_folds + 1):
        chunk = df.iloc[i * fold : (i + 1) * fold]
        res = evaluate_probability_pattern(chunk, rules, event_id, ycol, base_rate, total_n)
        if res and res["probability"] >= base_rate and res["p_value"] <= MAX_P_VALUE:
            ok += 1
    return ok >= max(1, n_folds // 2)


def passes_filters(full: dict, oos: dict | None, wf: bool, min_n: int) -> bool:
    if full["n"] < min_n:
        return False
    if full["p_value"] > MAX_P_VALUE:
        return False
    if full["lift"] < MIN_LIFT:
        return False
    if full["monthly_stability"] < MIN_MONTHLY_STAB:
        return False
    if not wf:
        return False
    if oos is None or oos["n"] < MIN_N_OOS:
        return False
    if abs(full["probability"] - oos["probability"]) > MAX_PROB_GAP:
        return False
    if oos["probability"] < full["base_rate"]:
        return False
    return True


def _cap(candidates: list, max_n: int) -> list:
    if len(candidates) <= max_n:
        return candidates
    rng = np.random.default_rng(42)
    idx = rng.choice(len(candidates), max_n, replace=False)
    return [candidates[i] for i in idx]


def _file_date_range(df: pd.DataFrame) -> tuple[str, str]:
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return "", ""
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def _monthly_probs(df: pd.DataFrame, rules: list[Rule], ycol: str) -> dict[str, float | None]:
    """Probabilità mensile su tutto il periodo del file (prima → ultima data)."""
    mask = pd.Series(True, index=df.index)
    for r in rules:
        mask &= r.mask(df)
    sub = df.loc[mask]
    if "month" not in df.columns:
        return {}

    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return {}
    month_range = pd.period_range(dates.min(), dates.max(), freq="M")
    out: dict[str, float | None] = {}
    for period in month_range:
        key = str(period)
        chunk = sub[sub["month"] == key]
        out[key] = float(chunk[ycol].astype(bool).mean()) if len(chunk) > 0 else None
    return out


def discover_probability_patterns(
    path: str,
    min_n: int = MIN_N_DEFAULT,
    mode: str = "fast",
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    min_n = max(200, int(min_n))
    cfg = MODE_PRESETS.get(mode, MODE_PRESETS["fast"])

    def log(msg: str):
        if progress_cb:
            progress_cb(msg)

    log(f"Modalità **{cfg['label']}** — caricamento dati...")
    df = build_league_features(path)
    if df.empty or len(df) < min_n * 2:
        return pd.DataFrame(), {"error": "Dati insufficienti", "n_matches": len(df), "mode": mode}

    events = events_for_discovery(df.columns)
    if not events:
        return pd.DataFrame(), {"error": "Nessun evento disponibile", "n_matches": len(df)}

    features = prematch_features(df)
    if len(features) < 5:
        return pd.DataFrame(), {"error": "Feature pre-match insufficienti", "n_matches": len(df)}

    split = int(len(df) * 0.70)
    train, test = df.iloc[:split], df.iloc[split:]
    total_n = len(df)
    date_from, date_to = _file_date_range(df)
    base_rates_train = _base_rates(train)
    base_rates_full = _base_rates(df)
    event_ycols = {eid: EVENT_DEFS[eid]["y"] for eid in events}

    candidates: list[tuple[list[Rule], str, str]] = []

    log(f"Grid search ({len(features)} feature, gruppi: {', '.join(cfg['event_groups'])})...")
    for grp in cfg["event_groups"]:
        evts = [e for e in events if EVENT_DEFS[e]["group"] == grp]
        if evts:
            candidates.extend(
                grid_search_candidates(
                    train, features, evts,
                    max_combo=cfg["grid_max_combo"],
                    max_out=cfg["grid_max_out"],
                )
            )

    log(f"Random search ({cfg['random_iter']} iter, max {cfg['random_max_rules']} regole)...")
    candidates.extend(
        random_search_candidates(
            train, features, events,
            n_iter=cfg["random_iter"],
            max_rules=cfg["random_max_rules"],
        )
    )

    if cfg["use_ml"]:
        log("Mutual Information + ML...")
        core_events = events[: cfg["ml_events"]]
        for eid in events[: cfg["mi_events"]]:
            ycol = event_ycols[eid]
            ranked = mutual_info_ranking(train, features, ycol)
            candidates.extend(
                grid_search_candidates(
                    train, features, [eid], ranked[:8],
                    max_combo=3, max_out=cfg["grid_mi_max_out"],
                )
            )
        candidates.extend(ml_boosted_candidates(train, features, core_events, event_ycols))

    if cfg["use_cluster"]:
        log("Clustering...")
        candidates.extend(cluster_candidates(train, features, events[: cfg["cluster_events"]]))
    if cfg["use_apriori"]:
        log("Apriori...")
        candidates.extend(apriori_candidates(train, features, events[: cfg["apriori_events"]]))

    candidates = _cap(candidates, cfg["max_candidates"])
    log(f"Validazione rapida {len(candidates)} pattern...")

    seen: set[str] = set()
    prelim: list[dict] = []

    for rules, event_id, method in candidates:
        key = _pattern_id(rules, event_id)
        if key in seen:
            continue
        seen.add(key)

        ycol = event_ycols.get(event_id)
        if not ycol:
            continue
        base = base_rates_train.get(event_id, 0.5)

        full = evaluate_probability_pattern(train, rules, event_id, ycol, base, len(train))
        if not full or full["n"] < min_n:
            continue
        if full["p_value"] > MAX_P_VALUE or full["lift"] < MIN_LIFT:
            continue
        if full["monthly_stability"] < MIN_MONTHLY_STAB:
            continue

        oos = evaluate_probability_pattern(test, rules, event_id, ycol, base, total_n)
        if not oos or oos["n"] < MIN_N_OOS:
            continue
        if abs(full["probability"] - oos["probability"]) > MAX_PROB_GAP:
            continue
        if oos["probability"] < base:
            continue

        prelim.append({
            "rules": rules,
            "event_id": event_id,
            "method": method,
            "full": full,
            "oos": oos,
            "key": key,
            "base": base,
            "ycol": ycol,
        })

    prelim.sort(key=lambda x: (-x["full"]["lift"], -x["full"]["probability"], -x["full"]["n"]))
    prelim = prelim[: cfg["prelim_cap"]]
    log(f"Walk-forward ({cfg['walk_forward_folds']} fold) su {len(prelim)} semifinalisti...")

    validated: list[dict] = []
    for item in prelim:
        rules = item["rules"]
        event_id = item["event_id"]
        full = item["full"]
        oos = item["oos"]
        ycol = item["ycol"]
        base = item["base"]

        wf = walk_forward_pass(
            train, rules, event_id, ycol, base, len(train),
            n_folds=cfg["walk_forward_folds"],
        )
        if not wf:
            continue

        base_full = base_rates_full.get(event_id, base)
        file_stats = evaluate_probability_pattern(
            df, rules, event_id, ycol, base_full, total_n
        )
        if not file_stats or file_stats["n"] < min_n:
            continue
        file_stats["walk_forward_pass"] = wf

        desc = _rules_description(rules)
        evt_label = EVENT_DEFS[event_id]["label"]
        trading = suggest_markets(event_id, file_stats["probability"], file_stats["lift"])

        row = {
            "pattern_id": item["key"],
            "pattern_name": f"{evt_label} | {desc[:60]}",
            "event_id": event_id,
            "event_label": evt_label,
            "event_group": EVENT_DEFS[event_id]["group"],
            "description": desc,
            "rules": [asdict(r) for r in rules],
            "methods": [item["method"]],
            "date_from": date_from,
            "date_to": date_to,
            "train_n": full["n"],
            "train_probability": full["probability"],
            "oos_n": oos["n"],
            "oos_probability": oos["probability"],
            "oos_p_value": oos["p_value"],
            "oos_pass": True,
            "monthly_probs": _monthly_probs(df, rules, ycol),
            "trading_opportunities": trading,
            **file_stats,
        }
        row["robustness_score"] = robustness_score(row)
        row["edge_explanation"] = explain_pattern(row)
        validated.append(row)

    # dedup per evento + feature set
    best: dict[tuple, dict] = {}
    for p in validated:
        sig = (p["event_id"], tuple(sorted(r["feature"] for r in p["rules"])))
        if sig not in best or p["robustness_score"] > best[sig]["robustness_score"]:
            best[sig] = p

    final = sorted(
        best.values(),
        key=lambda x: (
            -x["robustness_score"],
            -x["probability"],
            -x["monthly_stability"],
            -x["n"],
            -x["oos_probability"],
            x["p_value"],
        ),
    )[: cfg["final_cap"]]

    rows = [serialize_pattern_row(p) for p in final]
    result_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not result_df.empty:
        result_df.insert(0, "rank", range(1, len(result_df) + 1))

    meta = {
        "engine": "probability_pattern",
        "mode": mode,
        "mode_label": cfg["label"],
        "n_matches": len(df),
        "date_from": date_from,
        "date_to": date_to,
        "n_train": len(train),
        "n_test": len(test),
        "n_features": len(features),
        "n_events": len(events),
        "n_candidates": len(candidates),
        "n_validated": len(final),
        "min_sample": min_n,
        "methods": [
            "grid_adaptive", "random", "mutual_info", "decision_tree",
            "random_forest", "hist_gradient_boosting", "kmeans", "apriori", "walk_forward",
        ],
    }
    log(f"Completato: {len(final)} pattern robusti su {len(events)} eventi.")
    return result_df, meta
