"""Metriche statistiche per Probability Pattern Engine."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from core.league_pattern_discovery import monthly_stability, wilson_ci


def apply_rules_mask(df: pd.DataFrame, rules) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for r in rules:
        if r.feature not in df.columns:
            return pd.Series(False, index=df.index)
        mask &= r.mask(df)
    return mask


def association_metrics(
    n: int,
    k: int,
    total_n: int,
    base_rate: float,
) -> dict[str, float]:
    p = k / n if n else 0.0
    support = n / total_n if total_n else 0.0
    confidence = p
    lift = p / base_rate if base_rate > 0 else 0.0
    leverage = p - base_rate
    conviction = (1.0 - base_rate) / (1.0 - p) if p < 0.999 else float("inf")
    expected_freq = base_rate * n

    base_k = base_rate * total_n
    odds_ratio = 1.0
    if k > 0 and (n - k) > 0 and base_k > 0 and (total_n - base_k) > 0:
        odds_ratio = (k / (n - k)) / (base_k / (total_n - base_k))

    return {
        "probability": p,
        "support": support,
        "confidence": confidence,
        "lift": lift,
        "leverage": leverage,
        "conviction": conviction,
        "expected_frequency": expected_freq,
        "odds_ratio": odds_ratio,
    }


def pattern_p_value(k: int, n: int, base_rate: float) -> float:
    if n == 0:
        return 1.0
    return float(stats.binomtest(k, n, base_rate, alternative="greater").pvalue)


def seasonal_stability(df: pd.DataFrame, y: pd.Series) -> float:
    if "season" not in df.columns or len(df) == 0:
        return 0.0
    tmp = df[["season"]].copy()
    tmp["y"] = y.astype(int)
    by_s = tmp.groupby("season")["y"].mean()
    if len(by_s) < 2:
        return 1.0 if len(by_s) == 1 else 0.0
    return float(1.0 - by_s.std())


def monte_carlo_bootstrap(y: np.ndarray, n_sim: int = 500) -> dict[str, float]:
    if len(y) < 10:
        return {"mc_median_prob": 0.0, "mc_p5_prob": 0.0, "mc_p95_prob": 0.0, "mc_prob_above_base": 0.0}
    rng = np.random.default_rng(42)
    probs = []
    base = float(y.mean())
    for _ in range(n_sim):
        sample = rng.choice(y, size=len(y), replace=True)
        probs.append(float(sample.mean()))
    probs = np.array(probs)
    return {
        "mc_median_prob": float(np.median(probs)),
        "mc_p5_prob": float(np.percentile(probs, 5)),
        "mc_p95_prob": float(np.percentile(probs, 95)),
        "mc_prob_above_base": float((probs > base).mean()),
    }


def robustness_score(m: dict[str, Any]) -> float:
    prob = min(1.0, m.get("probability", 0) / 0.85)
    lift = min(1.0, max(0, (m.get("lift", 1) - 1) / 0.5))
    sig = min(1.0, max(0, 1.0 - m.get("p_value", 1)))
    oos_gap = abs(m.get("probability", 0) - m.get("oos_probability", 0))
    oos = min(1.0, max(0, 1.0 - oos_gap / 0.15))
    stab_m = m.get("monthly_stability", 0)
    stab_s = m.get("seasonal_stability", 0)
    stab = 0.6 * stab_m + 0.4 * stab_s
    n_score = min(1.0, m.get("n", 0) / 400)
    wf = 1.0 if m.get("walk_forward_pass") else 0.0
    raw = 0.22 * prob + 0.18 * lift + 0.18 * sig + 0.15 * oos + 0.12 * stab + 0.10 * n_score + 0.05 * wf
    return round(100.0 * raw, 1)


def explain_pattern(m: dict[str, Any]) -> str:
    lift = m.get("lift", 1)
    p = m.get("probability", 0) * 100
    base = m.get("base_rate", 0) * 100
    n = m.get("n", 0)
    event = m.get("event_label", "l'evento")
    desc = m.get("description", "")
    parts = [
        f"Su **{n}** partite che soddisfano `{desc}`, **{event}** si verifica nel **{p:.1f}%** dei casi "
        f"(baseline campionato: {base:.1f}%).",
        f"**Lift {lift:.2f}**: la probabilità è {lift:.1f}× la media del campionato.",
    ]
    if m.get("p_value", 1) < 0.05:
        parts.append(f"Il risultato è **statisticamente significativo** (p={m['p_value']:.4f}).")
    if m.get("oos_probability"):
        parts.append(
            f"Out-of-sample: probabilità **{m['oos_probability']*100:.1f}%** "
            f"su {m.get('oos_n', 0)} partite."
        )
    if m.get("monthly_stability", 0) >= 0.6:
        parts.append("Stabilità mensile elevata: il pattern regge nel tempo.")
    return " ".join(parts)


def evaluate_probability_pattern(
    df: pd.DataFrame,
    rules,
    event_id: str,
    ycol: str,
    base_rate: float,
    total_n: int,
) -> dict[str, Any] | None:
    mask = apply_rules_mask(df, rules)
    sub = df.loc[mask]
    if len(sub) < 20:
        return None

    y = sub[ycol].astype(bool)
    n = len(sub)
    k = int(y.sum())
    if k == 0 and base_rate < 0.01:
        return None

    ci_low, ci_high = wilson_ci(k, n)
    assoc = association_metrics(n, k, total_n, base_rate)
    pval = pattern_p_value(k, n, base_rate)
    profits = y.astype(int).values  # for monthly stability helper
    mstab = monthly_stability(sub, y, pd.Series(profits, index=sub.index))
    sstab = seasonal_stability(sub, y)
    mc = monte_carlo_bootstrap(y.astype(int).values)

    return {
        "n": n,
        "hits": k,
        "probability": assoc["probability"],
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": pval,
        "base_rate": base_rate,
        "monthly_stability": mstab,
        "seasonal_stability": sstab,
        "walk_forward_pass": False,
        **assoc,
        **mc,
    }


def serialize_pattern_row(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    for key in ("trading_opportunities", "monthly_probs"):
        if key in out and not isinstance(out[key], str):
            out[key] = json.dumps(out[key], ensure_ascii=False, default=str)
    return out
