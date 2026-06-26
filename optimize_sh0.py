import pandas as pd

from core.loader import load_data
from core.sh0_combo_optimizer import optimize_sh0_combos
from core.sh0_loader import load_sh0_data
from core.sh0_optimizer import format_params, optimize_sh0

ITERATIONS = 3000

df_sh0 = load_sh0_data()
if df_sh0.empty:
    print("Nessun file in data/sh0/")
    raise SystemExit(1)

print("\n===== 0 SH COMBO OPTIMIZER =====")
combo_df = optimize_sh0_combos(df_sh0)
print(f"Combinazioni testate: {len(combo_df)}\n")

print("--- TOP 10 SCORE (profit + 0.6×DD) ---")
for i, row in combo_df.head(10).iterrows():
    print(f"\n#{i + 1} {row['combo']}")
    print(f"  Profit: {row['profit']:.2f} U | Max DD: {row['max_dd']:.2f} U | Score: {row['score']:.2f}")
    print(f"  Trade: {int(row['trades'])} | Winrate: {row['winrate'] * 100:.1f}%")

combo_df.to_csv("output/sh0_combo_optimization.csv", index=False)
print("\nSalvato: output/sh0_combo_optimization.csv")

best_combo = tuple(combo_df.iloc[0]["patterns"])
print(f"\n===== 0 SH PARAM OPTIMIZER (combo: {combo_df.iloc[0]['combo']}) =====")
baseline, results = optimize_sh0(df_sh0, patterns=best_combo, iterations=ITERATIONS)

print("\n--- BASELINE ---")
print(f"  Profit: {baseline['profit']:.2f} U | DD: {baseline['max_dd']:.2f} U | Score: {baseline['score']:.2f}")
print(f"  {format_params(baseline['params'])}")

print("\n--- TOP 5 STAKE ---")
for i, row in results.head(5).iterrows():
    print(f"\n#{i + 1}")
    print(f"  Profit: {row['profit']:.2f} U | DD: {row['max_dd']:.2f} U | Score: {row['score']:.2f}")
    print(f"  {format_params(row['params'])}")

results.to_csv("output/sh0_optimization.csv", index=False)
print("\nSalvato: output/sh0_optimization.csv")
