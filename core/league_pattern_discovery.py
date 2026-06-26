"""Motore autonomo di discovery pattern per singolo campionato."""
from __future__ import annotations

import itertools
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans

from compound_config import INITIAL_BANKROLL
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from core.compound_pattern_sim import simulate_compound_controlled
from core.pattern_rules import Rule
from core.market_registry import LIVE_MARKET_DEFS, MARKET_DEFS
from core.league_features import (
    build_league_features,
    available_features,
    market_odds_for_frame,
)

MIN_N_FULL = 80
MIN_N_OOS = 25
TRAIN_RATIO = 0.70
MAX_P_VALUE = 0.05
MIN_MONTHLY_POS_FRAC = 0.55
MAX_TRAIN_TEST_ROI_GAP = 25.0  # punti percentuali
MIN_OOS_ROI = 0.0


@dataclass
class PatternResult:
    pattern_id: str
    description: str
    market: str
    market_label: str
    rules: list[Rule]
    n: int
    winrate: float
    roi_pct: float
    profit_u: float
    ci_low: float
    ci_high: float
    p_value: float
    compound_roi_pct: float
    compound_profit_eur: float
    compound_max_dd_pct: float
    compound_stake_eur: float
    max_dd_u: float
    monthly_stability: float
    oos_n: int
    oos_winrate: float
    oos_roi_pct: float
    oos_pass: bool
    methods: list[str] = field(default_factory=list)
    avg_odd: float = 0.0
    odds_tier: str = "real"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rules"] = [asdict(r) for r in self.rules]
        return d


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return float(max(0, low)), float(min(1, high))


def max_drawdown(profits: np.ndarray) -> float:
    if len(profits) == 0:
        return 0.0
    equity = np.cumsum(profits)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return float(dd.min())


def monthly_stability(df: pd.DataFrame, wins: pd.Series, profits: pd.Series) -> float:
    if "month" not in df.columns or len(df) == 0:
        return 0.0
    tmp = df[["month"]].copy()
    tmp["win"] = wins.astype(int)
    tmp["p"] = profits
    by_m = tmp.groupby("month")["p"].sum()
    if len(by_m) == 0:
        return 0.0
    return float((by_m > 0).mean())


def _market_odds_series(df: pd.DataFrame, market_id: str) -> pd.Series:
    odds, _ = market_odds_for_frame(df, market_id)
    return odds


def _discovery_markets() -> list[str]:
    """Solo mercati con quote bookmaker reali o implicate da Over (no quote flat/stimate)."""
    return [
        mid for mid, cfg in MARKET_DEFS.items()
        if cfg.get("odds_tier") in ("real", "implied")
    ]


def diversify_patterns(
    patterns: list[PatternResult],
    max_per_market: int = 5,
    max_total: int = 30,
) -> list[PatternResult]:
    """Evita che un solo mercato monopolizzi la classifica (es. Under 2.5)."""
    if not patterns:
        return []
    by_market: dict[str, list[PatternResult]] = {}
    for p in patterns:
        by_market.setdefault(p.market, []).append(p)
    for m in by_market:
        by_market[m].sort(key=lambda x: (-x.oos_roi_pct, x.p_value))

    order = sorted(by_market.keys(), key=lambda m: -by_market[m][0].oos_roi_pct)
    idx = {m: 0 for m in order}
    final: list[PatternResult] = []
    while len(final) < max_total:
        added = False
        for m in order:
            if idx[m] >= len(by_market[m]):
                continue
            if sum(1 for x in final if x.market == m) >= max_per_market:
                continue
            final.append(by_market[m][idx[m]])
            idx[m] += 1
            added = True
            if len(final) >= max_total:
                break
        if not added:
            break
    return final


