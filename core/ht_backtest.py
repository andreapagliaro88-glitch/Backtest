import numpy as np
import pandas as pd

HT_DD_SKIP_T2 = -9
HT_DEFENSIVE_DD = -12
HT_DEFENSIVE_FACTOR = 0.4
HT_BOOST_STAKE = 5.5
HT_BOOST_HISTORY = 40
HT_BOOST_MIN_SIGNALS = 3
HT_PROFIT_ODDS = 0.4


def ht_base_stake(signals):
    if signals >= 4:
        return 3.5
    if signals == 3:
        return 3.0
    if signals == 2:
        return 1.2
    return 0


class HTState:
    def __init__(self):
        self.equity = 0
        self.peak = 0
        self.profits = []
        self.equity_history = []


def process_ht_trade(row, state):
    signals = row["signals"]
    stake = row["base_stake"]
    drawdown = state.equity - state.peak

    if drawdown < HT_DD_SKIP_T2 and signals == 2:
        state.profits.append(0)
        state.equity_history.append(state.equity)
        return 0, 0, state.equity

    if drawdown < HT_DEFENSIVE_DD:
        stake *= HT_DEFENSIVE_FACTOR

    if len(state.equity_history) > HT_BOOST_HISTORY:
        avg_equity = np.mean(state.equity_history[-HT_BOOST_HISTORY:])
        if state.equity > avg_equity and signals >= HT_BOOST_MIN_SIGNALS:
            stake = HT_BOOST_STAKE

    if row["vinto"]:
        profit = stake * HT_PROFIT_ODDS
    else:
        profit = -stake

    state.equity += profit
    state.peak = max(state.peak, state.equity)
    state.profits.append(profit)
    state.equity_history.append(state.equity)

    return stake, profit, state.equity


def prepare_ht_data(df, patterns=None):
    from core.match_grouping import group_by_fixture

    return group_by_fixture(df, patterns, system="HT")


def run_ht_backtest(df, patterns=None, tier_mode: bool = True, tier_rules=None):
    if tier_mode:
        from core.tier_backtest import run_tier_backtest
        return run_tier_backtest(df, "HT", patterns, rules=tier_rules)
    data = prepare_ht_data(df, patterns)
    data["base_stake"] = data["signals"].apply(ht_base_stake)
    data = data[data["base_stake"] > 0].sort_values(["date", "signals"]).reset_index(drop=True)

    state = HTState()
    records = []

    for _, row in data.iterrows():
        stake, profit, equity = process_ht_trade(row, state)
        records.append([row["date"], "HT", stake, profit, equity])

    df_trades = pd.DataFrame(records, columns=["date", "system", "stake", "profit", "equity"])
    if df_trades.empty:
        df_trades["peak"] = []
        df_trades["dd"] = []
        return df_trades

    df_trades["peak"] = df_trades["equity"].cummax()
    df_trades["dd"] = df_trades["equity"] - df_trades["peak"]
    return df_trades


def print_ht_stats(df_trades):
    active = df_trades[df_trades["stake"] > 0]
    total_profit = df_trades["profit"].sum()
    max_dd = df_trades["dd"].min()
    total_trades = len(active)
    avg_trade = total_profit / total_trades if total_trades else 0
    winrate = (active["profit"] > 0).mean() if total_trades else 0

    print("\n===== HT V4 OTTIMIZZATO =====")
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
