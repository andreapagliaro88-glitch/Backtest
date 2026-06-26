"""Test Controlled Compounding System."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compound_config import CCS_DOWNGRADE_TRADES
from core.controlled_compounding import ControlledCompounding
from core.ccs_monte_carlo import run_ccs_monte_carlo


def test_tier_upgrade():
    ccs = ControlledCompounding(150)
    assert ccs.current_unit_eur == 3.0
    ccs.bankroll = 200
    ccs.peak = 200
    ccs._try_upgrade_tier("2024-01-01")
    assert ccs.current_unit_eur == 4.0


def test_no_upgrade_in_drawdown():
    ccs = ControlledCompounding(200)
    assert ccs.current_unit_eur == 4.0
    ccs.peak = 350
    ccs.bankroll = 300
    assert ccs.in_drawdown
    before = ccs.current_unit_eur
    ccs._try_upgrade_tier(None)
    assert ccs.current_unit_eur == before


def test_downgrade_after_50_trades():
    ccs = ControlledCompounding(250)
    assert ccs.current_unit_eur == 5.0
    ccs.bankroll = 240
    for _ in range(CCS_DOWNGRADE_TRADES):
        ccs._update_downgrade_counter()
    assert ccs.current_unit_eur == 4.0


def test_withdrawal():
    ccs = ControlledCompounding(5990)
    ccs.bankroll = 5996
    unit = ccs.current_unit_eur
    ccs.settle_trade(True, 0.4, date="2024-01-01")
    assert len(ccs.withdrawals) == 1
    assert ccs.bankroll == round(5996 + unit * 0.4 - 1000, 2)


def test_monte_carlo():
    trades = [{"vinto": True, "profit_odds": 0.4}] * 50 + [{"vinto": False, "profit_odds": 0.4}] * 30
    mc = run_ccs_monte_carlo(trades, 150, n_simulations=100, seed=1)
    assert mc["n_simulations"] == 100
    assert "profit_p5" in mc


if __name__ == "__main__":
    test_tier_upgrade()
    test_no_upgrade_in_drawdown()
    test_downgrade_after_50_trades()
    test_withdrawal()
    test_monte_carlo()
    print("All CCS tests passed.")