def evaluate_pattern(
    df: pd.DataFrame,
    rules: list[Rule],
    market_id: str,
    odds_series: pd.Series | None = None,
    initial_bankroll: float | None = None,
) -> dict[str, Any] | None:
    if not rules:
        return None
    mask = pd.Series(True, index=df.index)
    for r in rules:
        if r.feature not in df.columns:
            return None
        mask &= r.mask(df)
    sub = df.loc[mask]
    if len(sub) < 10:
        return None

    ycol = MARKET_DEFS[market_id]["y"]
    if ycol not in sub.columns:
        return None

    wins = sub[ycol].astype(bool)
    odds = odds_series.loc[sub.index] if odds_series is not None else _market_odds_series(sub, market_id)
    valid = odds.notna() & (odds > 1.01)
    if valid.sum() < 10:
        return None

    sub = sub.loc[valid]
    wins = wins.loc[valid]
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
        wins_ord,
        odds_ord,
        initial_bankroll=initial_bankroll or INITIAL_BANKROLL,
    )

    return {
        "n": n,
        "wins": w,
        "winrate": wr,
        "roi_pct": roi_pct,
        "profit_u": profit_u,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": pval,
        "max_dd_u": max_drawdown(profits),
        "monthly_stability": monthly_stability(sub, wins, pd.Series(profits, index=sub.index)),
        "avg_odd": avg_odd,
        "profits": profits,
        "sub_idx": sub.index,
        **compound,
    }


def _pattern_id(rules: list[Rule], market_id: str) -> str:
    raw = market_id + "|" + "|".join(r.key() for r in rules)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _market_cfg(market_id: str) -> dict:
    return MARKET_DEFS.get(market_id) or LIVE_MARKET_DEFS.get(market_id, {})


def _make_result(
    rules: list[Rule],
    market_id: str,
    full: dict,
    oos: dict | None,
    methods: list[str],
) -> PatternResult:
    desc = " AND ".join(r.describe() for r in rules)
    oos_pass = False
    oos_n = oos_win = oos_roi = 0.0
    if oos and oos["n"] >= MIN_N_OOS:
        oos_n = oos["n"]
        oos_win = oos["winrate"]
        oos_roi = oos["roi_pct"]
        gap = abs(full["roi_pct"] - oos_roi)
        oos_pass = (
            oos_roi >= MIN_OOS_ROI
            and oos["p_value"] <= MAX_P_VALUE
            and gap <= MAX_TRAIN_TEST_ROI_GAP
        )

    return PatternResult(
        pattern_id=_pattern_id(rules, market_id),
        description=desc,
        market=market_id,
        market_label=(_market_cfg(market_id).get("label", market_id)),
        rules=rules,
        n=full["n"],
        winrate=full["winrate"],
        roi_pct=full["roi_pct"],
        profit_u=full["profit_u"],
        ci_low=full["ci_low"],
        ci_high=full["ci_high"],
        p_value=full["p_value"],
        compound_roi_pct=full["compound_roi_pct"],
        compound_profit_eur=full["compound_profit_eur"],
        compound_max_dd_pct=full["compound_max_dd_pct"],
        compound_stake_eur=full["compound_stake_eur"],
        max_dd_u=full["max_dd_u"],
        monthly_stability=full["monthly_stability"],
        oos_n=int(oos_n),
        oos_winrate=float(oos_win),
        oos_roi_pct=float(oos_roi),
        oos_pass=oos_pass,
        methods=methods,
        avg_odd=full["avg_odd"],
        odds_tier=_market_cfg(market_id).get("odds_tier", "real"),
    )


def _quantile_bins(series: pd.Series, q: int = 4) -> list[tuple[float, float]]:
    s = series.dropna()
    if len(s) < 20:
        return []
    qs = np.linspace(0, 1, q + 1)
    edges = s.quantile(qs).values
    edges = np.unique(edges)
    bins = []
    for i in range(len(edges) - 1):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if hi > lo:
            bins.append((lo, hi))
    return bins


def _mid_split(series: pd.Series) -> list[Rule]:
    s = series.dropna()
    if len(s) < 20:
        return []
    med = float(s.median())
    return [
        Rule(feature=series.name, op="gt", val=med),
        Rule(feature=series.name, op="lt", val=med),
    ]


