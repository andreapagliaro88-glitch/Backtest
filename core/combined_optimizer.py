from dataclasses import asdict
import itertools
import random

import pandas as pd

from core.combined_config import CombinedParams
from core.strategy_engine import prepare_combined_context, run_combined_metrics


PRIORITY_ORDERS = list(itertools.permutations(["HT", "O15", "O25"]))


def balanced_score(profit, max_dd):
    return profit + max_dd * 0.6


def score_metrics(metrics):
    profit = metrics["profit"]
    max_dd = metrics["max_dd"]
    metrics["score"] = balanced_score(profit, max_dd)
    metrics["calmar"] = profit / abs(max_dd) if max_dd < 0 else profit
    return metrics


def random_params(rng):
    return CombinedParams(
        priority_dd_threshold=rng.choice([-5, -7, -8, -10, -12, -15, -18]),
        priority_normal=rng.choice(PRIORITY_ORDERS),
        priority_crisis=rng.choice(PRIORITY_ORDERS),
        skip_o25_below_dd=rng.choice([None, -8, -10, -12, -15, -18]),
        skip_o15_below_dd=rng.choice([None, -10, -12, -15, -20]),
        full_stop_dd=rng.choice([None, -16, -20, -25, -30]),
        full_stop_trades=rng.choice([0, 5, 10, 15]),
    )


def optimize_combined(df_grouped, df_raw, iterations=800, seed=42):
    context = prepare_combined_context(df_grouped, df_raw)
    baseline = CombinedParams()
    baseline_result = score_metrics(run_combined_metrics(df_grouped, df_raw, baseline, context))
    baseline_result["params"] = asdict(baseline)

    rng = random.Random(seed)
    results = []
    for _ in range(iterations):
        params = random_params(rng)
        metrics = score_metrics(run_combined_metrics(df_grouped, df_raw, params, context))
        metrics["params"] = asdict(params)
        results.append(metrics)

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("score", ascending=False).reset_index(drop=True)
    return baseline_result, df_results


def format_params(params):
    normal = params["priority_normal"]
    crisis = params["priority_crisis"]
    if isinstance(normal, str):
        normal = tuple(x.strip().strip("'") for x in normal.strip("()").split(","))
    if isinstance(crisis, str):
        crisis = tuple(x.strip().strip("'") for x in crisis.strip("()").split(","))
    return (
        f"soglia priorità @ {params['priority_dd_threshold']} | "
        f"normale {'>'.join(normal)} | "
        f"crisi {'>'.join(crisis)} | "
        f"skip O25<{params['skip_o25_below_dd']} O15<{params['skip_o15_below_dd']} | "
        f"full stop @ {params['full_stop_dd']} per {params['full_stop_trades']} trade"
    )
