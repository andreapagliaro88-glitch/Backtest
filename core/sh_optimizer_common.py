"""Ottimizzazione parametri Composta Controllata per 0/1/2 SH."""
from __future__ import annotations

import random
from dataclasses import asdict

import pandas as pd

from core.sh_common import SHControlledParams, prepare_sh_data, run_sh_backtest_params


def format_sh_params(params: dict) -> str:
    return (
        f"quota 1.3 (+0.3U / -1U per trade) | stake fisso 1U | "
        f"stop DD {params.get('full_stop_dd', -18)} | "
        f"pausa {params.get('shock_trades', 5)} trade dopo {params.get('loss_streak_trigger', 3)} loss"
    )


def optimize_sh_system(
    df,
    system: str,
    patterns=None,
    iterations: int = 3000,
    seed: int = 42,
    max_dd_limit: float | None = -18.0,
) -> tuple[dict, pd.DataFrame]:
    data = prepare_sh_data(df, system, patterns)
    data = data.sort_values(["date", "signals"]).reset_index(drop=True)

    baseline = SHControlledParams()
    baseline_result = run_sh_backtest_params(data, system, baseline)
    baseline_result["params"] = asdict(baseline)

    rng = random.Random(seed)
    results = []
    for _ in range(iterations):
        params = SHControlledParams(
            shock_trades=rng.choice([3, 4, 5, 6, 7, 8]),
            loss_streak_trigger=rng.choice([2, 3, 4, 5]),
            full_stop_dd=rng.choice([-16.0, -18.0, -20.0, -22.0]),
        )
        metrics = run_sh_backtest_params(data, system, params)
        metrics["params"] = asdict(params)
        results.append(metrics)

    df_results = pd.DataFrame(results)
    if max_dd_limit is not None:
        df_results = df_results[df_results["max_dd"] >= max_dd_limit]
    df_results = df_results.sort_values("score", ascending=False).reset_index(drop=True)
    return baseline_result, df_results
