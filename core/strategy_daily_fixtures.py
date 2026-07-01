"""File Fixtures giornalieri per singola strategia (per pattern)."""
from __future__ import annotations

import os
import re
from datetime import datetime

import pandas as pd

FIXTURES_ROOT = os.path.join("data", "daily_trades", "fixtures")

CFG_SYSTEMS: dict[str, tuple[str, ...]] = {
    "ht": ("HT",),
    "o15": ("O15",),
    "o25": ("O25",),
    "sh0": ("SH0",),
    "sh1": ("SH1",),
    "sh2": ("SH2",),
    "combined": ("HT", "O15", "O25"),
    "manual": ("MANUAL",),
}


def fixtures_dir(cfg_key: str) -> str:
    return os.path.join(FIXTURES_ROOT, cfg_key.lower())


def ensure_fixtures_dir(cfg_key: str) -> str:
    path = fixtures_dir(cfg_key)
    os.makedirs(path, exist_ok=True)
    return path


def _safe_filename(name: str) -> str:
    base = os.path.basename(name)
    base = re.sub(r'[<>:"/\\|?*]', "_", base)
    return base or "upload.xlsx"


def pattern_filename(pattern: str) -> str:
    return f"{_safe_filename(pattern)}.xlsx"


def list_fixture_files(cfg_key: str) -> list[dict]:
    folder = ensure_fixtures_dir(cfg_key)
    rows: list[dict] = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith((".xlsx", ".xls")):
            continue
        full = os.path.join(folder, name)
        stat = os.stat(full)
        rows.append({
            "file": name,
            "path": full,
            "size_kb": round(stat.st_size / 1024, 1),
            "updated": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return rows


def file_for_pattern(cfg_key: str, pattern: str) -> str | None:
    folder = fixtures_dir(cfg_key)
    direct = os.path.join(folder, pattern_filename(pattern))
    if os.path.isfile(direct):
        return direct
    pat_l = pattern.lower()
    if not os.path.isdir(folder):
        return None
    for name in os.listdir(folder):
        if not name.lower().endswith((".xlsx", ".xls")):
            continue
        if pat_l in name.lower():
            return os.path.join(folder, name)
    return None


def save_fixture_bytes(cfg_key: str, filename: str, data: bytes) -> str:
    folder = ensure_fixtures_dir(cfg_key)
    path = os.path.join(folder, _safe_filename(filename))
    with open(path, "wb") as f:
        f.write(data)
    return path


def save_pattern_fixture(cfg_key: str, pattern: str, data: bytes, original_name: str = "") -> str:
    ext = ".xlsx"
    if original_name.lower().endswith(".xls"):
        ext = ".xls"
    name = f"{_safe_filename(pattern)}{ext}"
    return save_fixture_bytes(cfg_key, name, data)


def delete_fixture(cfg_key: str, filename: str) -> bool:
    path = os.path.join(fixtures_dir(cfg_key), _safe_filename(filename))
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def fixture_files_as_upload_tuples(cfg_key: str) -> list[tuple[str, str]]:
    """Percorsi file nella cartella strategia per merge_fixture_files."""
    folder = fixtures_dir(cfg_key)
    if not os.path.isdir(folder):
        return []
    out: list[tuple[str, str]] = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith((".xlsx", ".xls")):
            continue
        out.append((os.path.join(folder, name), name))
    return out


def forced_system_for_cfg(cfg_key: str) -> str | None:
    key = cfg_key.lower()
    if key == "manual":
        return "MANUAL"
    allowed = CFG_SYSTEMS.get(key, ())
    if key == "combined" or not allowed:
        return None
    return allowed[0] if len(allowed) == 1 else None


FIXTURE_HINTS: dict[str, str] = {
    "ht": (
        "<code>Fixtures_HT ...</code> (ATTACK CORE, MOMENTUM, RISE, CHAIN, CARRY, PUSH, ecc.). "
        "Solo segnali HT."
    ),
    "o15": "<code>Fixtures_Ov. 1.5 ...</code> — solo segnali Over 1.5.",
    "o25": "<code>Fixtures_Ov. 2.5 ...</code> — solo segnali Over 2.5.",
    "sh0": "<code>0 SH ...</code> (Push, Carry, Rise, Chain, Momentum, 0-0) — solo SH0.",
    "sh1": "File Fixtures SH1 — solo segnali SH1.",
    "sh2": "File Fixtures SH2 — solo segnali SH2.",
    "combined": (
        "<code>Fixtures_HT ...</code>, <code>Fixtures_Ov. 1.5 ...</code>, "
        "<code>Fixtures_Ov. 2.5 ...</code> — orchestrazione combinata HT/O15/O25."
    ),
    "manual": (
        "File Excel <b>uno per pattern</b> (stesso formato del backtest: ID, Data UTC, Gol). "
        "Solo i pattern della combo attiva vengono contati."
    ),
}

DEFAULT_FIXTURE_HINT = (
    "Nome file riconosciuto: <code>Fixtures_HT ...</code>, "
    "<code>Fixtures_Ov. 1.5 ...</code>, <code>Fixtures_Ov. 2.5 ...</code>, "
    "<code>0 SH ...</code> (Push, Carry, Rise, Chain, Momentum, 0-0). "
    "Ogni riga = 1 segnale; più file sulla stessa partita vengono sommati."
)


def preview_merged_fixtures(
    cfg_key: str,
    active_patterns: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Anteprima segnali da tutti i file nella cartella strategia."""
    allowed = CFG_SYSTEMS.get(cfg_key.lower(), ())
    pats = active_patterns if active_patterns is not None else allowed
    file_list = fixture_files_as_upload_tuples(cfg_key)
    if not file_list:
        return pd.DataFrame()

    if cfg_key.lower() == "manual":
        from core.manual_loader import merge_manual_daily_files
        merged = merge_manual_daily_files(file_list, active_patterns=pats if pats else None)
    else:
        from core.fixture_parser import merge_fixture_files
        merged = merge_fixture_files(file_list, active_patterns=pats if pats else None)
    if merged.empty:
        return merged
    if allowed:
        merged = merged[merged["strategia"].isin(allowed)]
    return merged.sort_values(["data", "ora", "match_id"]).reset_index(drop=True)
