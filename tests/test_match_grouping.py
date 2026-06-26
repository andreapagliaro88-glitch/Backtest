"""Test dedup partite tra file pattern."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.match_grouping import group_by_fixture
from core.o15_tier_backtest import prepare_o15_tier_data, run_o15_tier_backtest


def test_same_match_multiple_files_one_row():
    df = pd.DataFrame([
        {"match_id": 1, "date": "2025-01-01", "goals_ft": 3, "signal": 1, "vinto": True,
         "system": "O15", "pattern": "Boost"},
        {"match_id": 1, "date": "2025-01-01", "goals_ft": 3, "signal": 1, "vinto": True,
         "system": "O15", "pattern": "Flow"},
    ])
    grouped = prepare_o15_tier_data(df)
    assert len(grouped) == 1
    assert grouped.iloc[0]["patterns"] == ["Boost", "Flow"]
    assert grouped.iloc[0]["signals"] == 2


def test_backtest_one_trade_per_match():
    df = pd.DataFrame([
        {"match_id": 1, "date": "2025-01-01", "goals_ft": 3, "signal": 1, "vinto": True,
         "system": "O15", "pattern": "Boost"},
        {"match_id": 1, "date": "2025-01-01", "goals_ft": 3, "signal": 1, "vinto": True,
         "system": "O15", "pattern": "Flow"},
        {"match_id": 2, "date": "2025-01-02", "goals_ft": 2, "signal": 1, "vinto": False,
         "system": "O15", "pattern": "Boost"},
    ])
    trades = run_o15_tier_backtest(df)
    assert len(trades) == 2


if __name__ == "__main__":
    test_same_match_multiple_files_one_row()
    test_backtest_one_trade_per_match()
    print("match_grouping tests OK.")
