"""Feature engineering completo per quantitative edge discovery."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.footystats_analyzer import load_footystats_csv
from core.goal_timings import attach_timing_outcomes
from core.market_registry import LIVE_MARKET_DEFS, MARKET_DEFS


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def build_league_features(path: str) -> pd.DataFrame:
    df = load_footystats_csv(path)
    if df.empty:
        return df

    for c in [
        "odds_ft_home_team_win", "odds_ft_draw", "odds_ft_away_team_win",
        "odds_ft_over15", "odds_ft_over25", "odds_ft_over35", "odds_ft_over45",
        "odds_btts_yes", "odds_btts_no",
    ]:
        if c in df.columns:
            df[c.replace("odds_ft_", "odd_").replace("odds_", "odd_")] = _num(df, c)

    df["odd_1"] = _num(df, "odds_ft_home_team_win")
    df["odd_x"] = _num(df, "odds_ft_draw")
    df["odd_2"] = _num(df, "odds_ft_away_team_win")
    df["odd_fav"] = df[["odd_1", "odd_x", "odd_2"]].min(axis=1)
    df["odd_dog"] = df[["odd_1", "odd_x", "odd_2"]].max(axis=1)
    df["odd_spread_1x2"] = df["odd_dog"] - df["odd_fav"]

    df["xg_home_pre"] = _num(df, "Home Team Pre-Match xG")
    df["xg_away_pre"] = _num(df, "Away Team Pre-Match xG")
    df["xg_diff_pre"] = df["xg_home_pre"] - df["xg_away_pre"]
    df["xg_sum_pre"] = df["xg_home_pre"] + df["xg_away_pre"]
    df["ppg_home"] = _num(df, "Pre-Match PPG (Home)").fillna(_num(df, "home_ppg"))
    df["ppg_away"] = _num(df, "Pre-Match PPG (Away)").fillna(_num(df, "away_ppg"))
    df["ppg_diff"] = df["ppg_home"] - df["ppg_away"]
    df["ppg_sum"] = df["ppg_home"] + df["ppg_away"]
    df["pre_over25_pct"] = _num(df, "over_25_percentage_pre_match")
    df["pre_over15_pct"] = _num(df, "over_15_percentage_pre_match")
    df["pre_over35_pct"] = _num(df, "over_35_percentage_pre_match")
    df["pre_over45_pct"] = _num(df, "over_45_percentage_pre_match")
    df["pre_btts_pct"] = _num(df, "btts_percentage_pre_match")
    df["pre_fh_goal_pct"] = _num(df, "over_05_HT_FHG_percentage_pre_match")
    df["pre_2h_goal_pct"] = _num(df, "over_05_2HG_percentage_pre_match")
    df["pre_over15_2h_pct"] = _num(df, "over_15_2HG_percentage_pre_match")
    df["pre_avg_goals"] = _num(df, "average_goals_per_match_pre_match")
    df["pre_corners"] = _num(df, "average_corners_per_match_pre_match")
    df["pre_cards"] = _num(df, "average_cards_per_match_pre_match")
    df["elo_proxy_home"] = 1000 + (df["ppg_home"] - 1.5) * 120
    df["elo_proxy_away"] = 1000 + (df["ppg_away"] - 1.5) * 120
    df["elo_proxy_diff"] = df["elo_proxy_home"] - df["elo_proxy_away"]

    df = attach_timing_outcomes(df)

    df["month"] = df["date"].dt.to_period("M").astype(str)
    y, m = df["date"].dt.year, df["date"].dt.month
    df["season"] = np.where(
        m >= 7, y.astype(str) + "-" + (y + 1).astype(str), (y - 1).astype(str) + "-" + y.astype(str)
    )
    return df.sort_values("date").reset_index(drop=True)


FEATURE_COLS = [
    "odd_1", "odd_x", "odd_2", "odd_fav", "odd_dog", "odd_spread_1x2",
    "odd_over15", "odd_over25", "odd_over35", "odd_over45", "odd_btts_yes", "odd_btts_no",
    "xg_home_pre", "xg_away_pre", "xg_diff_pre", "xg_sum_pre",
    "ppg_home", "ppg_away", "ppg_diff", "ppg_sum",
    "elo_proxy_home", "elo_proxy_away", "elo_proxy_diff",
    "pre_over25_pct", "pre_over15_pct", "pre_over35_pct", "pre_over45_pct", "pre_btts_pct",
    "pre_fh_goal_pct", "pre_2h_goal_pct", "pre_over15_2h_pct", "pre_avg_goals",
    "pre_corners", "pre_cards",
]

# Colonne calcolate a fine partita: vietate come filtri pre-match (data leakage).
POST_MATCH_COLS = frozenset({
    "first_goal_min", "goals_after_60", "goals_2h",
    "live_h_60", "live_a_60", "live_total_60", "live_h_70", "live_a_70",
    "live_h_ht", "live_a_ht",
})

LIVE_FEATURE_COLS = [
    "live_00_60", "live_10_60", "live_01_60", "live_11_60",
    "live_00_ht", "live_10_70", "live_11_60",
    "odd_over25", "pre_over25_pct", "pre_btts_pct", "xg_sum_pre",
]


def _odds_from_pct(pct: pd.Series, lo: float = 1.12, hi: float = 6.0) -> pd.Series:
    p = (pct / 100.0).clip(0.10, 0.90)
    return (1.0 / p).clip(lo, hi)


def _implied_under_from_over(over: pd.Series, margin: float = 0.03) -> pd.Series:
    over = pd.to_numeric(over, errors="coerce").where(lambda x: x > 1.05)
    p_under = (1.0 - 1.0 / over) * (1.0 + margin)
    return 1.0 / p_under.clip(0.05, 0.95)


def model_odd_from_rate(rate: float, margin: float = 0.05) -> float:
    if rate <= 0.01 or rate >= 0.99:
        return np.nan
    return float(1.0 / (rate * (1.0 + margin)))


def db_odd_column_for_market(market_id: str) -> str | None:
    """Nome colonna quota nel CSV FootyStats (solo colonne bookmaker dirette)."""
    cfg = MARKET_DEFS.get(market_id) or LIVE_MARKET_DEFS.get(market_id, {})
    col = cfg.get("odd_col")
    return col if col else None


def db_odds_series(df: pd.DataFrame, market_id: str) -> pd.Series:
    """Quote lette solo dalla colonna CSV originale — nessuna stima."""
    col = db_odd_column_for_market(market_id)
    if not col or col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").where(lambda x: x > 1.01)


def market_odds_for_frame(
    df: pd.DataFrame,
    market_id: str,
    train_rates: dict[str, float] | None = None,
) -> tuple[pd.Series, pd.Series]:
    cfg = MARKET_DEFS.get(market_id) or LIVE_MARKET_DEFS.get(market_id, {})
    reliable = pd.Series(False, index=df.index)

    col = cfg.get("odd_col")
    if col and col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce").where(lambda x: x > 1.01)
        return s, s.notna()

    implied_from = cfg.get("implied_from")
    if implied_from and implied_from in df.columns:
        s = _implied_under_from_over(pd.to_numeric(df[implied_from], errors="coerce"))
        return s, s.notna()

    pct_col = cfg.get("pct_col")
    if pct_col and pct_col in df.columns:
        pct = pd.to_numeric(df[pct_col], errors="coerce")
        return _odds_from_pct(pct), pct.notna()

    if market_id == "home_win":
        s = pd.to_numeric(df["odd_1"], errors="coerce")
        return s, s.notna() & (s > 1.01)
    if market_id == "away_win":
        s = pd.to_numeric(df["odd_2"], errors="coerce")
        return s, s.notna() & (s > 1.01)
    if market_id == "draw":
        s = pd.to_numeric(df["odd_x"], errors="coerce")
        return s, s.notna() & (s > 1.01)

    ycol = cfg.get("y")
    if ycol and ycol in df.columns:
        rate = (train_rates or {}).get(market_id, float(df[ycol].mean()))
        odd = model_odd_from_rate(rate)
        if odd and np.isfinite(odd):
            return pd.Series(odd, index=df.index), reliable

    default = cfg.get("default_odd")
    if default:
        return pd.Series(float(default), index=df.index), reliable

    return pd.Series(np.nan, index=df.index), reliable


def available_features(df: pd.DataFrame, include_live: bool = True, numeric_only: bool = True) -> list[str]:
    cols = list(FEATURE_COLS)
    if include_live:
        cols = list(dict.fromkeys(cols + LIVE_FEATURE_COLS))
    out = []
    for c in cols:
        if c in POST_MATCH_COLS:
            continue
        if c not in df.columns:
            continue
        if numeric_only and (df[c].dtype == bool or df[c].nunique(dropna=True) <= 2):
            continue
        if df[c].notna().sum() >= 40:
            out.append(c)
    return out


def available_bool_features(df: pd.DataFrame) -> list[str]:
    out = []
    for c in LIVE_FEATURE_COLS:
        if c in df.columns and df[c].dtype == bool and df[c].notna().sum() >= 40:
            out.append(c)
    return out


# Re-export per compatibilità con import legacy
from core.live_states import apply_live_state_mask  # noqa: E402, F401
