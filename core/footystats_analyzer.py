"""Analisi generica quote 1X2 vs mercati — CSV FootyStats."""
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.footystats_markets import MARKETS, MIN_ROBUST, MIN_SAMPLE, SCAN_COLS

DATA_DIR = os.path.join("data", "footystats")
OUTPUT_DIR = os.path.join("output", "footystats")


@dataclass
class AnalysisResult:
    league: str
    market_id: str
    market_label: str
    matches: int
    base_winrate: float
    results: pd.DataFrame
    robust: pd.DataFrame
    best_range: str
    best_roi: float


def load_footystats_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", low_memory=False)
    df["date"] = pd.to_datetime(df["date_GMT"], format="mixed", errors="coerce")
    df = df[df["status"] == "complete"].copy()

    numeric_cols = [
        "odds_ft_home_team_win", "odds_ft_draw", "odds_ft_away_team_win",
        "odds_ft_over15", "odds_ft_over25", "odds_ft_over35", "odds_ft_over45",
        "odds_btts_yes", "odds_btts_no",
        "home_team_goal_count_half_time", "away_team_goal_count_half_time",
        "home_team_goal_count", "away_team_goal_count",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    ht_h = df["home_team_goal_count_half_time"].fillna(0)
    ht_a = df["away_team_goal_count_half_time"].fillna(0)
    ft_h = df["home_team_goal_count"].fillna(0)
    ft_a = df["away_team_goal_count"].fillna(0)
    sh_h = ft_h - ht_h
    sh_a = ft_a - ht_a

    df["fh_goal"] = (ht_h + ht_a) >= 1
    df["sh_goal"] = (sh_h + sh_a) >= 1
    df["sh_2plus"] = (sh_h + sh_a) >= 2
    df["ft_2plus"] = (ft_h + ft_a) >= 2
    df["ft_3plus"] = (ft_h + ft_a) >= 3
    df["ft_4plus"] = (ft_h + ft_a) >= 4
    df["btts"] = (ft_h >= 1) & (ft_a >= 1)
    df["home_win"] = ft_h > ft_a
    df["draw"] = ft_h == ft_a
    df["away_win"] = ft_h < ft_a

    df = df[
        (df["odds_ft_home_team_win"] > 1.01)
        & (df["odds_ft_draw"] > 1.01)
        & (df["odds_ft_away_team_win"] > 1.01)
    ].copy()

    df["odd_1"] = df["odds_ft_home_team_win"]
    df["odd_x"] = df["odds_ft_draw"]
    df["odd_2"] = df["odds_ft_away_team_win"]
    df["odd_fav"] = df[["odd_1", "odd_x", "odd_2"]].min(axis=1)
    df["odd_dog"] = df[["odd_1", "odd_x", "odd_2"]].max(axis=1)
    df["spread_fav_dog"] = df["odd_dog"] - df["odd_fav"]

    return df.sort_values("date").reset_index(drop=True)


def _bet_odd(row, market_cfg) -> float:
    odds_col = market_cfg.get("odds_col")
    if odds_col and odds_col in row.index:
        val = row[odds_col]
        if pd.notna(val) and val > 1.01:
            return float(val)
    default = market_cfg.get("default_odd")
    if default is not None:
        return float(default)
    return float("nan")


def _range_profit(sub: pd.DataFrame, target_col: str, market_cfg) -> tuple[float, float, float]:
    n = len(sub)
    if n == 0:
        return 0.0, 0.0, 0.0

    wins = sub[target_col].astype(bool)
    winrate = wins.mean()
    profits = []
    for _, row in sub.iterrows():
        odd = _bet_odd(row, market_cfg)
        if pd.isna(odd):
            continue
        profits.append(odd - 1 if row[target_col] else -1.0)

    if profits:
        roi = sum(profits) / len(profits) * 100
        profit_u = sum(profits)
    else:
        roi = (winrate * (market_cfg["default_odd"] - 1) - (1 - winrate)) * 100 if market_cfg["default_odd"] else 0
        profit_u = winrate * (market_cfg["default_odd"] - 1) - (1 - winrate) if market_cfg["default_odd"] else 0

    return winrate, profit_u, roi


def scan_market(df: pd.DataFrame, market_id: str, step: float = 0.05) -> pd.DataFrame:
    cfg = MARKETS[market_id]
    target_col = cfg["target_col"]
    rows = []

    for col, (lo, hi) in SCAN_COLS.items():
        edges = np.arange(lo, hi + step, step)
        for i in range(len(edges) - 1):
            a, b = edges[i], edges[i + 1]
            is_last = i == len(edges) - 2
            if is_last:
                mask = (df[col] >= a) & (df[col] <= b)
                label = f"{a:.2f}-{b:.2f}"
            else:
                mask = (df[col] >= a) & (df[col] < b)
                label = f"{a:.2f}-{b:.2f}"

            sub = df[mask]
            n = len(sub)
            if n < MIN_SAMPLE:
                continue

            wr, prof, roi = _range_profit(sub, target_col, cfg)
            rows.append({
                "colonna": col,
                "range": label,
                "min": a,
                "max": b,
                "n": n,
                "winrate": wr,
                "profit_u": prof,
                "roi_pct": roi,
                "break_even_odd": 1 / wr if wr > 0 else np.nan,
            })

    if not rows:
        return pd.DataFrame(columns=[
            "colonna", "range", "min", "max", "n", "winrate",
            "profit_u", "roi_pct", "break_even_odd",
        ])
    return pd.DataFrame(rows).sort_values("roi_pct", ascending=False).reset_index(drop=True)


def analyze_league_market(df: pd.DataFrame, league: str, market_id: str) -> AnalysisResult:
    cfg = MARKETS[market_id]
    target_col = cfg["target_col"]
    results = scan_market(df, market_id)
    robust = results[results["n"] >= MIN_ROBUST].copy()

    best = results.iloc[0] if not results.empty else None
    best_range = f"{best['colonna']} {best['range']}" if best is not None else "—"
    best_roi = float(best["roi_pct"]) if best is not None else 0.0

    return AnalysisResult(
        league=league,
        market_id=market_id,
        market_label=cfg["label"],
        matches=len(df),
        base_winrate=float(df[target_col].mean()),
        results=results,
        robust=robust,
        best_range=best_range,
        best_roi=best_roi,
    )


def list_csv_files(data_dir: str = DATA_DIR) -> list[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.lower().endswith(".csv")
    )


def export_result(result: AnalysisResult, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{result.market_id}.xlsx")

    info = pd.DataFrame([{
        "Campionato": result.league,
        "Mercato": result.market_label,
        "Partite": result.matches,
        "Winrate base %": round(result.base_winrate * 100, 2),
        "Miglior range": result.best_range,
        "Miglior ROI %": round(result.best_roi, 2),
    }])

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        info.to_excel(writer, sheet_name="Info", index=False)
        result.results.head(50).to_excel(writer, sheet_name="Top range", index=False)
        result.robust.head(30).to_excel(writer, sheet_name="Range robusti", index=False)
        result.results[result.results["roi_pct"] > 0].to_excel(
            writer, sheet_name="Profittevoli", index=False
        )

    return path


def run_analysis(
    market_ids: list[str] | None = None,
    files: list[str] | None = None,
    data_dir: str = DATA_DIR,
    output_dir: str = OUTPUT_DIR,
) -> pd.DataFrame:
    market_ids = market_ids or list(MARKETS.keys())
    paths = files or list_csv_files(data_dir)
    if not paths:
        raise FileNotFoundError(f"Nessun CSV in {data_dir}")

    summary_rows = []
    for path in paths:
        league = os.path.splitext(os.path.basename(path))[0]
        df = load_footystats_csv(path)
        league_out = os.path.join(output_dir, league)

        for mid in market_ids:
            if mid not in MARKETS:
                continue
            result = analyze_league_market(df, league, mid)
            export_result(result, league_out)

            best_robust = result.robust.iloc[0] if not result.robust.empty else None
            summary_rows.append({
                "campionato": league,
                "mercato": result.market_label,
                "partite": result.matches,
                "winrate_base": round(result.base_winrate * 100, 1),
                "miglior_range": result.best_range,
                "miglior_roi": round(result.best_roi, 1),
                "range_robusto": (
                    f"{best_robust['colonna']} {best_robust['range']}"
                    if best_robust is not None else ""
                ),
                "roi_robusto": round(best_robust["roi_pct"], 1) if best_robust is not None else None,
                "n_robusto": int(best_robust["n"]) if best_robust is not None else 0,
                "wr_robusto": round(best_robust["winrate"] * 100, 1) if best_robust is not None else None,
            })

    summary = pd.DataFrame(summary_rows)
    os.makedirs(output_dir, exist_ok=True)
    summary.to_csv(os.path.join(output_dir, "riepilogo_tutti.csv"), index=False)
    summary.to_excel(os.path.join(output_dir, "riepilogo_tutti.xlsx"), index=False)
    return summary
