"""Strategia manuale: file Excel caricati dall'utente + quota personalizzata."""
from __future__ import annotations

import pandas as pd

MANUAL_SYSTEM = "MANUAL"
MANUAL_CFG_KEY = "manual"

_manual_profit_odds: float = 0.35
_manual_decimal_odds: float = 1.35
_manual_label: str = "Manuale"


def set_manual_odds(decimal_odds: float) -> None:
    global _manual_profit_odds, _manual_decimal_odds
    dec = max(float(decimal_odds), 1.01)
    _manual_decimal_odds = dec
    _manual_profit_odds = round(dec - 1.0, 4)


def get_manual_profit_odds() -> float:
    return _manual_profit_odds


def get_manual_decimal_odds() -> float:
    return _manual_decimal_odds


def set_manual_label(label: str) -> None:
    global _manual_label
    _manual_label = (label or "Manuale").strip() or "Manuale"


def get_manual_label() -> str:
    return _manual_label


def run_manual_backtest(
    df: pd.DataFrame,
    patterns=None,
    tier_mode: bool = True,
    tier_rules=None,
    **kwargs,
) -> pd.DataFrame:
    from core.tier_backtest import run_tier_backtest

    if tier_mode:
        return run_tier_backtest(df, MANUAL_SYSTEM, patterns, rules=tier_rules)
    return run_tier_backtest(df, MANUAL_SYSTEM, patterns, rules=tier_rules)


def manual_format_params(params) -> str:
    return "—"
