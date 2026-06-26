"""Persistenza risultati Probability Pattern Engine."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import pandas as pd

OUTPUT_DIR = os.path.join("output", "probability_patterns")


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip().lower())
    return s.strip("_") or "league"


def _ensure_dir() -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


def save_results(
    league: str,
    df: pd.DataFrame,
    meta: dict[str, Any],
    updated: datetime | None = None,
) -> str:
    """Salva CSV + meta JSON. Restituisce path del CSV."""
    root = _ensure_dir()
    ts = (updated or datetime.now()).strftime("%Y%m%d_%H%M%S")
    slug = _slug(league)
    csv_path = os.path.join(root, f"{slug}_{ts}.csv")
    meta_path = os.path.join(root, f"{slug}_{ts}_meta.json")
    latest_csv = os.path.join(root, f"{slug}_latest.csv")
    latest_meta = os.path.join(root, f"{slug}_latest_meta.json")

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    meta_out = {
        **meta,
        "league": league,
        "saved_at": (updated or datetime.now()).isoformat(),
        "n_patterns": len(df),
        "csv_file": os.path.basename(csv_path),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2)

    df.to_csv(latest_csv, index=False, encoding="utf-8-sig")
    with open(latest_meta, "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2)

    return csv_path


def list_saved_runs() -> list[dict[str, Any]]:
    root = _ensure_dir()
    runs: list[dict[str, Any]] = []
    for fn in os.listdir(root):
        if not fn.endswith("_meta.json"):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
            csv_fn = meta.get("csv_file") or fn.replace("_meta.json", ".csv")
            csv_path = os.path.join(root, csv_fn)
            if os.path.isfile(csv_path):
                runs.append({**meta, "meta_path": path, "csv_path": csv_path})
        except (json.JSONDecodeError, OSError):
            continue
    runs.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return runs


def load_saved_run(csv_path: str) -> tuple[pd.DataFrame, dict[str, Any], datetime | None]:
    meta_path = csv_path.replace(".csv", "_meta.json")
    if not meta_path.endswith("_meta.json"):
        base = os.path.splitext(csv_path)[0]
        meta_path = f"{base}_meta.json"
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    meta: dict[str, Any] = {}
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    updated = None
    if meta.get("saved_at"):
        try:
            updated = datetime.fromisoformat(meta["saved_at"])
        except ValueError:
            pass
    return df, meta, updated


def load_latest_for_league(league: str) -> tuple[pd.DataFrame, dict[str, Any], datetime | None] | None:
    path = os.path.join(_ensure_dir(), f"{_slug(league)}_latest.csv")
    if not os.path.isfile(path):
        return None
    df, meta, updated = load_saved_run(path)
    return df, meta, updated
