"""Configurazione tier per strategia (HT, O15, O25, SH0/1/2)."""
from __future__ import annotations

from core.tier_engine import O15_TIER_RISK, O15_TIER_RULES, TierRiskRules, TierRules

TIER_SYSTEMS = ("HT", "O15", "O25", "SH0", "SH1", "SH2")

SYSTEM_PROFIT_ODDS: dict[str, float] = {
    "HT": 0.4,
    "O15": 0.35,
    "O25": 0.8,
    "SH0": 0.3,
    "SH1": 0.3,
    "SH2": 0.3,
}

DEFAULT_TIER_RULES: dict[str, TierRules] = {
    "HT": TierRules(
        stake_t1=5.0, stake_t2=3.0, stake_t3=1.5, stake_t4=0.8,
        tier3_patterns=[], tier4_patterns=[],
    ),
    "O15": O15_TIER_RULES,
    "O25": TierRules(
        stake_t1=5.0, stake_t2=3.0, stake_t3=1.2, stake_t4=0.8,
        tier3_patterns=[], tier4_patterns=[],
    ),
    "SH0": TierRules(
        stake_t1=1.5, stake_t2=1.2, stake_t3=1.0, stake_t4=0.8,
        tier3_patterns=[], tier4_patterns=[],
    ),
    "SH1": TierRules(
        stake_t1=1.5, stake_t2=1.2, stake_t3=1.0, stake_t4=0.8,
        tier3_patterns=[], tier4_patterns=[],
    ),
    "SH2": TierRules(
        stake_t1=1.5, stake_t2=1.2, stake_t3=1.0, stake_t4=0.8,
        tier3_patterns=[], tier4_patterns=[],
    ),
}


def default_tier_rules(system: str) -> TierRules:
    return DEFAULT_TIER_RULES.get(system, TierRules())


def profit_odds_for(system: str) -> float:
    return SYSTEM_PROFIT_ODDS.get(system, 0.35)


def default_tier_risk(system: str) -> TierRiskRules:
    return O15_TIER_RISK