def grid_search_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
    top_features: list[str] | None = None,
) -> list[tuple[list[Rule], str, str]]:
    out: list[tuple[list[Rule], str, str]] = []
    feats = top_features or features[:12]

    for market_id in markets:
        for feat in feats:
            if feat not in train.columns:
                continue
            for lo, hi in _quantile_bins(train[feat], 4):
                out.append(([Rule(feat, "between", lo=lo, hi=hi)], market_id, "grid"))
            for r in _mid_split(train[feat].rename(feat)):
                out.append(([r], market_id, "grid"))

        for f1, f2 in itertools.combinations(feats[:8], 2):
            b1 = _quantile_bins(train[f1], 3)
            b2 = _quantile_bins(train[f2], 3)
            for (lo1, hi1), (lo2, hi2) in itertools.product(b1[:2], b2[:2]):
                rules = [
                    Rule(f1, "between", lo=lo1, hi=hi1),
                    Rule(f2, "between", lo=lo2, hi=hi2),
                ]
                out.append((rules, market_id, "grid_pair"))
    return out


def random_search_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
    n_iter: int = 400,
    rng: np.random.Generator | None = None,
) -> list[tuple[list[Rule], str, str]]:
    rng = rng or np.random.default_rng(42)
    out: list[tuple[list[Rule], str, str]] = []
    for _ in range(n_iter):
        market_id = rng.choice(markets)
        k = int(rng.integers(1, 4))
        chosen = rng.choice(features, size=min(k, len(features)), replace=False)
        rules: list[Rule] = []
        for feat in chosen:
            s = train[feat].dropna()
            if len(s) < 20:
                continue
            if rng.random() < 0.6:
                lo, hi = float(s.quantile(rng.uniform(0.05, 0.45))), float(
                    s.quantile(rng.uniform(0.55, 0.95)
                ))
                if hi > lo:
                    rules.append(Rule(feat, "between", lo=lo, hi=hi))
            else:
                val = float(s.quantile(rng.uniform(0.2, 0.8)))
                op = "gt" if rng.random() < 0.5 else "lt"
                rules.append(Rule(feat, op, val=val))
        if rules:
            out.append((rules, market_id, "random"))
    return out


def mutual_info_ranking(
    train: pd.DataFrame,
    features: list[str],
    market_id: str,
) -> list[str]:
    ycol = MARKET_DEFS[market_id]["y"]
    cols = [c for c in features if c in train.columns]
    X = train[cols].fillna(train[cols].median())
    y = train[ycol].astype(int)
    if len(X) < 50:
        return cols
    mi = mutual_info_classif(X, y, random_state=42)
    ranked = sorted(zip(cols, mi), key=lambda x: -x[1])
    return [c for c, _ in ranked]


def tree_rule_candidates(
    train: pd.DataFrame,
    features: list[str],
    market_id: str,
    max_depth: int = 3,
) -> list[tuple[list[Rule], str, str]]:
    ycol = MARKET_DEFS[market_id]["y"]
    cols = [c for c in features if c in train.columns][:20]
    X = train[cols].fillna(train[cols].median())
    y = train[ycol].astype(int)
    if len(X) < 80 or y.nunique() < 2:
        return []

    clf = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=25, random_state=42)
    clf.fit(X, y)

    out: list[tuple[list[Rule], str, str]] = []
    tree = clf.tree_
    feat_names = cols

    def recurse(node: int, rules: list[Rule]):
        if tree.feature[node] == -2:
            n = tree.n_node_samples[node]
            if n >= MIN_N_FULL and tree.value[node][0][1] / n >= 0.55:
                out.append((list(rules), market_id, "decision_tree"))
            return
        f = feat_names[tree.feature[node]]
        thr = float(tree.threshold[node])
        recurse(tree.children_left[node], rules + [Rule(f, "lt", val=thr)])
        recurse(tree.children_right[node], rules + [Rule(f, "gt", val=thr)])

    recurse(0, [])
    return out[:30]


