import pandas as pd
from core.loader import load_data
from core.ht_optimizer import format_params, optimize_ht

ITERATIONS = 3000

df_raw = load_data()
baseline, results = optimize_ht(df_raw, iterations=ITERATIONS)

print("\n===== HT OPTIMIZER =====")
print(f"Iterazioni testate: {ITERATIONS}\n")

print("--- BASELINE (attuale) ---")
print(f"  Profit:   {baseline['profit']:.2f} U")
print(f"  Max DD:   {baseline['max_dd']:.2f} U")
print(f"  Score:    {baseline['score']:.2f}")
print(f"  Calmar:   {baseline['calmar']:.2f}")
print(f"  Winrate:  {baseline['winrate'] * 100:.1f}%")
print(f"  {format_params(baseline['params'])}")

print("\n--- TOP 10 EQUILIBRIO PROFIT / DD ---")
for i, row in results.head(10).iterrows():
    print(f"\n#{i + 1}")
    print(f"  Profit:   {row['profit']:.2f} U")
    print(f"  Max DD:   {row['max_dd']:.2f} U")
    print(f"  Score:    {row['score']:.2f}")
    print(f"  Calmar:   {row['calmar']:.2f}")
    print(f"  Trade:    {int(row['trades'])}")
    print(f"  Winrate:  {row['winrate'] * 100:.1f}%")
    print(f"  {format_params(row['params'])}")

best = results.iloc[0]
improvement = best["score"] - baseline["score"]
print(f"\n--- MIGLIORAMENTO SCORE vs baseline: {improvement:+.2f} ---")

results.to_csv("output/ht_optimization.csv", index=False)
print("\nRisultati completi salvati in output/ht_optimization.csv")
