from dataclasses import dataclass, asdict
import random

import numpy as np
import pandas as pd

from core.ht_backtest import HTState, prepare_ht_data


@dataclass
class HTParams:
    stake_4: float = 4.0
    stake_3: float = 2.2
    stake_2: float = 0.7
    dd_skip_t2: float = -7.0
    defensive_dd: float = -12.0
    defensive_factor: float = 0.5
    boost_stake: float = 4.5
    boost_history: int = 50
    boost_min_signals: int = 4
    profit_odds: float = 0.4


def base_stake(signals, params):
    if signals >= 4:
        return params.stake_4
    if signals == 3:
        return params.stake_3
    if signals == 2:
        return params.stake_2
    return 0.0


def run_ht_backtest_params(data, params):
    state = HTState()
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

        if drawdown < params.defensive_dd:
            stake *= params.defensive_factor

        if len(state.equity_history) > params.boost_history:
            avg_equity = np.mean(state.equity_history[-params.boost_history:])
            if state.equity > avg_equity and signals >= params.boost_min_signals:
                stake = params.boost_stake

        if row.vinto:
            profit = stake * params.profit_odds
        else:
            profit = -stake

        state.equity += profit
        state.peak = max(state.peak, state.equity)
        state.profits.append(profit)
        state.equity_history.append(state.equity)
        stakes.append(stake)
        profits.append(profit)

    if not profits:
        return {"profit": 0, "max_dd": 0, "trades": 0, "winrate": 0, "score": 0}

    equity = np.cumsum(profits)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    active = [s for s in stakes if s > 0]
    wins = [p for p, s in zip(profits, stakes) if s > 0 and p > 0]

    profit = float(sum(profits))
    max_dd = float(dd.min())
    trades = len(active)
    winrate = len(wins) / trades if trades else 0
    score = balanced_score(profit, max_dd)

    return {
        "profit": profit,
        "max_dd": max_dd,
        "trades": trades,
        "winrate": winrate,
        "score": score,
        "calmar": profit / abs(max_dd) if max_dd < 0 else profit,
    }


def balanced_score(profit, max_dd):
    # Equilibrio profit/drawdown: premia profitto, penalizza DD profondo
    return profit + max_dd * 0.6


def prepare_ht_rows(df, patterns=None):
    data = prepare_ht_data(df, patterns)
    data = data.sort_values(["date", "signals"]).reset_index(drop=True)
    return data


def random_params(rng):
    return HTParams(
        stake_4=rng.choice([3.0, 3.5, 4.0, 4.5, 5.0, 5.5]),
        stake_3=rng.choice([1.5, 1.8, 2.0, 2.2, 2.5, 3.0]),
        stake_2=rng.choice([0.5, 0.7, 1.0, 1.2]),
        dd_skip_t2=rng.choice([-5, -6, -7, -8, -9, -10]),
        defensive_dd=rng.choice([-10, -11, -12, -14, -16, -18]),
        defensive_factor=rng.choice([0.4, 0.5, 0.6, 0.7]),
        boost_stake=rng.choice([3.5, 4.0, 4.5, 5.0, 5.5]),
        boost_history=rng.choice([30, 40, 50, 60, 70]),
        boost_min_signals=rng.choice([3, 4]),
        profit_odds=0.4,
    )


def optimize_ht(df, patterns=None, iterations=3000, seed=42):
    data = prepare_ht_rows(df, patterns)
    baseline = HTParams()
    baseline_result = run_ht_backtest_params(data, baseline)
    baseline_result["params"] = asdict(baseline)

    rng = random.Random(seed)
    results = []

    for _ in range(iterations):
        params = random_params(rng)
        metrics = run_ht_backtest_params(data, params)
        metrics["params"] = asdict(params)
        results.append(metrics)

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("score", ascending=False).reset_index(drop=True)
    return baseline_result, df_results


def format_params(params):
    return (
        f"stake 4/3/2 = {params['stake_4']}/{params['stake_3']}/{params['stake_2']} | "
        f"skip T2 @ {params['dd_skip_t2']} | "
        f"difesa @ {params['defensive_dd']} x{params['defensive_factor']} | "
        f"boost {params['boost_stake']} (hist {params['boost_history']}, min sig {params['boost_min_signals']})"
    )
