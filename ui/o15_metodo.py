"""Compatibilità O15 — re-export da tier_metodo generico."""
from ui.tier_metodo import (
    active_tier_rules,
    apply_tier_rules,
    format_stakes_summary,
    mark_combos_stale,
    render_stake_simulator,
    render_tier_optimizer,
    show_active_config_banner,
    show_tier_metodo_panel,
    stakes_fingerprint,
)


def o15_active_tier_rules():
    return active_tier_rules("o15", "O15")


def format_o15_stakes_summary(rules=None):
    from core.tier_engine import TierRules
    if rules is not None and isinstance(rules, TierRules):
        return (
            f"T1={rules.stake_t1}U · T2={rules.stake_t2}U · "
            f"T3={rules.stake_t3}U · T4={rules.stake_t4}U"
        )
    return format_stakes_summary("o15", "O15")


def o15_stakes_fingerprint(rules=None):
    return stakes_fingerprint("o15", "O15", rules)


def mark_o15_combos_stale():
    mark_combos_stale("o15")


def apply_o15_tier_rules(rules_dict: dict):
    apply_tier_rules("o15", rules_dict)


def show_o15_active_config_banner(*, always: bool = False):
    show_active_config_banner("o15", "O15", always=always)


def show_o15_metodo_panel(df_trades=None, df_raw=None):
    show_tier_metodo_panel("o15", "O15", "Over 1.5", df_trades, df_raw)


def render_o15_tier_optimizer(df_raw):
    render_tier_optimizer("o15", "O15", "Over 1.5", df_raw)


def render_o15_stake_simulator(df_raw):
    render_stake_simulator("o15", "O15", "Over 1.5", df_raw)
