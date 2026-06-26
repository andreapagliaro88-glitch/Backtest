from dataclasses import dataclass, asdict
import random

import numpy as np
import pandas as pd

from core.o15_backtest import O15State, _prepare_o15_data_legacy


@dataclass
class O15Params:
    stake_4: float = 5.0
    stake_3: float = 3.0
    stake_2: float = 1.5
    dd_skip_t2: float = -999.0
    defensive_dd: float = -999.0
    defensive_factor: float = 0.5
    shock_trades: int = 6
    shock_factor: float = 0.5
    loss_streak_trigger: int = 2
    boost_stake: float = 5.5
    boost_history: int = 50
    boost_min_signals: int = 4
    boost_requires_last10: bool = True
    profit_odds: float = 0.35


def base_stake(signals, params):
    if signals >= 4:
        return params.stake_4
    if signals == 3:
        return params.stake_3
    if signals == 2:
        return params.stake_2
    return 0.0


def balanced_score(profit, max_dd):
    return profit + max_dd * 0.6


def run_o15_backtest_params(data, params):
    state = O15State()
    profits = []
    stakes = []

    for row in data.itertuples(index=False):
        signals = row.signals
        stake = base_stake(signals, params)
        if stake == 0:
            continue

        drawdown = state.equity - state.peak

        if drawdown < params.dd_skip_t2 and signals == 2:
            state.profits.append(0)
            state.equity_history.append(state.equity)
            stakes.append(0)
            profits.append(0)
            continue

        if state.shock_mode > 0:
            stake *= params.shock_factor
            state.shock_mode -= 1

        if drawdown < params.defensive_dd:
            stake *= params.defensive_factor

        if len(state.equity_history) > params.boost_history:
            avg_equity = np.mean(state.equity_history[-params.boost_history:])
            last10 = state.profits[-10:] if len(state.profits) >= 10 else []
            last10_ok = sum(last10) > 0 if params.boost_requires_last10 else True

            if state.equity > avg_equity and last10_ok and signals >= params.boost_min_signals:
                stake = params.boost_stake

        if row.vinto:
            profit = stake * params.profit_odds
            state.loss_streak = 0
        else:
            profit = -stake
            state.loss_streak += 1

        if state.loss_streak >= params.loss_streak_trigger:
            state.shock_mode = params.shock_trades
            state.loss_streak = 0

        state.equity += profit
        state.peak = max(state.peak, state.equity)
        state.profits.append(profit)
        state.equity_history.append(state.equity)
        stakes.append(stake)
        profits.append(profit)

    if not profits:
        return {"profit": 0, "max_dd": 0, "trades": 0, "winrate": 0, "score": 0, "calmar": 0}

    equity = np.cumsum(profits)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    active = [s for s in stakes if s > 0]
    wins = [p for p, s in zip(profits, stakes) if s > 0 and p > 0]

    profit = float(sum(profits))
    max_dd = float(dd.min())
    trades = len(active)
    winrate = len(wins) / trades if trades else 0

    return {
        "profit": profit,
        "max_dd": max_dd,
        "trades": trades,
        "winrate": winrate,
        "score": balanced_score(profit, max_dd),
        "calmar": profit / abs(max_dd) if max_dd < 0 else profit,
    }


def prepare_o15_rows(df, patterns=None):
    data = _prepare_o15_data_legacy(df, patterns)
    data = data.sort_values(["date", "signals"]).reset_index(drop=True)
    return data


def random_params(rng, aggressive=False):
    if not aggressive:
        return O15Params(
            stake_4=rng.choice([4.0, 4.5, 5.0, 5.5, 6.0, 6.5]),
            stake_3=rng.choice([2.0, 2.5, 3.0, 3.5, 4.0]),
            stake_2=rng.choice([1.0, 1.2, 1.5, 1.8, 2.0]),
            shock_trades=rng.choice([4, 5, 6, 7, 8]),
            shock_factor=rng.choice([0.4, 0.5, 0.6]),
            loss_streak_trigger=rng.choice([2, 3]),
            boost_stake=rng.choice([4.5, 5.0, 5.5, 6.0, 6.5]),
            boost_history=rng.choice([30, 40, 50, 60, 70]),
            boost_min_signals=rng.choice([3, 4]),
            boost_requires_last10=rng.choice([True, False]),
            profit_odds=0.35,
        )

    return O15Params(
        stake_4=rng.choice([5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]),
        stake_3=rng.choice([3.0, 3.5, 4.0, 4.5, 5.0, 5.5]),
        stake_2=rng.choice([1.5, 2.0, 2.5, 3.0]),
        dd_skip_t2=rng.choice([-999, -6, -7, -8, -9, -10]),
        defensive_dd=rng.choice([-999, -8, -10, -12, -14, -15]),
        defensive_factor=rng.choice([0.4, 0.5, 0.6]),
        shock_trades=rng.choice([4, 5, 6, 7, 8]),
        shock_factor=rng.choice([0.4, 0.5, 0.6]),
        loss_streak_trigger=rng.choice([2, 3]),
        boost_stake=rng.choice([5.5, 6.0, 6.5, 7.0, 7.5, 8.0]),
        boost_history=rng.choice([30, 40, 50, 60]),
        boost_min_signals=rng.choice([3, 4]),
        boost_requires_last10=rng.choice([True, False]),
        profit_odds=0.35,
    )


def optimize_o15(df, patterns=None, iterations=3000, seed=42, aggressive=False, max_dd_limit=None):
    data = prepare_o15_rows(df, patterns)
    baseline = O15Params()
    baseline_result = run_o15_backtest_params(data, baseline)
    baseline_result["params"] = asdict(baseline)

    rng = random.Random(seed)
    results = []

    for _ in range(iterations):
        params = random_params(rng, aggressive=aggressive)
        metrics = run_o15_backtest_params(data, params)
        metrics["params"] = asdict(params)
        results.append(metrics)

    df_results = pd.DataFrame(results)
    if max_dd_limit is not None:
        df_results = df_results[df_results["max_dd"] >= max_dd_limit]
    df_results = df_results.sort_values("profit", ascending=False).reset_index(drop=True)
    return baseline_result, df_results


def format_params(params):
    last10 = "sì" if params["boost_requires_last10"] else "no"
    return (
        f"stake 4/3/2 = {params['stake_4']}/{params['stake_3']}/{params['stake_2']} | "
        f"shock {params['shock_trades']} x{params['shock_factor']} dopo {params['loss_streak_trigger']} loss | "
        f"boost {params['boost_stake']} (hist {params['boost_history']}, min sig {params['boost_min_signals']}, last10 {last10})"
    )