def rf_importance_features(
    train: pd.DataFrame,
    features: list[str],
    market_id: str,
    top_k: int = 10,
) -> list[str]:
    ycol = MARKET_DEFS[market_id]["y"]
    cols = [c for c in features if c in train.columns][:25]
    X = train[cols].fillna(train[cols].median())
    y = train[ycol].astype(int)
    if len(X) < 80:
        return cols[:top_k]
    rf = RandomForestClassifier(
        n_estimators=80, max_depth=5, min_samples_leaf=20, random_state=42, n_jobs=-1
    )
    rf.fit(X, y)
    imp = sorted(zip(cols, rf.feature_importances_), key=lambda x: -x[1])
    return [c for c, _ in imp[:top_k]]


def cluster_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
) -> list[tuple[list[Rule], str, str]]:
    cols = [c for c in features if c in train.columns][:15]
    X = train[cols].dropna()
    if len(X) < 100:
        return []
    idx = X.index
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X.fillna(X.median()))

    out: list[tuple[list[Rule], str, str]] = []
    for k in (3, 4, 5):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(Xs)
        centers = km.cluster_centers_
        for ci in range(k):
            cluster_idx = idx[labels == ci]
            if len(cluster_idx) < MIN_N_FULL:
                continue
            # approssima cluster con iper-box su feature più distanti dal centro globale
            sub = train.loc[cluster_idx, cols]
            global_med = train.loc[idx, cols].median()
            diffs = (sub.median() - global_med).abs().sort_values(ascending=False)
            rules: list[Rule] = []
            for feat in diffs.head(3).index:
                lo, hi = float(sub[feat].quantile(0.15)), float(sub[feat].quantile(0.85))
                if hi > lo:
                    rules.append(Rule(feat, "between", lo=lo, hi=hi))
            if not rules:
                continue
            for market_id in markets:
                out.append((rules, market_id, f"cluster_k{k}"))
    return out


def apriori_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
    min_support: float = 0.08,
) -> list[tuple[list[Rule], str, str]]:
    """Frequent itemsets su feature discretizzate (Apriori semplificato)."""
    cols = features[:12]
    discretized: dict[str, pd.Series] = {}
    for c in cols:
        if c not in train.columns:
            continue
        s = train[c]
        q1, q2 = s.quantile(0.33), s.quantile(0.66)
        discretized[c] = pd.cut(
            s, bins=[-np.inf, q1, q2, np.inf], labels=["L", "M", "H"]
        )

    items = []
    for c, ser in discretized.items():
        for lvl in ["L", "M", "H"]:
            col_name = f"{c}_{lvl}"
            items.append((col_name, ser == lvl))

    if len(items) < 3:
        return []

    n = len(train)
    item_df = pd.DataFrame({name: mask.astype(int) for name, mask in items}, index=train.index)
    freq_items = [c for c in item_df.columns if item_df[c].mean() >= min_support]

    out: list[tuple[list[Rule], str, str]] = []
    for size in (2, 3):
        for combo in itertools.combinations(freq_items, size):
            mask = item_df[list(combo)].all(axis=1)
            if mask.mean() < min_support:
                continue
            rules: list[Rule] = []
            for item in combo:
                feat, lvl = item.rsplit("_", 1)
                s = train[feat]
                q1, q2 = s.quantile(0.33), s.quantile(0.66)
                if lvl == "L":
                    rules.append(Rule(feat, "lt", val=float(q1)))
                elif lvl == "M":
                    rules.append(Rule(feat, "between", lo=float(q1), hi=float(q2)))
                else:
                    rules.append(Rule(feat, "gt", val=float(q2)))
            for market_id in markets:
                out.append((rules, market_id, "apriori"))
    return out[:80]


def passes_robustness(full: dict, oos: dict | None) -> bool:
    if full["n"] < MIN_N_FULL:
        return False
    if full["p_value"] > MAX_P_VALUE:
        return False
    if full["roi_pct"] <= 0:
        return False
    if full["monthly_stability"] < MIN_MONTHLY_POS_FRAC:
        return False
    if oos is None or oos["n"] < MIN_N_OOS:
        return False
    if not (oos["roi_pct"] >= MIN_OOS_ROI and oos["p_value"] <= MAX_P_VALUE):
        return False
    if abs(full["roi_pct"] - oos["roi_pct"]) > MAX_TRAIN_TEST_ROI_GAP:
        return False
    return True


