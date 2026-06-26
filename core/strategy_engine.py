import pandas as pd
import numpy as np
from core.combined_config import CombinedParams
from core.ht_backtest import HTState, ht_base_stake, process_ht_trade, prepare_ht_data
from core.o15_backtest import O15State, o15_base_stake, process_o15_trade
from core.o25_backtest import O25State, o25_base_stake, process_o25_trade
from core.sh0_backtest import SH0State, sh0_base_stake, process_sh0_trade


class StrategyState:
    def __init__(self):
        self.equity_u = 0.0
        self.peak_u = 0.0
        self.ht = HTState()
        self.o15 = O15State()
        self.o25 = O25State()
        self.sh0 = SH0State()


def build_ht_lookup(df_raw):
    ht_lookup = {}
    if df_raw is None or df_raw.empty:
        return ht_lookup

    ht_data = prepare_ht_data(df_raw)
    ht_data["base_stake"] = ht_data["signals"].apply(ht_base_stake)
    ht_data = ht_data[ht_data["base_stake"] > 0]
    for _, ht_row in ht_data.iterrows():
        ht_lookup[(ht_row["match_id"], ht_row["date"])] = ht_row
    return ht_lookup


def iter_combined_trades(df_grouped, df_raw, params=None):
    params = params or CombinedParams()
    state = StrategyState()
    ht_lookup = build_ht_lookup(df_raw)
    full_stop = 0

    for (match_id, date), group in df_grouped.groupby(
        ["match_id", "date"], sort=False
    ):
        if full_stop > 0:
            full_stop -= 1
            continue

        drawdown_u = state.equity_u - state.peak_u
        if params.full_stop_dd is not None and drawdown_u < params.full_stop_dd:
            full_stop = params.full_stop_trades

        systems = group["system"].tolist()
        blocked = params.allowed_systems(drawdown_u) or set()
        priority = params.priority_for(drawdown_u)

        chosen = None
        for system_name in priority:
            if system_name in systems and system_name not in blocked:
                chosen = group[group["system"] == system_name].iloc[0]
                break

        if chosen is None:
            continue

        system = chosen["system"]
        trade_date = pd.to_datetime(date)

        if system == "HT":
            ht_row = ht_lookup.get((match_id, trade_date))
            if ht_row is None:
                continue

            state.ht.equity = state.equity_u
            state.ht.peak = state.peak_u
            stake_u, profit_u, equity_u = process_ht_trade(ht_row, state.ht)
            state.equity_u = equity_u
            state.peak_u = state.ht.peak

            yield _trade(trade_date, system, ht_row["signals"], stake_u, profit_u, equity_u, ht_row["vinto"])
            continue

        if system == "O25":
            row = chosen.copy()
            row["base_stake"] = o25_base_stake(row["signals"])
            if row["base_stake"] == 0:
                continue

            state.o25.equity = state.equity_u
            state.o25.peak = state.peak_u
            stake_u, profit_u, equity_u = process_o25_trade(row, state.o25)
            state.equity_u = equity_u
            state.peak_u = state.o25.peak

            if stake_u == 0:
                continue

            yield _trade(trade_date, system, row["signals"], stake_u, profit_u, equity_u, row["vinto"])
            continue

        if system == "O15":
            row = chosen.copy()
            row["base_stake"] = o15_base_stake(row["signals"])
            if row["base_stake"] == 0:
                continue

            state.o15.equity = state.equity_u
            state.o15.peak = state.peak_u
            stake_u, profit_u, equity_u = process_o15_trade(row, state.o15)
            state.equity_u = equity_u
            state.peak_u = state.o15.peak

            yield _trade(trade_date, system, row["signals"], stake_u, profit_u, equity_u, row["vinto"])
            continue

        if system == "SH0":
            row = chosen.copy()
            row["base_stake"] = sh0_base_stake(row["signals"])
            if row["base_stake"] == 0:
                continue

            state.sh0.equity = state.equity_u
            state.sh0.peak = state.peak_u
            stake_u, profit_u, equity_u = process_sh0_trade(row, state.sh0)
            state.equity_u = equity_u
            state.peak_u = state.sh0.peak

            yield _trade(trade_date, system, row["signals"], stake_u, profit_u, equity_u, row["vinto"])


def _trade(date, system, signals, stake_u, profit_u, equity_u, vinto):
    return {
        "date": date,
        "system": system,
        "signals": signals,
        "stake_u": stake_u,
        "profit_u": profit_u,
        "equity_u": equity_u,
        "vinto": bool(vinto),
        "skipped": stake_u == 0,
    }


def _row_for_system(row):
    system = row["system"]
    if system == "O25":
        signals = row["signals"]
        return {
            "signals": signals,
            "vinto": row["vinto"],
            "base_stake": o25_base_stake(signals),
        }
    if system == "O15":
        signals = row["signals"]
        return {
            "signals": signals,
            "vinto": row["vinto"],
            "base_stake": o15_base_stake(signals),
        }
    if system == "SH0":
        signals = row["signals"]
        return {
            "signals": signals,
            "vinto": row["vinto"],
            "base_stake": sh0_base_stake(signals),
        }
    return row


