"""Ottimizzazione combinazioni pattern 1 SH."""
from core.pattern_combo_optimizer import best_combos, optimize_pattern_combos
from core.sh1_backtest import run_sh1_backtest
from core.sh1_loader import list_available_patterns

optimize_sh1_combos = lambda df, patterns=None: optimize_pattern_combos(
    df,
    lambda d, p: run_sh1_backtest(d, p),
    patterns=patterns or list_available_patterns(df),
)

__all__ = ["optimize_sh1_combos", "best_combos", "list_available_patterns"]
