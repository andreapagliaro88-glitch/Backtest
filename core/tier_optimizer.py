"""Ottimizzazione assegnazione pattern T3 / T4 — tutte le strategie."""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from core.backtest_metrics import backtest_metrics
from core.tier_backtest import run_tier_backtest
from core.tier_config import default_tier_rules
from core.tier_engine import TierRules


def list_patterns_for_system(df: pd.DataFrame, system: str) -> list[str]:
    if df.empty or "pattern" not in df.columns:
        return []
    sub = df if "system" not in df.columns else df[df["system"] == system]
    return sorted(sub["pattern"].dropna().unique().tolist())


def _solo_metrics(df_trades: pd.DataFrame) -> dict:
    active = df_trades[df_trades["stake"] > 0] if not df_trades.empty else df_trades
    if active.empty:
        return {"profit": 0.0, "max_dd": 0.0, "trades": 0, "winrate": 0.0, "score": 0.0, "calmar": 0.0}
    return backtest_metrics(active)


def optimize_pattern_tiers(
    df_raw: pd.DataFrame,
    system: str,
    min_trades: int = 10,
    t3_quantile: float = 0.70,
    t4_quantile: float = 0.35,
) -> tuple[pd.DataFrame, TierRules]:
    base = default_tier_rules(system)
    patterns = list_patterns_for_system(df_raw, system)
    if not patterns:
        return pd.DataFrame(), base

    rows = []
    for pat in patterns:
        trades = run_tier_backtest(df_raw, system, (pat,), rules=TierRules(
            stake_t1=base.stake_t1,
            stake_t2=base.stake_t2,
            stake_t3=base.stake_t3,
            stake_t4=base.stake_t4,
            tier3_patterns=[pat],
            tier4_patterns=[],
            min_engines_t1=base.min_engines_t1,
            min_engines_t2=base.min_engines_t2,
        ))
        m = _solo_metrics(trades)
        rows.append({
            "pattern": pat,
            "profit": m["profit"],
            "max_dd": m["max_dd"],
            "score": m["score"],
            "calmar": m["calmar"],
            "trades": m["trades"],
            "winrate": m["winrate"],
        })

    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    if df.empty:
        return df, base

    df["winrate_pct"] = (df["winrate"] * 100).round(1)
    eligible = df[(df["trades"] >= min_trades) & (df["profit"] > 0)].copy()

    if eligible.empty:
        df["suggested_tier"] = "ESCLUSO"
        df["motivo"] = df.apply(
            lambda r: "Pochi trade" if r["trades"] < min_trades else "Profit ≤ 0",
            axis=1,
        )
        return df, base

    q_hi = float(eligible["score"].quantile(t3_quantile))
    q_lo = float(eligible["score"].quantile(t4_quantile))

    t3: list[str] = []
    t4: list[str] = []

    for _, row in df.iterrows():
        pat = row["pattern"]
        if row["trades"] < min_trades or row["profit"] <= 0:
            continue
        if row["score"] >= q_hi:
            t3.append(pat)
        elif row["score"] >= q_lo:
            t4.append(pat)

    df["suggested_tier"] = df["pattern"].apply(
        lambda p: "T3" if p in t3 else ("T4" if p in t4 else "ESCLUSO")
    )
    df["motivo"] = df.apply(
        lambda r: (
            "Top score" if r["suggested_tier"] == "T3"
            else ("Score medio+" if r["suggested_tier"] == "T4"
                  else ("Pochi trade" if r["trades"] < min_trades else "Score basso / loss"))
        ),
        axis=1,
    )

    rules = TierRules(
        stake_t1=base.stake_t1,
        stake_t2=base.stake_t2,
        stake_t3=base.stake_t3,
        stake_t4=base.stake_t4,
        tier3_patterns=t3,
        tier4_patterns=t4,
        min_engines_t1=base.min_engines_t1,
        min_engines_t2=base.min_engines_t2,
    )
    return df, rules


def tier_rules_to_dict(rules: TierRules) -> dict:
    return asdict(rules)


def tier_rules_from_dict(data: dict) -> TierRules:
    return TierRules(**{k: data[k] for k in TierRules.__dataclass_fields__ if k in data})