def prepare_combined_context(df_grouped, df_raw):
    ht_lookup = build_ht_lookup(df_raw)
    groups = []
    for (match_id, date), group in df_grouped.groupby(
        ["match_id", "date"], sort=False
    ):
        systems = {}
        for _, row in group.iterrows():
            systems[row["system"]] = _row_for_system(row)
        groups.append((match_id, pd.to_datetime(date), systems))
    return groups, ht_lookup


def run_combined_metrics(df_grouped, df_raw, params=None, context=None):
    if context is None:
        groups, ht_lookup = prepare_combined_context(df_grouped, df_raw)
    else:
        groups, ht_lookup = context
    return _run_combined_core(groups, ht_lookup, params)


def _run_combined_core(groups, ht_lookup, params=None):
    params = params or CombinedParams()
    state = StrategyState()
    full_stop = 0
    profits = []
    stakes = []
    systems_used = []

    for match_id, trade_date, systems in groups:
        if full_stop > 0:
            full_stop -= 1
            continue

        drawdown_u = state.equity_u - state.peak_u
        if params.full_stop_dd is not None and drawdown_u < params.full_stop_dd:
            full_stop = params.full_stop_trades

        blocked = params.allowed_systems(drawdown_u) or set()
        priority = params.priority_for(drawdown_u)

        system = None
        row = None
        for system_name in priority:
            if system_name in systems and system_name not in blocked:
                system = system_name
                row = systems[system_name]
                break

        if system is None:
            continue

        trade = None

        if system == "HT":
            ht_row = ht_lookup.get((match_id, trade_date))
            if ht_row is None:
                continue
            state.ht.equity = state.equity_u
            state.ht.peak = state.peak_u
            stake_u, profit_u, equity_u = process_ht_trade(ht_row, state.ht)
            state.equity_u = equity_u
            state.peak_u = state.ht.peak
            trade = _trade(trade_date, system, ht_row["signals"], stake_u, profit_u, equity_u, ht_row["vinto"])
        elif system == "O25":
            if row["base_stake"] == 0:
                continue
            state.o25.equity = state.equity_u
            state.o25.peak = state.peak_u
            stake_u, profit_u, equity_u = process_o25_trade(row, state.o25)
            state.equity_u = equity_u
            state.peak_u = state.o25.peak
            if stake_u == 0:
                continue
            trade = _trade(trade_date, system, row["signals"], stake_u, profit_u, equity_u, row["vinto"])
        elif system == "O15":
            if row["base_stake"] == 0:
                continue
            state.o15.equity = state.equity_u
            state.o15.peak = state.peak_u
            stake_u, profit_u, equity_u = process_o15_trade(row, state.o15)
            state.equity_u = equity_u
            state.peak_u = state.o15.peak
            trade = _trade(trade_date, system, row["signals"], stake_u, profit_u, equity_u, row["vinto"])
        elif system == "SH0":
            if row["base_stake"] == 0:
                continue
            state.sh0.equity = state.equity_u
            state.sh0.peak = state.peak_u
            stake_u, profit_u, equity_u = process_sh0_trade(row, state.sh0)
            state.equity_u = equity_u
            state.peak_u = state.sh0.peak
            trade = _trade(trade_date, system, row["signals"], stake_u, profit_u, equity_u, row["vinto"])

        if trade is None or trade["skipped"]:
            continue

        profits.append(trade["profit_u"])
        stakes.append(trade["stake_u"])
        systems_used.append(trade["system"])

    if not profits:
        return {
            "profit": 0,
            "max_dd": 0,
            "trades": 0,
            "winrate": 0,
            "ht_trades": 0,
            "o15_trades": 0,
            "o25_trades": 0,
            "sh0_trades": 0,
        }

    equity = np.cumsum(profits)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    wins = sum(1 for p in profits if p > 0)

    return {
        "profit": float(sum(profits)),
        "max_dd": float(dd.min()),
        "trades": len(stakes),
        "winrate": wins / len(stakes),
        "ht_trades": systems_used.count("HT"),
        "o15_trades": systems_used.count("O15"),
        "o25_trades": systems_used.count("O25"),
        "sh0_trades": systems_used.count("SH0"),
    }


def run_combined_backtest(df_grouped, df_raw, params=None):
    records = []
    for trade in iter_combined_trades(df_grouped, df_raw, params):
        if trade["skipped"]:
            continue
        records.append([
            trade["date"],
            trade["system"],
            trade["stake_u"],
            trade["profit_u"],
            trade["equity_u"],
        ])

    df_trades = pd.DataFrame(records, columns=["date", "system", "stake", "profit", "equity"])
    if df_trades.empty:
        df_trades["peak"] = []
        df_trades["dd"] = []
        return df_trades

    df_trades["peak"] = df_trades["equity"].cummax()
    df_trades["dd"] = df_trades["equity"] - df_trades["peak"]
    return df_trades
