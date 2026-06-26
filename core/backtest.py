import pandas as pd
from core.strategy_engine import run_combined_backtest


def prepare_grouped(df):
    """Una riga per partita e strategia — più file pattern → segnali sommati, 1 trade."""
    from core.match_grouping import group_by_fixture

    if df.empty:
        return pd.DataFrame(columns=["match_id", "date", "system", "signals", "vinto", "goals_ft"])

    parts = []
    for system in df["system"].dropna().unique():
        sub = group_by_fixture(df, system=system)
        sub["system"] = system
        parts.append(sub)

    if not parts:
        return pd.DataFrame(columns=["match_id", "date", "system", "signals", "vinto", "goals_ft"])

    out = pd.concat(parts, ignore_index=True)
    return out.sort_values("date").reset_index(drop=True)


def run_backtest(df_grouped, system=None, df_raw=None, combined_params=None):
    if system is not None:
        return pd.DataFrame(columns=["date", "system", "stake", "profit", "equity"])

    return run_combined_backtest(df_grouped, df_raw, combined_params)
