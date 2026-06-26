"""Caricamento file Excel 0 SH da data/sh0/ con tag pattern."""
from __future__ import annotations

import os
import re

import pandas as pd

SH0_PATTERNS = ("0-0", "Push", "Carry", "Rise", "Chain", "Momentum")


def pattern_from_filename(filename: str) -> str:
    name = os.path.basename(filename).lower()
    name_clean = re.sub(r"[^\w\s.\-%]", " ", name)
    if "0-0" in name or "0 0" in name_clean:
        return "0-0"
    for label, key in [
        ("Push", "push"),
        ("Carry", "carry"),
        ("Rise", "rise"),
        ("Chain", "chain"),
        ("Momentum", "momentum"),
    ]:
        if key in name_clean or key in name:
            return label
    return os.path.splitext(os.path.basename(filename))[0]


def load_sh0_data(base_path: str = "data/sh0") -> pd.DataFrame:
    """Ogni riga = 1 segnale; colonna pattern = file sorgente."""
    if not os.path.isdir(base_path):
        return pd.DataFrame()

    parts = []
    from collections import defaultdict

    files_by_pattern: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for file in os.listdir(base_path):
        if not file.endswith(".xlsx"):
            continue
        path = os.path.join(base_path, file)
        files_by_pattern[pattern_from_filename(file)].append((file, path))

    for pattern, items in sorted(files_by_pattern.items()):
        file, path = max(items, key=lambda x: os.path.getsize(x[1]))
        df = pd.read_excel(path)
        df.columns = df.columns.str.strip().str.lower()

        df = df.rename(columns={
            "id": "match_id",
            "data (utc)": "date",
            "gol casa": "home_ft",
            "gol ospite": "away_ft",
            "vinto": "vinto",
        })

        if "match_id" not in df.columns or "date" not in df.columns:
            continue

        df = df.drop_duplicates(subset=["match_id", "date"], keep="first")

        df["goals_ft"] = df["home_ft"] + df["away_ft"]
        df["signal"] = 1
        df["system"] = "SH0"
        df["pattern"] = pattern
        df["source_file"] = file

        if "vinto" in df.columns:
            df["vinto"] = df["vinto"].astype(bool)
        else:
            home_ht_col = next((c for c in df.columns if c.startswith("gol casa 1")), None)
            away_ht_col = next((c for c in df.columns if c.startswith("gol ospite 1")), None)
            if home_ht_col and away_ht_col:
                goals_2h = (df[home_ht_col].fillna(0) + df[away_ht_col].fillna(0)) == 0
                goals_ft = df["goals_ft"] == df[home_ht_col].fillna(0) + df[away_ht_col].fillna(0)
                df["vinto"] = goals_2h & goals_ft
            else:
                df["vinto"] = False

        parts.append(df[[
            "match_id", "date", "goals_ft", "signal", "vinto", "system", "pattern", "source_file",
        ]])

    if not parts:
        return pd.DataFrame()

    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out.dropna(subset=["date"]).reset_index(drop=True)


def list_available_patterns(df: pd.DataFrame) -> list[str]:
    if df.empty or "pattern" not in df.columns:
        return []
    found = [p for p in SH0_PATTERNS if p in set(df["pattern"])]
    extra = sorted(set(df["pattern"]) - set(SH0_PATTERNS))
    return found + extra
