"""Test tier engine Over 1.5."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tier_engine import O15_TIER_RULES, classify_tier, stake_u_for_tier


def test_tier_counts():
    assert classify_tier(["A", "B", "C"], O15_TIER_RULES) == 1
    assert classify_tier(["A", "B"], O15_TIER_RULES) == 2
    assert classify_tier(["Boost"], O15_TIER_RULES) == 3
    assert classify_tier(["Flow"], O15_TIER_RULES) == 4
    assert classify_tier(["Unknown"], O15_TIER_RULES) is None


def test_stake():
    assert stake_u_for_tier(1, O15_TIER_RULES) == 5.0
    assert stake_u_for_tier(4, O15_TIER_RULES) == 0.8


if __name__ == "__main__":
    test_tier_counts()
    test_stake()
    print("O15 tier tests OK.")
