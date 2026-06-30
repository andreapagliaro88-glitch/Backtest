"""Persistenza stato strategia (combinazioni, combo attiva, tier) tra refresh browser."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

STATE_DIR = Path("output/strategy_state")


def _state_path(cfg_key: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{cfg_key}.json"


def _serialize_combo_df(df: pd.DataFrame | None) -> list[dict] | None:
    if df is None or df.empty:
        return None
    out = df.copy()
    for col in ("patterns", "ht_patterns", "o15_patterns", "o25_patterns"):
        if col in out.columns:
            out[col] = out[col].apply(
                lambda v: list(v) if isinstance(v, (tuple, list)) else v
            )
    return json.loads(out.to_json(orient="records", date_format="iso"))


def _deserialize_combo_df(records: list[dict] | None) -> pd.DataFrame | None:
    if not records:
        return None
    df = pd.DataFrame(records)
    for col in ("patterns", "ht_patterns", "o15_patterns", "o25_patterns"):
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: tuple(v) if isinstance(v, list) else v
            )
    return df


def save_strategy_state(cfg_key: str, payload: dict[str, Any]) -> None:
    path = _state_path(cfg_key)
    data = {"version": 1, **payload}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_strategy_state(cfg_key: str) -> dict[str, Any] | None:
    path = _state_path(cfg_key)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_state_payload(cfg_key: str, session: dict) -> dict[str, Any]:
    combo_df = session.get(f"{cfg_key}_combo_results")
    return {
        "active_patterns": list(session.get(f"{cfg_key}_active_patterns") or []),
        "active_combo_label": session.get(f"{cfg_key}_active_combo_label"),
        "combo_stakes_fp": session.get(f"{cfg_key}_combo_stakes_fp"),
        "combo_stakes_label": session.get(f"{cfg_key}_combo_stakes_label"),
        "combo_stale": bool(session.get(f"{cfg_key}_combo_stale")),
        "tier_rules_dict": session.get(f"{cfg_key}_tier_rules_dict"),
        "workflow_tier_done": session.get(f"{cfg_key}_workflow_tier_done"),
        "workflow_stake_done": session.get(f"{cfg_key}_workflow_stake_done"),
        "combo_results": _serialize_combo_df(combo_df),
    }


def persist_from_session(cfg_key: str, session: dict) -> None:
    save_strategy_state(cfg_key, build_state_payload(cfg_key, session))


def hydrate_session(cfg_key: str, session: dict) -> bool:
    """Carica stato salvato in session_state. Ritorna True se trovato."""
    flag = f"{cfg_key}_state_hydrated"
    if session.get(flag):
        return False
    session[flag] = True

    data = load_strategy_state(cfg_key)
    if not data:
        return False

    if data.get("active_patterns"):
        session[f"{cfg_key}_active_patterns"] = tuple(data["active_patterns"])
    if data.get("active_combo_label"):
        session[f"{cfg_key}_active_combo_label"] = data["active_combo_label"]
        session[f"{cfg_key}_combo_summary_dirty"] = True
    if data.get("combo_stakes_fp"):
        session[f"{cfg_key}_combo_stakes_fp"] = data["combo_stakes_fp"]
    if data.get("combo_stakes_label"):
        session[f"{cfg_key}_combo_stakes_label"] = data["combo_stakes_label"]
    if data.get("combo_stale"):
        session[f"{cfg_key}_combo_stale"] = data["combo_stale"]
    if data.get("tier_rules_dict"):
        session[f"{cfg_key}_tier_rules_dict"] = data["tier_rules_dict"]
    if data.get("workflow_tier_done"):
        session[f"{cfg_key}_workflow_tier_done"] = data["workflow_tier_done"]
    if data.get("workflow_stake_done"):
        session[f"{cfg_key}_workflow_stake_done"] = data["workflow_stake_done"]

    combo_df = _deserialize_combo_df(data.get("combo_results"))
    if combo_df is not None and not combo_df.empty:
        session[f"{cfg_key}_combo_results"] = combo_df
        session[f"{cfg_key}_patterns_dirty"] = True

    return True
