import ast
import random
from dataclasses import asdict

import pandas as pd

from core.backtest import prepare_grouped
from core.combined_config import CombinedParams
from core.combined_optimizer import format_params, score_metrics
from core.loader import load_data
from core.strategy_engine import prepare_combined_context, run_combined_metrics

ITERATIONS = 3000
DD_MIN = -18.0
DD_MAX = -15.0


def defensive_params(rng):
    return CombinedParams(
        priority_dd_threshold=rng.choice([-5, -7, -8, -10, -12, -15, -18]),
        priority_normal=rng.choice([
            ("HT", "O15", "O25"),
            ("HT", "O25", "O15"),
            ("O15", "HT", "O25"),
        ]),
        priority_crisis=rng.choice([
            ("O15", "HT", "O25"),
            ("O15", "O25", "HT"),
            ("HT", "O15", "O25"),
            ("O25", "O15", "HT"),
        ]),
        skip_o25_below_dd=rng.choice([-8, -10, -12, -15, -18]),
        skip_o15_below_dd=rng.choice([-10, -12, -15, -18, -20]),
        full_stop_dd=rng.choice([-14, -15, -16, -18]),
        full_stop_trades=rng.choice([5, 10, 15, 20]),
    )


df_raw = load_data()
df_grouped = prepare_grouped(df_raw)
context = prepare_combined_context(df_grouped, df_raw)

rng = random.Random(99)
results = []
for _ in range(ITERATIONS):
    params = defensive_params(rng)
    metrics = score_metrics(run_combined_metrics(df_grouped, df_raw, params, context))
    if DD_MIN <= metrics["max_dd"] <= DD_MAX:
        metrics["params"] = asdict(params)
        results.append(metrics)

df_old = pd.read_csv("output/combined_optimization.csv")
df_old["max_dd"] = pd.to_numeric(df_old["max_dd"])
old_best = df_old[(df_old["max_dd"] >= DD_MIN) & (df_old["max_dd"] <= DD_MAX)].sort_values(
    "profit", ascending=False
).iloc[0]

print(f"\n===== DD TARGET {DD_MIN} .. {DD_MAX} U =====")
print(f"Iterazioni difensive: {ITERATIONS}")
print(f"Candidati validi: {len(results)}")

if results:
    df_new = pd.DataFrame(results).sort_values("profit", ascending=False).reset_index(drop=True)
    best = df_new.iloc[0]
    print("\n--- MIGLIOR NUOVO ---")
    print(f"  Profit: {best['profit']:.2f} U")
    print(f"  Max DD: {best['max_dd']:.2f} U")
    print(f"  Trade:  {int(best['trades'])}")
    print(f"  {format_params(best['params'])}")
    df_new.to_csv("output/combined_optimization_dd.csv", index=False)
else:
    best = None
    print("Nessun candidato nuovo nel range DD")

print("\n--- MIGLIOR PRECEDENTE ---")
print(f"  Profit: {old_best['profit']:.2f} U")
print(f"  Max DD: {old_best['max_dd']:.2f} U")
p = old_best["params"]
if isinstance(p, str):
    p = ast.literal_eval(p.replace("nan", "None"))
print(f"  {format_params(p)}")

if best is not None and best["profit"] > old_best["profit"]:
    winner = best
    print("\n=> Vincitore: NUOVO")
else:
    winner_params = p
    winner = {"profit": old_best["profit"], "max_dd": old_best["max_dd"], "params": winner_params}
    print("\n=> Vincitore: PRECEDENTE")

print("\n--- CONFIG FINALE ---")
print(winner["params"])
