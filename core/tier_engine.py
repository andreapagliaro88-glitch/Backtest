"""Classificazione tier per strategia — Metodo Over 1.5 e estensioni future."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace


def normalize_pattern(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).lower().strip())


def pattern_matches(name: str, candidates: list[str]) -> bool:
    p = normalize_pattern(name)
    for c in candidates:
        cn = normalize_pattern(c)
        if cn in p or p in cn:
            return True
    return False


def any_pattern_matches(names: list[str], candidates: list[str]) -> bool:
    return any(pattern_matches(n, candidates) for n in names)


@dataclass
class TierRules:
    """Regole stake U per tier — convertite in € dal CCS come stake_u × 1U."""
    stake_t1: float = 5.0
    stake_t2: float = 3.0
    stake_t3: float = 1.5
    stake_t4: float = 0.8
    tier3_patterns: list[str] = field(default_factory=list)
    tier4_patterns: list[str] = field(default_factory=list)
    min_engines_t1: int = 3
    min_engines_t2: int = 2


@dataclass
class TierRiskRules:
    """Controllo streak — Metodo O1.5."""
    loss_streak_trigger: int = 2
    block_tier4_trades: int = 5
    reduce_t23_factor: float = 0.80
    shock_trades: int = 5
    shock_factor: float = 0.60
    loss_streak_shock: int = 3


O15_TIER_RULES = TierRules(
    stake_t1=5.0,
    stake_t2=3.0,
    stake_t3=1.5,
    stake_t4=0.8,
    # Default allineati ai file Excel tipici (Boost / Flow / Trigger).
    # Usa tab «Ottimizza tier» per ricalibrare sui tuoi dati.
    tier3_patterns=["Boost"],
    tier4_patterns=["Flow"],
)

O15_TIER_RISK = TierRiskRules(
    loss_streak_trigger=2,
    block_tier4_trades=5,
    reduce_t23_factor=0.80,
    shock_trades=5,
    shock_factor=0.60,
    loss_streak_shock=3,
)

TIER_LABELS = {
    1: "T1 — Elite (3+ engine)",
    2: "T2 — Core (2 engine)",
    3: "T3 — Single edge",
    4: "T4 — Marginal",
}


def classify_tier(active_patterns: list[str], rules: TierRules) -> int | None:
    """
    Classifica il tier in base agli engine attivi sulla partita.
    Ritorna None se non si entra (pattern singolo non riconosciuto).
    """
    patterns = [p for p in active_patterns if p]
    n = len(patterns)
    if n >= rules.min_engines_t1:
        return 1
    if n == rules.min_engines_t2:
        return 2
    if n == 1:
        if any_pattern_matches(patterns, rules.tier3_patterns):
            return 3
        if any_pattern_matches(patterns, rules.tier4_patterns):
            return 4
        return None
    return None


def stake_u_for_tier(tier: int, rules: TierRules) -> float:
    return {
        1: rules.stake_t1,
        2: rules.stake_t2,
        3: rules.stake_t3,
        4: rules.stake_t4,
    }.get(tier, 0.0)


def tier_label(tier: int | None) -> str:
    if tier is None:
        return "—"
    return TIER_LABELS.get(tier, f"T{tier}")


def rules_with_all_patterns(patterns: list[str], base: TierRules) -> TierRules:
    """Include ogni pattern in T3/T4 così i singoli engine non vengono saltati."""
    return rules_for_pattern_combo(tuple(patterns), base)


def rules_for_pattern_combo(combo: tuple[str, ...] | list[str], base: TierRules) -> TierRules:
    """Regole tier limitate ai pattern della combinazione attiva."""
    active = list(combo)
    active_set = set(active)
    t3 = [p for p in base.tier3_patterns if p in active_set]
    t4 = [p for p in base.tier4_patterns if p in active_set]
    for p in active:
        if any_pattern_matches([p], t3 + t4):
            continue
        t4.append(p)
    return replace(base, tier3_patterns=t3, tier4_patterns=t4)
