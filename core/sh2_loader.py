"""Caricamento file Excel 2 SH da data/sh2/ con tag pattern."""
from __future__ import annotations

import os
import re
from collections import defaultdict

import pandas as pd

SH2_PATTERNS = (
    "Momentum", "Impulse", "Drive", "SecondHit", "Carry", "Wave", "Double", "OnFlow",
    "Second Half Engine",
)


def is_sh2_file(filename: str) -> bool:
    name = os.path.basename(filename).lower()
    name_clean = re.sub(r"[^\w\s.\-%]", " ", name)
    name_clean = re.sub(r"\s+", " ", name_clean).strip()
    if "0 sh" in name_clean or "1 sh" in name_clean:
        return False
    return "2 sh" in name_clean or "2-sh" in name_clean


def pattern_from_filename(filename: str) -> str:
    name = os.path.basename(filename).lower()
    name_clean = re.sub(r"[^\w\s.\-%]", " ", name)
    name_clean = re.sub(r"\s+", " ", name_clean).strip()
    compact = name_clean.replace(" ", "")

    if "second half engine" in name_clean:
        return "Second Half Engine"
    mapping = [
        ("Momentum", "momentum"),
        ("Impulse", "impulse"),
        ("Drive", "drive"),
        ("SecondHit", "secondhit"),
        ("Carry", "carry"),
        ("Wave", "wave"),
        ("Double", "double"),
        ("OnFlow", "onflow"),
    ]
    for label, key in mapping:
        if key in compact or key in name_clean:
            return label
    if "second" in name_clean and "hit" in name_clean:
        return "SecondHit"
    if "on" in name_clean and "flow" in name_clean:
        return "OnFlow"
    return os.path.splitext(os.path.basename(filename))[0]


def load_sh2_data(base_path: str = "data/sh2") -> pd.DataFrame:
    if not os.path.isdir(base_path):
        return pd.DataFrame()

    files_by_pattern: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for file in os.listdir(base_path):
        if not file.endswith(".xlsx") or not is_sh2_file(file):
            continue
        path = os.path.join(base_path, file)
        files_by_pattern[pattern_from_filename(file)].append((file, path))

    parts = []
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
        df["system"] = "SH2"
        df["pattern"] = pattern
        df["source_file"] = file

        if "vinto" in df.columns:
            df["vinto"] = df["vinto"].astype(bool)
        else:
            home_ht_col = next((c for c in df.columns if c.startswith("gol casa 1")), None)
            away_ht_col = next((c for c in df.columns if c.startswith("gol ospite 1")), None)
            if home_ht_col and away_ht_col:
                ht_goals = df[home_ht_col].fillna(0) + df[away_ht_col].fillna(0)
                df["vinto"] = ht_goals >= 2
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
    found = [p for p in SH2_PATTERNS if p in set(df["pattern"])]
    extra = sorted(set(df["pattern"]) - set(SH2_PATTERNS))
    return found + extra
