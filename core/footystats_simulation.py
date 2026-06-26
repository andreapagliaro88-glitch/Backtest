"""Simulazione trade e metriche dashboard FootyStats."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from core.footystats_analyzer import _bet_odd, analyze_league_market, load_footystats_csv
from core.footystats_markets import MARKETS, MIN_ROBUST, SCAN_COLS

ODDS_BUCKETS = [
    (1.20, 1.50), (1.50, 1.80), (1.80, 2.10), (2.10, 2.50), (2.50, 3.00),
]

PLOT_LAYOUT = dict(
    paper_bgcolor="#0d1117",
    plot_bgcolor="#161b22",
    font=dict(color="#e6edf3", size=11),
    margin=dict(l=40, r=20, t=48, b=40),
    xaxis=dict(gridcolor="#30363d", zerolinecolor="#30363d"),
    yaxis=dict(gridcolor="#30363d", zerolinecolor="#30363d"),
)


def _mask_range(df: pd.DataFrame, col: str, lo: float, hi: float) -> pd.Series:
    return (df[col] >= lo) & (df[col] <= hi)


def simulate_trades(
    df: pd.DataFrame,
    market_id: str,
    range_col: str,
    range_lo: float,
    range_hi: float,
    league: str,
    stake_eur: float = 100.0,
) -> pd.DataFrame:
    cfg = MARKETS[market_id]
    target = cfg["target_col"]
    sub = df[_mask_range(df, range_col, range_lo, range_hi)].sort_values("date")
    rows = []
    for _, row in sub.iterrows():
        odd = _bet_odd(row, cfg)
        if pd.isna(odd) or odd <= 1.01:
            continue
        won = bool(row[target])
        profit_u = (odd - 1.0) if won else -1.0
        profit_eur = profit_u * stake_eur
        rows.append({
            "date": row["date"],
            "campionato": league,
            "mercato": cfg["label"],
            "market_id": market_id,
            "won": won,
            "odd": odd,
            "profit_u": profit_u,
            "profit_eur": profit_eur,
            "stake_eur": stake_eur,
        })
    return pd.DataFrame(rows)


def enrich_trades(trades: pd.DataFrame, initial_bankroll: float = 10_000.0) -> pd.DataFrame:
    if trades.empty:
        return trades
    t = trades.sort_values("date").reset_index(drop=True)
    t["equity_eur"] = initial_bankroll + t["profit_eur"].cumsum()
    t["peak_eur"] = t["equity_eur"].cummax()
    t["dd_eur"] = t["equity_eur"] - t["peak_eur"]
    t["dd_pct"] = np.where(t["peak_eur"] > 0, t["dd_eur"] / t["peak_eur"] * 100, 0.0)
    t["trade_n"] = np.arange(1, len(t) + 1)

    t["wr_roll"] = t["won"].astype(float).rolling(20, min_periods=1).mean() * 100
    t["roi_roll"] = t["profit_u"].rolling(20, min_periods=1).mean() * 100

    def _pf_roll(s: pd.Series) -> float:
        wins = s[s > 0].sum()
        losses = abs(s[s < 0].sum())
        return wins / losses if losses > 0 else np.nan

    t["pf_roll"] = t["profit_u"].rolling(20, min_periods=1).apply(_pf_roll, raw=False)
    return t


def metrics_from_trades(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "partite": 0, "winrate": 0.0, "roi_pct": 0.0, "profit_factor": 0.0,
            "profit_eur": 0.0, "dd_max_eur": 0.0, "dd_max_pct": 0.0,
            "equity_finale": 0.0,
        }
    wins = trades.loc[trades["profit_eur"] > 0, "profit_eur"].sum()
    losses = abs(trades.loc[trades["profit_eur"] < 0, "profit_eur"].sum())
    pf = wins / losses if losses > 0 else float("inf")
    roi = trades["profit_u"].mean() * 100
    enriched = enrich_trades(trades.copy(), initial_bankroll=0)
    return {
        "partite": len(trades),
        "winrate": trades["won"].mean() * 100,
        "roi_pct": roi,
        "profit_factor": pf,
        "profit_eur": trades["profit_eur"].sum(),
        "dd_max_eur": float(enriched["dd_eur"].min()) if "dd_eur" in enriched else 0.0,
        "dd_max_pct": float(enriched["dd_pct"].min()) if "dd_pct" in enriched else 0.0,
        "equity_finale": float(trades["profit_eur"].sum()),
    }


def drawdown_duration(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "dd_eur" not in trades.columns:
        return pd.DataFrame(columns=["start", "end", "days", "trades"])
    rows = []
    in_dd = False
    start_date = None
    start_idx = 0
    for i, row in trades.iterrows():
        if row["dd_eur"] < -0.01:
            if not in_dd:
                in_dd = True
                start_date = row["date"]
                start_idx = row["trade_n"]
        elif in_dd:
            rows.append({
                "start": start_date,
                "end": row["date"],
                "days": max((row["date"] - start_date).days, 1),
                "trades": int(row["trade_n"] - start_idx),
            })
            in_dd = False
    if in_dd:
        last = trades.iloc[-1]
        rows.append({
            "start": start_date,
            "end": last["date"],
            "days": max((last["date"] - start_date).days, 1),
            "trades": int(last["trade_n"] - start_idx + 1),
        })
    return pd.DataFrame(rows)


def build_heatmap(
    paths: list[str],
    market_id: str,
    date_from=None,
    date_to=None,
) -> pd.DataFrame:
    cfg = MARKETS[market_id]
    target = cfg["target_col"]
    rows = []
    for path in paths:
        league = os.path.splitext(os.path.basename(path))[0]
        df = load_footystats_csv(path)
        if date_from is not None:
            df = df[df["date"] >= pd.Timestamp(date_from)]
        if date_to is not None:
            df = df[df["date"] <= pd.Timestamp(date_to)]
        col = "odd_fav"
        for lo, hi in ODDS_BUCKETS:
            sub = df[_mask_range(df, col, lo, hi)]
            if len(sub) < 20:
                roi = np.nan
            else:
                profits = []
                for _, row in sub.iterrows():
                    odd = _bet_odd(row, cfg)
                    if pd.isna(odd):
                        continue
                    profits.append(odd - 1 if row[target] else -1.0)
                roi = np.mean(profits) * 100 if profits else np.nan
            rows.append({
                "campionato": league,
                "range": f"{lo:.2f}-{hi:.2f}",
                "roi_pct": roi,
            })
    return pd.DataFrame(rows)


def _parse_range_row(row) -> tuple[str, float, float] | None:
    if row is None:
        return None
    return str(row["colonna"]), float(row["min"]), float(row["max"])


def run_dashboard_analysis(
    files: list[str],
    market_ids: list[str],
    date_from=None,
    date_to=None,
    stake_eur: float = 100.0,
    initial_bankroll: float = 10_000.0,
) -> dict:
    summary_rows = []
    all_trades = []

    for path in files:
        league = os.path.splitext(os.path.basename(path))[0]
        df = load_footystats_csv(path)
        if date_from is not None:
            df = df[df["date"] >= pd.Timestamp(date_from)]
        if date_to is not None:
            df = df[df["date"] <= pd.Timestamp(date_to)]
        if df.empty:
            continue

        for mid in market_ids:
            if mid not in MARKETS:
                continue
            result = analyze_league_market(df, league, mid)
            best = result.results.iloc[0] if not result.results.empty else None
            robust = result.robust.iloc[0] if not result.robust.empty else None

            best_rng = _parse_range_row(best)
            rob_rng = _parse_range_row(robust)

            best_trades = pd.DataFrame()
            rob_trades = pd.DataFrame()
            if best_rng:
                best_trades = simulate_trades(
                    df, mid, best_rng[0], best_rng[1], best_rng[2], league, stake_eur,
                )
            if rob_rng:
                rob_trades = simulate_trades(
                    df, mid, rob_rng[0], rob_rng[1], rob_rng[2], league, stake_eur,
                )

            sim_trades = rob_trades if not rob_trades.empty else best_trades
            if not sim_trades.empty:
                all_trades.append(sim_trades)

            best_m = metrics_from_trades(best_trades)
            rob_m = metrics_from_trades(rob_trades)
            sim_m = metrics_from_trades(sim_trades)

            summary_rows.append({
                "campionato": league,
                "mercato": result.market_label,
                "market_id": mid,
                "partite": result.matches,
                "winrate_base": round(result.base_winrate * 100, 1),
                "miglior_range": result.best_range,
                "miglior_roi": round(result.best_roi, 1),
                "range_robusto": (
                    f"{robust['colonna']} {robust['range']}" if robust is not None else ""
                ),
                "roi_robusto": round(robust["roi_pct"], 1) if robust is not None else None,
                "n_robusto": int(robust["n"]) if robust is not None else 0,
                "wr_robusto": round(robust["winrate"] * 100, 1) if robust is not None else None,
                "roi_sim_pct": round(sim_m["roi_pct"], 1),
                "wr_sim_pct": round(sim_m["winrate"], 1),
                "profit_factor": round(sim_m["profit_factor"], 2) if sim_m["profit_factor"] != float("inf") else 99.9,
                "dd_max_eur": round(sim_m["dd_max_eur"], 0),
                "dd_max_pct": round(sim_m["dd_max_pct"], 1),
                "partite_sim": sim_m["partite"],
            })

    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    if not trades.empty:
        trades = trades.sort_values("date").reset_index(drop=True)
        trades = enrich_trades(trades, initial_bankroll)

    summary = pd.DataFrame(summary_rows)
    global_m = metrics_from_trades(trades) if not trades.empty else metrics_from_trades(pd.DataFrame())

    robust_rows = summary[summary["n_robusto"] >= MIN_ROBUST] if not summary.empty else summary
    heatmap = build_heatmap(files, market_ids[0], date_from, date_to) if market_ids else pd.DataFrame()

    return {
        "summary": summary,
        "trades": trades,
        "metrics": global_m,
        "roi_robusto_avg": float(robust_rows["roi_robusto"].dropna().mean()) if not robust_rows.empty else 0.0,
        "roi_best_avg": float(summary["miglior_roi"].mean()) if not summary.empty else 0.0,
        "heatmap": heatmap,
        "dd_duration": drawdown_duration(trades),
    }
