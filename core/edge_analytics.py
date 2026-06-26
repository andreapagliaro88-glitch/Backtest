"""Arricchimento pattern con serie trade e metriche avanzate."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from core.edge_scoring import analyze_trade_series, serialize_analytics
from core.live_states import apply_live_state_mask
from core.market_registry import LIVE_MARKET_DEFS, MARKET_DEFS
from core.league_features import db_odd_column_for_market, db_odds_series, market_odds_for_frame
from core.pattern_rules import Rule


def _pattern_mask(df: pd.DataFrame, rules: list[Rule], market_id: str) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for r in rules:
        if r.feature not in df.columns:
            return pd.Series(False, index=df.index)
        mask &= r.mask(df)
    if market_id in LIVE_MARKET_DEFS:
        mask &= apply_live_state_mask(df, market_id)
    return mask


def summarize_db_odds(
    df: pd.DataFrame,
    rules: list[Rule],
    market_id: str,
    n_examples: int = 5,
) -> dict[str, Any]:
    """Statistiche quota da colonna CSV reale + esempi partite."""
    col = db_odd_column_for_market(market_id)
    mask = _pattern_mask(df, rules, market_id)
    sub = df.loc[mask]

    empty = {
        "odds_db_column": col or "",
        "odds_db_available": False,
        "odds_db_mean": None,
        "odds_db_min": None,
        "odds_db_max": None,
        "odds_db_coverage_pct": 0.0,
        "odds_examples": [],
    }
    if not col or sub.empty:
        return empty

    raw = db_odds_series(sub, market_id)
    valid = raw.notna()
    coverage = 100.0 * float(valid.sum()) / len(sub) if len(sub) else 0.0
    if valid.sum() == 0:
        empty["odds_db_column"] = col
        empty["odds_db_coverage_pct"] = coverage
        return empty

    sub = sub.loc[valid].sort_values("date")
    odds = raw.loc[sub.index]

    examples: list[dict[str, Any]] = []
    picks = np.linspace(0, len(sub) - 1, min(n_examples, len(sub)), dtype=int)
    for i in picks:
        row = sub.iloc[int(i)]
        dt = row["date"]
        if hasattr(dt, "strftime"):
            dt = dt.strftime("%Y-%m-%d")
        examples.append({
            "data": str(dt),
            "partita": f"{row.get('home_team_name', '?')} vs {row.get('away_team_name', '?')}",
            "quota": round(float(odds.iloc[int(i)]), 2),
        })

    return {
        "odds_db_column": col,
        "odds_db_available": True,
        "odds_db_mean": round(float(odds.mean()), 3),
        "odds_db_min": round(float(odds.min()), 3),
        "odds_db_max": round(float(odds.max()), 3),
        "odds_db_coverage_pct": round(coverage, 1),
        "odds_examples": examples,
    }


def _market_odds_series(df: pd.DataFrame, market_id: str) -> pd.Series:
    odds, _ = market_odds_for_frame(df, market_id)
    return odds


def _season_label(dt) -> str:
    if pd.isna(dt):
        return "unknown"
    y = dt.year
    return f"{y}-{y + 1}" if dt.month >= 7 else f"{y - 1}-{y}"


def build_pattern_trades(
    df: pd.DataFrame,
    rules: list[Rule],
    market_id: str,
    train_rates: dict[str, float] | None = None,
) -> pd.DataFrame:
    mask = _pattern_mask(df, rules, market_id)
    if not mask.any():
        return pd.DataFrame()

    cfg = MARKET_DEFS.get(market_id) or LIVE_MARKET_DEFS.get(market_id, {})
    ycol = cfg.get("y")
    if not ycol:
        return pd.DataFrame()

    sub = df.loc[mask].copy()
    odds, _ = market_odds_for_frame(sub, market_id, train_rates)
    valid = odds.notna() & (odds > 1.01)
    sub = sub.loc[valid].sort_values("date")

    if sub.empty:
        return pd.DataFrame()

    wins = sub[ycol].astype(bool)
    odds = odds.loc[sub.index]
    sub["win"] = wins
    sub["odd"] = odds
    sub["profit_u"] = pd.Series(np.where(wins, odds - 1.0, -1.0), index=wins.index)
    sub["is_home_fav"] = sub["odd_1"] <= sub["odd_2"] if "odd_1" in sub.columns else True
    if "month" not in sub.columns:
        sub["month"] = sub["date"].dt.to_period("M").astype(str)
    sub["season"] = sub["date"].apply(_season_label)
    return sub[["date", "month", "season", "win", "odd", "profit_u", "is_home_fav"]]


def rules_from_row(row: dict | pd.Series) -> list[Rule]:
    rules_raw = row["rules"]
    if isinstance(rules_raw, str):
        rules_raw = json.loads(rules_raw)
    return [Rule(**r) for r in rules_raw]


def enrich_patterns_dataframe(
    patterns_df: pd.DataFrame,
    league_df: pd.DataFrame,
) -> pd.DataFrame:
    if patterns_df.empty:
        return patterns_df

    rows: list[dict[str, Any]] = []
    for _, pat in patterns_df.iterrows():
        d = pat.to_dict()
        rules = rules_from_row(pat)
        trades = build_pattern_trades(league_df, rules, pat["market"])
        if trades.empty:
            d.update({
                "robustness_score": 0.0,
                "edge_score": 0.0,
                "sharpe_ratio": 0.0,
                "profit_factor": 0.0,
                "expectancy_u": 0.0,
                "kelly_pct": 0.0,
            })
            d.update(summarize_db_odds(league_df, rules, pat["market"]))
            rows.append(serialize_analytics(d))
            continue

        analytics = analyze_trade_series(trades, d)
        d.update(analytics)
        d.update(summarize_db_odds(league_df, rules, pat["market"]))
        d["edge_name"] = f"{pat.get('market_label', '')} | {pat.get('description', '')[:70]}"
        rows.append(serialize_analytics(d))

    out = pd.DataFrame(rows)
    out = out.sort_values("edge_score", ascending=False).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out
