"""Ottimizzazione combinazioni pattern 2 SH."""
from core.pattern_combo_optimizer import best_combos, optimize_pattern_combos
from core.sh2_backtest import run_sh2_backtest
from core.sh2_loader import list_available_patterns

optimize_sh2_combos = lambda df, patterns=None: optimize_pattern_combos(
    df,
    lambda d, p: run_sh2_backtest(d, p),
    patterns=patterns or list_available_patterns(df),
)

__all__ = ["optimize_sh2_combos", "best_combos", "list_available_patterns"]
