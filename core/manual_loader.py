"""Caricamento Excel per strategia manuale (upload UI o cartella data/manual/)."""
from __future__ import annotations

import io
import os
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from core.manual_strategy import MANUAL_SYSTEM

MANUAL_DATA_DIR = Path("data/manual")


def pattern_from_filename(filename: str) -> str:
    name = os.path.splitext(os.path.basename(filename))[0]
    clean = re.sub(r"[^\w\s.\-%']", " ", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = re.sub(r"\s*-\s*\d+%.*$", "", clean)
    clean = re.sub(r"\s*\d+%.*$", "", clean).strip()
    return clean or name


def _normalize_excel(df: pd.DataFrame, filename: str) -> pd.DataFrame | None:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df = df.rename(columns={
        "id": "match_id",
        "data (utc)": "date",
        "gol casa": "home_ft",
        "gol ospite": "away_ft",
    })

    if "match_id" not in df.columns or "date" not in df.columns:
        return None

    if "home_ft" not in df.columns or "away_ft" not in df.columns:
        return None

    df = df.drop_duplicates(subset=["match_id", "date"], keep="first")
    df["goals_ft"] = df["home_ft"] + df["away_ft"]
    pattern = pattern_from_filename(filename)

    if "vinto" in df.columns:
        df["vinto"] = df["vinto"].astype(bool)
    else:
        home_ht_col = next((c for c in df.columns if c.startswith("gol casa 1")), None)
        away_ht_col = next((c for c in df.columns if c.startswith("gol ospite 1")), None)
        if home_ht_col and away_ht_col:
            ht_goals = df[home_ht_col].fillna(0) + df[away_ht_col].fillna(0)
            df["vinto"] = ht_goals >= 1
        elif "goals_ft" in df.columns:
            df["vinto"] = df["goals_ft"] >= 1
        else:
            df["vinto"] = False

    df["signal"] = 1
    df["system"] = MANUAL_SYSTEM
    df["pattern"] = pattern
    df["source_file"] = os.path.basename(filename)

    cols = ["match_id", "date", "goals_ft", "signal", "vinto", "system", "pattern", "source_file"]
    return df[cols]


def load_from_bytes(content: bytes, filename: str) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(content))
    out = _normalize_excel(df, filename)
    return out if out is not None else pd.DataFrame()


def load_from_uploads(files) -> pd.DataFrame:
    """files: iterable di UploadedFile Streamlit o (name, bytes)."""
    files_by_pattern: dict[str, list[tuple[str, bytes]]] = defaultdict(list)
    for item in files:
        if hasattr(item, "getvalue"):
            name = item.name
            content = item.getvalue()
        else:
            name, content = item
        if not str(name).lower().endswith(".xlsx"):
            continue
        pat = pattern_from_filename(name)
        files_by_pattern[pat].append((name, content))

    parts = []
    for pattern, items in sorted(files_by_pattern.items()):
        name, content = max(items, key=lambda x: len(x[1]))
        chunk = load_from_bytes(content, name)
        if not chunk.empty:
            chunk["pattern"] = pattern
            parts.append(chunk)

    if not parts:
        return pd.DataFrame()

    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out.dropna(subset=["date"]).reset_index(drop=True)


def load_from_folder(base_path: str | Path = MANUAL_DATA_DIR) -> pd.DataFrame:
    base = Path(base_path)
    if not base.is_dir():
        return pd.DataFrame()
    files = [f for f in base.iterdir() if f.suffix.lower() == ".xlsx"]
    if not files:
        return pd.DataFrame()
    return load_from_uploads([(f.name, f.read_bytes()) for f in files])


def save_uploads_to_folder(files, base_path: str | Path = MANUAL_DATA_DIR) -> int:
    base = Path(base_path)
    base.mkdir(parents=True, exist_ok=True)
    n = 0
    for item in files:
        name = item.name if hasattr(item, "name") else item[0]
        content = item.getvalue() if hasattr(item, "getvalue") else item[1]
        if not str(name).lower().endswith(".xlsx"):
            continue
        (base / os.path.basename(name)).write_bytes(content)
        n += 1
    return n


def list_available_patterns(df: pd.DataFrame) -> list[str]:
    if df.empty or "pattern" not in df.columns:
        return []
    return sorted(df["pattern"].dropna().unique().tolist())


def merge_manual_daily_files(
    files: list[tuple],
    active_patterns: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    """
    Merge file Excel manuali del giorno (stesso formato backtest).
    Ritorna dataframe compatibile con merge_fixture_files / daily_trades.
    """
    allowed = set(active_patterns) if active_patterns else None
    rows: list[dict] = []

    for buf, fname in files:
        if isinstance(buf, (str, os.PathLike)):
            content = Path(buf).read_bytes()
        elif hasattr(buf, "read"):
            content = buf.read()
        else:
            content = bytes(buf)
        chunk = load_from_bytes(content, fname)
        if chunk.empty:
            continue
        pat = pattern_from_filename(fname)
        if allowed is not None and pat not in allowed:
            continue
        for _, r in chunk.iterrows():
            rows.append({
                "match_id": r["match_id"],
                "data": pd.to_datetime(r["date"], errors="coerce"),
                "ora": "",
                "campionato": "",
                "partita": f"Match {r['match_id']}",
                "strategia": MANUAL_SYSTEM,
                "segnali": 1,
                "fonte_file": os.path.basename(fname),
                "pattern": pat,
            })

    if not rows:
        return pd.DataFrame()

    raw = pd.DataFrame(rows).dropna(subset=["data"])
    agg = raw.groupby(["match_id", "data", "strategia"], as_index=False).agg(
        segnali=("segnali", "sum"),
        ora=("ora", "first"),
        campionato=("campionato", "first"),
        partita=("partita", "first"),
        fonti=("fonte_file", lambda x: ", ".join(sorted(set(x)))),
        patterns=("pattern", lambda x: sorted(set(x))),
    )
    agg["patterns_str"] = agg["patterns"].apply(lambda p: " + ".join(p))
    return agg.sort_values(["data", "ora", "match_id"]).reset_index(drop=True)
