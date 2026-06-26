"""Unione partite duplicate tra file pattern — 1 sola riga (e 1 giocata) per match_id + data."""
from __future__ import annotations

from typing import Iterable

import pandas as pd


def _patterns_agg(series: pd.Series) -> list[str]:
    return sorted(set(series.dropna().astype(str)))


def group_by_fixture(
    df: pd.DataFrame,
    patterns: tuple[str, ...] | list[str] | None = None,
    *,
    system: str | None = None,
    include_pattern_list: bool = False,
) -> pd.DataFrame:
    """
    Stessa partita in più file Excel → una sola riga.
    I segnali dei pattern vengono sommati (engine attivi); il backtest fa 1 trade.
    """
    data = df.copy()
    if system and "system" in data.columns:
        data = data[data["system"] == system]
    if patterns and "pattern" in data.columns:
        data = data[data["pattern"].isin(patterns)]

    empty_cols = ["match_id", "date", "signals", "vinto"]
    if "goals_ft" in df.columns:
        empty_cols.append("goals_ft")
    if "goals_ht" in df.columns:
        empty_cols.append("goals_ht")
    if include_pattern_list:
        empty_cols.extend(["patterns", "patterns_str"])

    if data.empty:
        return pd.DataFrame(columns=empty_cols)

    agg: dict = {
        "signal": "sum",
        "vinto": "max",
    }
    if "goals_ft" in data.columns:
        agg["goals_ft"] = "first"
    if "goals_ht" in data.columns:
        agg["goals_ht"] = "first"
    if include_pattern_list and "pattern" in data.columns:
        agg["pattern"] = _patterns_agg

    grouped = data.groupby(["match_id", "date"], as_index=False).agg(agg)
    grouped = grouped.rename(columns={"signal": "signals"})
    grouped["date"] = pd.to_datetime(grouped["date"])

    if include_pattern_list and "pattern" in grouped.columns:
        grouped = grouped.rename(columns={"pattern": "patterns"})
        grouped["patterns_str"] = grouped["patterns"].apply(lambda p: " + ".join(p))
        grouped["signals"] = grouped["patterns"].apply(len)

    return grouped.sort_values(["date", "signals"]).reset_index(drop=True)
