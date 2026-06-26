import ast
import pandas as pd
from core.backtest import prepare_grouped
from core.combined_config import CombinedParams
from core.combined_optimizer import format_params, optimize_combined
from core.loader import load_data

ITERATIONS = 800

df_raw = load_data()
df_grouped = prepare_grouped(df_raw)
baseline, results = optimize_combined(df_grouped, df_raw, iterations=ITERATIONS)

print("\n===== COMBINED OPTIMIZER =====")
print(f"Iterazioni: {ITERATIONS}\n")

print("--- BASELINE (attuale) ---")
print(f"  Profit:   {baseline['profit']:.2f} U")
print(f"  Max DD:   {baseline['max_dd']:.2f} U")
print(f"  Score:    {baseline['score']:.2f}")
print(f"  Trade:    {baseline['trades']} (HT {baseline['ht_trades']} | O15 {baseline['o15_trades']} | O25 {baseline['o25_trades']})")
print(f"  {format_params(baseline['params'])}")

print("\n--- TOP 10 ---")
for i, row in results.head(10).iterrows():
    print(f"\n#{i + 1}")
    print(f"  Profit:   {row['profit']:.2f} U")
    print(f"  Max DD:   {row['max_dd']:.2f} U")
    print(f"  Score:    {row['score']:.2f}")
    print(f"  Calmar:   {row['calmar']:.2f}")
    print(f"  Trade:    {int(row['trades'])} (HT {int(row['ht_trades'])} | O15 {int(row['o15_trades'])} | O25 {int(row['o25_trades'])})")
    print(f"  Winrate:  {row['winrate'] * 100:.1f}%")
    print(f"  {format_params(row['params'])}")

best = results.iloc[0]
print(f"\n--- MIGLIORAMENTO SCORE: {best['score'] - baseline['score']:+.2f} ---")

results.to_csv("output/combined_optimization.csv", index=False)
print("Salvato: output/combined_optimization.csv")
