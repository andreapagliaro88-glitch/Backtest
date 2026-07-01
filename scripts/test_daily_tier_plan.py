"""Verifica allineamento trade giornaliero con combo + stake tier."""
from core.fixture_parser import merge_fixture_files, pattern_from_fixture_filename
from core.strategy_daily_plan import StrategyDailyPlanConfig, plan_tier_daily_match
from core.tier_backtest import TierState
from core.tier_engine import TierRules, rules_for_pattern_combo
from core.controlled_compounding import ControlledCompounding


def test_pattern_filter_and_stake():
    active = ("Carry", "Momentum", "Impulse", "Wave")
    base = TierRules(
        stake_t1=4.0, stake_t2=2.0, stake_t3=1.5, stake_t4=1.5,
        tier3_patterns=["Impulse", "Double", "Wave"],
        tier4_patterns=["Carry", "Momentum", "OnFlow"],
    )
    rules = rules_for_pattern_combo(active, base)
    cfg = StrategyDailyPlanConfig(system="SH2", rules=rules, active_patterns=active)

    files = [
        ("Carry_SH2.xlsx", "Carry"),
        ("Momentum_SH2.xlsx", "Momentum"),
        ("Impulse_SH2.xlsx", "Impulse"),
        ("Drive_SH2.xlsx", "Drive"),  # non in combo — ignorato
    ]
    # Simula merge senza file reali: test pattern_from_fixture_filename
    assert pattern_from_fixture_filename("Fixtures 2 SH Carry.xlsx", "SH2") == "Carry"
    assert pattern_from_fixture_filename("2 SH Impulse export.xlsx", "SH2") == "Impulse"

    row = {
        "data": "2026-06-23",
        "ora": "20:00",
        "campionato": "Test",
        "partita": "A - B",
    }
    tier_state = TierState()
    ccs = ControlledCompounding(500)
    plan = plan_tier_daily_match(
        row, "m1", ["Carry", "Momentum", "Impulse"], cfg, tier_state, ccs,
        fonti="Carry.xlsx, Momentum.xlsx, Impulse.xlsx",
    )
    assert plan["esito"] == "DA GIOCARE"
    assert plan["stake_u"] == 4.0, f"T1 atteso 4U, got {plan['stake_u']}"
    assert plan["modalita_rischio"] == "Tier"
    assert "Carry" in plan["note"]
    print("OK: combo filter + stake tier T1 =", plan["stake_u"])


if __name__ == "__main__":
    test_pattern_filter_and_stake()
