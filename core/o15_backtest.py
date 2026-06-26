import numpy as np
import pandas as pd

O15_SHOCK_TRADES = 5
O15_SHOCK_FACTOR = 0.6
O15_LOSS_STREAK_TRIGGER = 3
O15_BOOST_STAKE = 8.0
O15_BOOST_HISTORY = 60
O15_BOOST_MIN_SIGNALS = 3
O15_PROFIT_ODDS = 0.35


def o15_base_stake(signals):
    if signals >= 4:
        return 6.0
    if signals == 3:
        return 3.5
    if signals == 2:
        return 3.0
    return 0


class O15State:
    def __init__(self):
        self.equity = 0
        self.peak = 0
        self.profits = []
        self.equity_history = []
        self.loss_streak = 0
        self.shock_mode = 0


def process_o15_trade(row, state):
    signals = row["signals"]
    stake = row["base_stake"]

    if state.shock_mode > 0:
        stake *= O15_SHOCK_FACTOR
        state.shock_mode -= 1

    if len(state.equity_history) > O15_BOOST_HISTORY:
        avg_equity = np.mean(state.equity_history[-O15_BOOST_HISTORY:])
        if state.equity > avg_equity and signals >= O15_BOOST_MIN_SIGNALS:
            stake = O15_BOOST_STAKE

    if row["vinto"] == 1:
        profit = stake * O15_PROFIT_ODDS
        state.loss_streak = 0
    else:
        profit = -stake
        state.loss_streak += 1

    if state.loss_streak >= O15_LOSS_STREAK_TRIGGER:
        state.shock_mode = O15_SHOCK_TRADES
        state.loss_streak = 0

    state.equity += profit
    state.peak = max(state.peak, state.equity)
    state.profits.append(profit)
    state.equity_history.append(state.equity)

    return stake, profit, state.equity


def prepare_o15_data(df, patterns=None):
    """Prepara dati O15 — usa grouping tier (pattern per partita)."""
    from core.o15_tier_backtest import prepare_o15_tier_data
    return prepare_o15_tier_data(df, patterns)


def _prepare_o15_data_legacy(df, patterns=None):
    from core.match_grouping import group_by_fixture

    return group_by_fixture(df, patterns, system="O15")


def run_o15_backtest(df, patterns=None, tier_mode: bool = True, tier_rules=None):
    if tier_mode:
        from core.o15_tier_backtest import run_o15_tier_backtest
        return run_o15_tier_backtest(df, patterns, rules=tier_rules)
    data = _prepare_o15_data_legacy(df, patterns)
    data["base_stake"] = data["signals"].apply(o15_base_stake)
    data = data[data["base_stake"] > 0].sort_values(["date", "signals"]).reset_index(drop=True)

    state = O15State()
    records = []

    for _, row in data.iterrows():
        stake, profit, equity = process_o15_trade(row, state)
        records.append([row["date"], "O15", stake, profit, equity])

    df_trades = pd.DataFrame(records, columns=["date", "system", "stake", "profit", "equity"])
    if df_trades.empty:
        df_trades["peak"] = []
        df_trades["dd"] = []
        return df_trades

    df_trades["peak"] = df_trades["equity"].cummax()
    df_trades["dd"] = df_trades["equity"] - df_trades["peak"]
    return df_trades


def print_o15_stats(df_trades):
    active = df_trades[df_trades["stake"] > 0]
    total_profit = df_trades["profit"].sum()
    max_dd = df_trades["dd"].min()
    total_trades = len(active)
    avg_trade = total_profit / total_trades if total_trades else 0
    winrate = (active["profit"] > 0).mean() if total_trades else 0

    print("\n===== OVER 1.5 V4 OTTIMIZZATO =====")
    print(f"  Profit: {total_profit:.2f} U")
    print(f"  Max DD: {max_dd:.2f} U")
    print(f"  Trade attivi: {total_trades}")
    print(f"  Avg/trade: {avg_trade:.3f} U")
    print(f"  Winrate: {winrate * 100:.2f}%")

    df_trades = df_trades.copy()
    df_trades["date"] = pd.to_datetime(df_trades["date"])
    monthly = df_trades.groupby(df_trades["date"].dt.to_period("M"))["profit"].sum()

    print("\n  --- Profitto mensile ---")
    for month, profit in monthly.items():
        print(f"  {month}: {profit:.2f} U")
    print(f"\n  Media U/mese: {monthly.mean():.2f} U")
