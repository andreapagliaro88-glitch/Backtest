import numpy as np
import pandas as pd

O25_DD_SKIP = -10
O25_SHOCK_TRADES = 8
O25_SHOCK_FACTOR = 0.4
O25_LOSS_STREAK_TRIGGER = 2
O25_BOOST_STAKE = 4.0
O25_BOOST_HISTORY = 40
O25_BOOST_MIN_SIGNALS = 3
O25_BOOST_REQUIRES_LAST5 = True
O25_PROFIT_ODDS = 0.8


def o25_base_stake(signals):
    if signals >= 4:
        return 3.5
    if signals == 3:
        return 1.2
    if signals == 2:
        return 1.0
    return 0


class O25State:
    def __init__(self):
        self.equity = 0
        self.peak = 0
        self.profits = []
        self.equity_history = []
        self.loss_streak = 0
        self.shock_mode = 0


def process_o25_trade(row, state):
    signals = row["signals"]
    stake = row["base_stake"]
    drawdown = state.equity - state.peak

    if drawdown < O25_DD_SKIP and signals == 2:
        state.profits.append(0)
        state.equity_history.append(state.equity)
        return 0, 0, state.equity

    if state.shock_mode > 0:
        stake *= O25_SHOCK_FACTOR
        state.shock_mode -= 1

    if len(state.equity_history) > O25_BOOST_HISTORY:
        avg_equity = np.mean(state.equity_history[-O25_BOOST_HISTORY:])
        last5 = state.profits[-5:] if len(state.profits) >= 5 else []
        last5_ok = sum(last5) > 0 if O25_BOOST_REQUIRES_LAST5 else True

        if state.equity > avg_equity and last5_ok and signals >= O25_BOOST_MIN_SIGNALS:
            stake = O25_BOOST_STAKE

    if row["vinto"] == 1:
        profit = stake * O25_PROFIT_ODDS
        state.loss_streak = 0
    else:
        profit = -stake
        state.loss_streak += 1

    if state.loss_streak >= O25_LOSS_STREAK_TRIGGER:
        state.shock_mode = O25_SHOCK_TRADES
        state.loss_streak = 0

    state.equity += profit
    state.peak = max(state.peak, state.equity)
    state.profits.append(profit)
    state.equity_history.append(state.equity)

    return stake, profit, state.equity


def prepare_o25_data(df, patterns=None):
    from core.match_grouping import group_by_fixture

    return group_by_fixture(df, patterns, system="O25")


def run_o25_backtest(df, patterns=None, tier_mode: bool = True, tier_rules=None):
    if tier_mode:
        from core.tier_backtest import run_tier_backtest
        return run_tier_backtest(df, "O25", patterns, rules=tier_rules)
    data = prepare_o25_data(df, patterns)
    data["base_stake"] = data["signals"].apply(o25_base_stake)
    data = data[data["base_stake"] > 0].sort_values(["date", "signals"]).reset_index(drop=True)

    state = O25State()
    records = []

    for _, row in data.iterrows():
        stake, profit, equity = process_o25_trade(row, state)
        records.append([row["date"], "O25", stake, profit, equity])

    df_trades = pd.DataFrame(records, columns=["date", "system", "stake", "profit", "equity"])
    if df_trades.empty:
        df_trades["peak"] = []
        df_trades["dd"] = []
        return df_trades

    df_trades["peak"] = df_trades["equity"].cummax()
    df_trades["dd"] = df_trades["equity"] - df_trades["peak"]
    return df_trades


def print_o25_stats(df_trades):
    active = df_trades[df_trades["stake"] > 0]
    total_profit = df_trades["profit"].sum()
    max_dd = df_trades["dd"].min()
    total_trades = len(active)
    avg_trade = total_profit / total_trades if total_trades else 0
    winrate = (active["profit"] > 0).mean() if total_trades else 0

    print("\n===== OVER 2.5 OTTIMIZZATO =====")
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
