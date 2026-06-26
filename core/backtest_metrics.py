"""Metriche comuni per backtest in unità."""
from __future__ import annotations

import pandas as pd


def backtest_metrics(df_trades: pd.DataFrame) -> dict:
    if df_trades.empty:
        return {"profit": 0.0, "max_dd": 0.0, "trades": 0, "winrate": 0.0, "score": 0.0, "calmar": 0.0}

    active = df_trades[df_trades["stake"] > 0]
    profit = float(df_trades["profit"].sum())
    max_dd = float(df_trades["dd"].min())
    trades = len(active)
    winrate = float((active["profit"] > 0).mean()) if trades else 0.0
    score = profit + max_dd * 0.6
    calmar = profit / abs(max_dd) if max_dd < 0 else profit

    return {
        "profit": profit,
        "max_dd": max_dd,
        "trades": trades,
        "winrate": winrate,
        "score": score,
        "calmar": calmar,
    }
