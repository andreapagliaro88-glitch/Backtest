"""Parser file Fixtures (HT / Over 1.5 / Over 2.5 / 0 SH) da export Excel."""
from __future__ import annotations

import os
import re

import pandas as pd

SH0_FILE_PATTERNS = (
    "0 sh",
    "sh push",
    "sh carry",
    "sh rise",
    "sh chain",
    "sh momentum",
    "sh pattern",
    "0-sh",
)


SH1_FILE_PATTERNS = (
    "1 sh",
    "sh reload",
    "sh chain",
    "sh carry",
    "sh boost",
    "sh followup",
    "sh follow up",
    "sh echo",
    "sh double",
    "second half engine",
    "1-sh",
)


SH2_FILE_PATTERNS = (
    "2 sh",
    "sh momentum",
    "sh impulse",
    "sh drive",
    "sh secondhit",
    "sh second hit",
    "sh carry",
    "sh wave",
    "sh double",
    "sh onflow",
    "sh on flow",
    "second half engine",
    "2-sh",
)


def strategy_from_filename(filename: str) -> str | None:
    name = os.path.basename(filename).lower()
    name_clean = re.sub(r"[^\w\s.\-%]", " ", name)
    name_clean = re.sub(r"\s+", " ", name_clean).strip()

    if "_ht " in name or name.startswith("fixtures_ht"):
        return "HT"
    if "ov. 1.5" in name or "ov 1.5" in name or "over 1.5" in name:
        return "O15"
    if "ov. 2.5" in name or "ov 2.5" in name or "over 2.5" in name:
        return "O25"
    if "2 sh" in name_clean or "2-sh" in name_clean:
        for pat in SH2_FILE_PATTERNS:
            if pat in name_clean or pat in name:
                return "SH2"
        if "sh" in name_clean:
            return "SH2"
    if "1 sh" in name_clean or "1-sh" in name_clean:
        for pat in SH1_FILE_PATTERNS:
            if pat in name_clean or pat in name:
                return "SH1"
        if "sh" in name_clean:
            return "SH1"
    for pat in SH0_FILE_PATTERNS:
        if pat in name_clean or pat in name:
            return "SH0"
    return None


def _pick_col(columns, *candidates):
    cols_lower = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def parse_fixture_file(path_or_buffer, filename: str) -> pd.DataFrame:
    strategia = strategy_from_filename(filename)
    if strategia is None:
        raise ValueError(f"Strategia non riconosciuta dal nome file: {filename}")

    df = pd.read_excel(path_or_buffer)
    cols = list(df.columns)

    col_data = _pick_col(cols, "Orario inizio", "data", "date", "Data (UTC)")
    col_casa = _pick_col(cols, "Squadra di casa", "casa", "home", "Casa")
    col_ospite = _pick_col(cols, "Squadra in trasferta", "ospite", "away", "Ospite")
    col_campionato = _pick_col(cols, "Nome campionato", "campionato", "league", "Lega")
    col_paese = _pick_col(cols, "Nome paese", "paese", "country", "Paese")
    col_fid = _pick_col(cols, "fixture_id - C", "fixture_id", "id", "ID")

    if not all([col_data, col_casa, col_ospite]):
        raise ValueError(f"Colonne mancanti in {filename}")

    out = pd.DataFrame()
    out["data"] = pd.to_datetime(df[col_data], errors="coerce")
    out["ora"] = out["data"].dt.strftime("%H:%M")
    out["campionato"] = df[col_campionato].astype(str) if col_campionato else ""
    if col_paese is not None and col_campionato is not None:
        out["campionato"] = df[col_paese].astype(str) + " - " + df[col_campionato].astype(str)
    elif col_paese is not None and not col_campionato:
        out["campionato"] = df[col_paese].astype(str)
    out["casa"] = df[col_casa].astype(str)
    out["ospite"] = df[col_ospite].astype(str)
    out["partita"] = out["casa"] + " - " + out["ospite"]
    out["match_id"] = df[col_fid] if col_fid else (out["partita"] + "_" + out["data"].astype(str))
    out["strategia"] = strategia
    out["segnali"] = 1
    out["fonte_file"] = os.path.basename(filename)

    return out.dropna(subset=["data"]).reset_index(drop=True)


def merge_fixture_files(files: list[tuple]) -> pd.DataFrame:
    """
    files: lista di (buffer_or_path, filename)
    Ritorna dataframe aggregato con segnali sommati per match+strategia.
    """
    parts = []
    for buf, fname in files:
        parts.append(parse_fixture_file(buf, fname))

    if not parts:
        return pd.DataFrame()

    raw = pd.concat(parts, ignore_index=True)

    agg = raw.groupby(
        ["match_id", "data", "strategia"],
        as_index=False,
    ).agg(
        segnali=("segnali", "sum"),
        ora=("ora", "first"),
        campionato=("campionato", "first"),
        partita=("partita", "first"),
        fonti=("fonte_file", lambda x: ", ".join(sorted(set(x)))),
    )

    return agg.sort_values(["data", "ora", "match_id"]).reset_index(drop=True)


def merge_to_daily_format(merged: pd.DataFrame) -> pd.DataFrame:
    """Converte in formato long per daily_trades."""
    rows = []
    for _, r in merged.iterrows():
        rows.append({
            "data": r["data"],
            "ora": r["ora"],
            "campionato": r["campionato"],
            "partita": r["partita"],
            "match_id": r["match_id"],
            "strategia": r["strategia"],
            "segnali": int(r["segnali"]),
            "fonti": r.get("fonti", ""),
        })
    return pd.DataFrame(rows)


def pivot_signals(merged: pd.DataFrame) -> dict:
    """match_id -> {HT: n, O15: n, O25: n, SH0: n}"""
    out = {}
    for _, r in merged.iterrows():
        key = r["match_id"]
        if key not in out:
            out[key] = {"HT": 0, "O15": 0, "O25": 0, "SH0": 0, "SH1": 0, "SH2": 0}
        out[key][r["strategia"]] = int(r["segnali"])
    return out
