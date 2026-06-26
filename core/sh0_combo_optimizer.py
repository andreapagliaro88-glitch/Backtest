"""Ottimizzazione combinazioni pattern 0 SH — wrapper."""
from core.pattern_combo_optimizer import best_combos, optimize_pattern_combos
from core.sh0_backtest import run_sh0_backtest
from core.sh0_loader import list_available_patterns

optimize_sh0_combos = lambda df, patterns=None: optimize_pattern_combos(
    df,
    lambda d, p: run_sh0_backtest(d, p),
    patterns=patterns or list_available_patterns(df),
)

__all__ = ["optimize_sh0_combos", "best_combos", "list_available_patterns"]
