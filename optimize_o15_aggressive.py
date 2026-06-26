import ast
import pandas as pd
from core.loader import load_data
from core.o15_backtest import run_o15_backtest
from core.o15_optimizer import format_params, optimize_o15

CURRENT_PROFIT = 224.32
CURRENT_DD = -8.63
MAX_DD = -15
ITERATIONS = 8000

df_raw = load_data()
_, results = optimize_o15(
    df_raw,
    iterations=ITERATIONS,
    aggressive=True,
    max_dd_limit=MAX_DD,
)

print("\n===== O15 AGGRESSIVE (DD <= 15U) =====")
print(f"Attuale: profit={CURRENT_PROFIT} dd={CURRENT_DD}")
print(f"Iterazioni: {ITERATIONS}\n")

if results.empty:
    print("Nessuna config trovata entro il limite DD.")
    raise SystemExit(1)

for i, row in results.head(10).iterrows():
    print(
        f"#{i+1} profit={row['profit']:.1f} dd={row['max_dd']:.1f} "
        f"trades={int(row['trades'])} wr={row['winrate']*100:.1f}% "
        f"(+{row['profit']-CURRENT_PROFIT:.1f} U vs attuale)"
    )
    print(f"    {format_params(row['params'])}")

best = results.iloc[0]
print(f"\nMigliore: profit={best['profit']:.2f} dd={best['max_dd']:.2f}")
print(f"Params: {best['params']}")

if best["profit"] <= CURRENT_PROFIT + 5:
    print("\nNessun miglioramento significativo trovato oltre la config attuale.")
else:
    print(f"\nMiglioramento profit: +{best['profit'] - CURRENT_PROFIT:.2f} U")

results.to_csv("output/o15_optimization_aggressive.csv", index=False)
