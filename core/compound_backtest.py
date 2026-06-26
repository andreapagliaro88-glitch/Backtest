import pandas as pd

from core.ccs_runner import run_ccs_backtest
from core.strategy_engine import iter_combined_trades


def run_compound_backtest(df_grouped, df_raw, initial_bankroll=None):
    """Backtest compound con Controlled Compounding System."""
    return run_ccs_backtest(df_grouped, df_raw, initial_bankroll)


def print_compound_stats(df_trades, ccs):
    active = df_trades[df_trades["stake_eur"] > 0] if not df_trades.empty else df_trades
    s = ccs.summary()

    print("\n===== CCS COMPOUND BACKTEST =====")
    print(f"  Bankroll iniziale: {s['initial_bankroll']:.2f} €")
    print(f"  Bankroll finale:   {s['final_bankroll']:.2f} €")
    print(f"  Profitto totale:   {s['total_profit_eur']:.2f} € (incl. prelievi)")
    print(f"  Prelievi:          {s['n_withdrawals']} × {s['total_withdrawn']:.2f} €")
    print(f"  ROI:               {s['roi_pct']:.2f}%")
    print(f"  Max DD:            {s['max_dd_eur']:.2f} € ({s['max_dd_pct']:.2f}%)")
    print(f"  1U finale:         {s['current_unit_eur']:.2f} €")
    print(f"  Trade attivi:      {s['trades']}")

    if active.empty:
        return

    print(f"  Winrate:           {s['winrate'] * 100:.2f}%")

    monthly = df_trades.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit_eur"].sum()
    print(f"\n  Media mensile: {monthly_profit.mean():.2f} €")
