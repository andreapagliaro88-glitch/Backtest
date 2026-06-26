"""Generazione candidati pattern: grid, random, ML."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.tree import DecisionTreeClassifier

from core.pattern_rules import Rule

MIN_BIN_WIDTH_FRAC = 0.04


def adaptive_bins(series: pd.Series, max_bins: int = 12) -> list[tuple[float, float]]:
    if series.dtype == bool or series.nunique(dropna=True) <= 2:
        return []
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 40:
        return []
    edges = np.unique(s.quantile(np.linspace(0, 1, max_bins + 1)).values)
    bins: list[tuple[float, float]] = []
    span = float(s.max() - s.min()) or 1.0
    min_w = span * MIN_BIN_WIDTH_FRAC
    for i in range(len(edges) - 1):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if hi - lo >= min_w * 0.5:
            bins.append((lo, hi))
    return bins


def mutual_info_ranking(train: pd.DataFrame, features: list[str], ycol: str) -> list[str]:
    cols = [c for c in features if c in train.columns]
    X = train[cols].fillna(train[cols].median())
    y = train[ycol].astype(int)
    if len(X) < 80 or y.nunique() < 2:
        return cols
    mi = mutual_info_classif(X, y, random_state=42)
    return [c for c, _ in sorted(zip(cols, mi), key=lambda x: -x[1])]


def grid_search_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
    top_features: list[str] | None = None,
    max_combo: int = 4,
    max_out: int = 8_000,
) -> list[tuple[list[Rule], str, str]]:
    out: list[tuple[list[Rule], str, str]] = []
    feats = top_features or features[:15]

    def _add(item):
        out.append(item)
        return len(out) >= max_out

    for market_id in markets:
        for feat in feats:
            if feat not in train.columns:
                continue
            if train[feat].dtype == bool or train[feat].nunique(dropna=True) <= 2:
                if _add(([Rule(feat, "eq", val=1)], market_id, "grid_bool")):
                    return out
                continue
            for lo, hi in adaptive_bins(train[feat], 10):
                if _add(([Rule(feat, "between", lo=lo, hi=hi)], market_id, "grid")):
                    return out
            med = float(train[feat].median())
            if _add(([Rule(feat, "gt", val=med)], market_id, "grid_split")):
                return out
            if _add(([Rule(feat, "lt", val=med)], market_id, "grid_split")):
                return out

        for size in range(2, min(max_combo, len(feats)) + 1):
            for combo in itertools.combinations(feats[:8], size):
                bin_lists = []
                for f in combo:
                    b = adaptive_bins(train[f], 3)[:2]
                    if not b:
                        break
                    bin_lists.append([(f, lo, hi) for lo, hi in b])
                else:
                    for picks in itertools.product(*bin_lists):
                        rules = [Rule(f, "between", lo=lo, hi=hi) for f, lo, hi in picks]
                        if _add((rules, market_id, f"grid_{size}")):
                            return out
    return out


def random_search_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
    n_iter: int = 1200,
    max_rules: int = 5,
    rng: np.random.Generator | None = None,
) -> list[tuple[list[Rule], str, str]]:
    rng = rng or np.random.default_rng(42)
    out: list[tuple[list[Rule], str, str]] = []
    for _ in range(n_iter):
        market_id = str(rng.choice(markets))
        k = int(rng.integers(1, max_rules + 1))
        chosen = rng.choice(features, size=min(k, len(features)), replace=False)
        rules: list[Rule] = []
        for feat in chosen:
            s = train[feat].dropna()
            if len(s) < 30:
                continue
            if s.dtype == bool or s.nunique() <= 2:
                rules.append(Rule(feat, "eq", val=1))
                continue
            qlo = float(s.quantile(rng.uniform(0.02, 0.45)))
            qhi = float(s.quantile(rng.uniform(0.55, 0.98)))
            if qhi > qlo:
                rules.append(Rule(feat, "between", lo=qlo, hi=qhi))
            else:
                rules.append(
                    Rule(feat, "gt" if rng.random() < 0.5 else "lt", val=float(s.quantile(rng.uniform(0.2, 0.8))))
                )
        if rules:
            out.append((rules, market_id, "random"))
    return out


def tree_rule_candidates(
    train: pd.DataFrame,
    features: list[str],
    market_id: str,
    ycol: str,
    max_depth: int = 4,
    min_leaf: int = 40,
) -> list[tuple[list[Rule], str, str]]:
    cols = [c for c in features if c in train.columns][:25]
    X = train[cols].fillna(train[cols].median())
    y = train[ycol].astype(int)
    if len(X) < 120 or y.nunique() < 2:
        return []

    clf = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=min_leaf, random_state=42)
    clf.fit(X, y)
    out: list[tuple[list[Rule], str, str]] = []
    tree = clf.tree_
    feat_names = cols

    def recurse(node: int, rules: list[Rule]):
        if tree.feature[node] == -2:
            n = tree.n_node_samples[node]
            if n >= min_leaf * 2:
                wr = tree.value[node][0][1] / n if n else 0
                if wr >= 0.52:
                    out.append((list(rules), market_id, "decision_tree"))
            return
        f = feat_names[tree.feature[node]]
        thr = float(tree.threshold[node])
        recurse(tree.children_left[node], rules + [Rule(f, "lt", val=thr)])
        recurse(tree.children_right[node], rules + [Rule(f, "gt", val=thr)])

    recurse(0, [])
    return out[:40]


def ml_boosted_candidates(
    train: pd.DataFrame,
    features: list[str],
    markets: list[str],
    market_ycols: dict[str, str],
) -> list[tuple[list[Rule], str, str]]:
    out: list[tuple[list[Rule], str, str]] = []
    for market_id in markets:
        ycol = market_ycols.get(market_id)
        if not ycol or ycol not in train.columns:
            continue
        cols = [c for c in features if c in train.columns][:22]
        X = train[cols].fillna(train[cols].median())
        y = train[ycol].astype(int)
        if len(X) < 120:
            continue

        rf = RandomForestClassifier(
            n_estimators=100, max_depth=6, min_samples_leaf=30, random_state=42, n_jobs=-1
        )
        rf.fit(X, y)
        top = [c for c, _ in sorted(zip(cols, rf.feature_importances_), key=lambda x: -x[1])[:8]]
        out.extend(grid_search_candidates(train, features, [market_id], top, max_combo=3))
        out.extend(tree_rule_candidates(train, features, market_id, ycol))

        try:
            hgb = HistGradientBoostingClassifier(max_depth=4, min_samples_leaf=30, random_state=42)
            hgb.fit(X, y)
            pred = hgb.predict_proba(X)[:, 1]
            corrs = X.corrwith(pd.Series(pred, index=X.index)).abs().sort_values(ascending=False)
            hgb_top = list(corrs.head(8).index)
            out.extend(grid_search_candidates(train, features, [market_id], hgb_top, max_combo=3))
        except Exception:
            pass

    return out
