"""Caricamento Excel con tag pattern per HT / O15 / O25."""
from __future__ import annotations

import os
import re
from collections import defaultdict

import pandas as pd


def _find_ht_goal_columns(columns):
    home_col = next((c for c in columns if c.startswith("gol casa 1")), None)
    away_col = next((c for c in columns if c.startswith("gol ospite 1")), None)
    return home_col, away_col


def pattern_from_filename(filename: str, system: str = "") -> str:
    name = os.path.splitext(os.path.basename(filename))[0]
    clean = re.sub(r"[^\w\s.\-%']", " ", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = re.sub(r"\s*-\s*\d+%.*$", "", clean)
    clean = re.sub(r"\s*\d+%.*$", "", clean)
    clean = re.sub(r"\s*\(\d+\)\s*$", "", clean).strip()

    upper = clean.upper()
    if system == "HT" or upper.startswith("HT "):
        clean = re.sub(r"^HT\s+", "", clean, flags=re.I).strip()
    elif system == "O15" or "1.5" in clean or "1,5" in clean:
        clean = re.sub(r"^(Ov\.?\s*)?1[.,]5\s*", "", clean, flags=re.I).strip()
    elif system == "O25" or "2.5" in clean or "2,5" in clean:
        clean = re.sub(r"^(Ov\.?\s*)?2[.,]5\s*", "", clean, flags=re.I).strip()

    return clean or os.path.splitext(os.path.basename(filename))[0]


def _read_folder(path: str, system: str, is_ht: bool) -> list[pd.DataFrame]:
    files_by_pattern: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for file in os.listdir(path):
        if not file.endswith(".xlsx"):
            continue
        fpath = os.path.join(path, file)
        pat = pattern_from_filename(file, system)
        files_by_pattern[pat].append((file, fpath))

    parts = []
    for pattern, items in sorted(files_by_pattern.items()):
        file, fpath = max(items, key=lambda x: os.path.getsize(x[1]))
        df = pd.read_excel(fpath)
        df.columns = df.columns.str.strip().str.lower()
        df = df.rename(columns={"id": "match_id", "data (utc)": "date"})

        if is_ht:
            home_ht_col, away_ht_col = _find_ht_goal_columns(df.columns)
            if home_ht_col is None or away_ht_col is None:
                continue
            df = df.rename(columns={
                home_ht_col: "home_ht",
                away_ht_col: "away_ht",
                "gol casa": "home_ft",
                "gol ospite": "away_ft",
            })
            df["goals_ht"] = df["home_ht"] + df["away_ht"]
            df["goals_ft"] = df["home_ft"] + df["away_ft"]
            if "vinto" in df.columns:
                df["vinto"] = df["vinto"].astype(bool)
            else:
                df["vinto"] = df["goals_ht"] >= 1
            cols = ["match_id", "date", "goals_ht", "goals_ft", "vinto"]
        else:
            df = df.rename(columns={"gol casa": "home_ft", "gol ospite": "away_ft", "vinto": "vinto"})
            df["goals_ft"] = df["home_ft"] + df["away_ft"]
            if "vinto" in df.columns:
                df["vinto"] = df["vinto"].astype(bool)
            cols = ["match_id", "date", "goals_ft", "vinto"]

        df["signal"] = 1
        df["system"] = system
        df["pattern"] = pattern
        df["source_file"] = file
        parts.append(df[cols + ["signal", "system", "pattern", "source_file"]])

    return parts


def load_pattern_data(base_path: str = "data") -> pd.DataFrame:
    dfs = []
    mapping = [
        ("ht", "HT", True),
        ("over15", "O15", False),
        ("over25", "O25", False),
    ]
    for folder, system, is_ht in mapping:
        path = os.path.join(base_path, folder)
        if os.path.isdir(path):
            dfs.extend(_read_folder(path, system, is_ht))

    if not dfs:
        return pd.DataFrame()

    out = pd.concat(dfs, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out.dropna(subset=["date"]).reset_index(drop=True)


def filter_by_patterns(
    df: pd.DataFrame,
    ht: tuple[str, ...] | list[str] | None = None,
    o15: tuple[str, ...] | list[str] | None = None,
    o25: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    masks = []
    for system, patterns in [("HT", ht), ("O15", o15), ("O25", o25)]:
        sys_mask = df["system"] == system
        if patterns:
            masks.append(~sys_mask | df["pattern"].isin(patterns))
        else:
            masks.append(pd.Series(True, index=df.index))
    combined = masks[0]
    for m in masks[1:]:
        combined &= m
    return df[combined].reset_index(drop=True)
