from core.ht_backtest import HTState, ht_base_stake, prepare_ht_data, process_ht_trade
from core.o15_backtest import O15State, o15_base_stake, prepare_o15_data, process_o15_trade
from core.o25_backtest import O25State, o25_base_stake, prepare_o25_data, process_o25_trade


def _vinto_bool(value):
    if isinstance(value, bool):
        return value
    return bool(value)


def _iter_strategy_trades(data, base_stake_fn, state_cls, process_fn, system):
    data = data.copy()
    data["base_stake"] = data["signals"].apply(base_stake_fn)
    data = data[data["base_stake"] > 0].sort_values(["date", "signals"])

    state = state_cls()
    for _, row in data.iterrows():
        stake, profit, equity = process_fn(row, state)
        if stake == 0:
            continue
        yield {
            "date": row["date"],
            "system": system,
            "signals": row["signals"],
            "stake_u": stake,
            "profit_u": profit,
            "equity_u": equity,
            "vinto": _vinto_bool(row["vinto"]),
            "skipped": False,
        }


def iter_ht_trades(df_raw):
    yield from _iter_strategy_trades(
        prepare_ht_data(df_raw), ht_base_stake, HTState, process_ht_trade, "HT"
    )


def iter_o15_trades(df_raw):
    yield from _iter_strategy_trades(
        prepare_o15_data(df_raw), o15_base_stake, O15State, process_o15_trade, "O15"
    )


def iter_o25_trades(df_raw):
    yield from _iter_strategy_trades(
        prepare_o25_data(df_raw), o25_base_stake, O25State, process_o25_trade, "O25"
    )
