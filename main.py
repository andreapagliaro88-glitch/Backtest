import os
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import matplotlib.pyplot as plt
from core.loader import load_data
from core.backtest import prepare_grouped, run_backtest
from core.ht_backtest import run_ht_backtest, print_ht_stats
from core.o15_backtest import run_o15_backtest, print_o15_stats
from core.o25_backtest import run_o25_backtest, print_o25_stats
from core.sh0_backtest import run_sh0_backtest, print_sh0_stats
from core.sh0_loader import load_sh0_data

df_raw = load_data()
df_grouped = prepare_grouped(df_raw)
os.makedirs("output", exist_ok=True)

plt.figure(figsize=(10, 6))

df_combined = run_backtest(df_grouped, df_raw=df_raw)
df_combined.to_csv("output/trades.csv", index=False)

print("\ncombined")
print(f"  Trades: {len(df_combined[df_combined['stake'] > 0]) if not df_combined.empty else 0}")
print(f"  Profit: {df_combined['profit'].sum():.2f}" if not df_combined.empty else "  Profit: 0.00")
print(f"  Max DD: {df_combined['dd'].min():.2f}" if not df_combined.empty else "  Max DD: 0.00")
print("  Output: output/trades.csv")

if not df_combined.empty:
    plt.plot(df_combined["equity"], label="combined")

    plt.figure(figsize=(10, 4))
    plt.plot(df_combined.index, df_combined["equity"])
    plt.title("Equity Curve - Combined")
    plt.xlabel("Trade")
    plt.ylabel("U")
    plt.tight_layout()
    plt.savefig("output/equity_combined.png")
    plt.close()

    monthly = df_combined.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit"].sum()

    plt.figure(figsize=(10, 5))
    monthly_profit.plot(kind="bar")
    plt.title("Profitto Mensile Combined (U)")
    plt.xlabel("Mese")
    plt.ylabel("U")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("output/monthly_combined.png")
    plt.close()

strategies = [
    ("HT", run_ht_backtest, print_ht_stats, "output/trades_ht.csv"),
    ("O15", run_o15_backtest, print_o15_stats, "output/trades_o15.csv"),
    ("O25", run_o25_backtest, print_o25_stats, "output/trades_o25.csv"),
]

df_sh0 = load_sh0_data()
if not df_sh0.empty:
    strategies.append(("SH0", lambda _: run_sh0_backtest(df_sh0), print_sh0_stats, "output/trades_sh0.csv"))

results = {}
for label, run_fn, print_fn, output_path in strategies:
    df_trades = run_fn(df_raw)
    df_trades.to_csv(output_path, index=False)
    print_fn(df_trades)
    results[label] = df_trades

    if not df_trades.empty:
        plt.plot(df_trades["equity"], label=label)

plt.title("Equity Curve")
plt.legend()
plt.tight_layout()
plt.savefig("output/equity_curve.png")
plt.close()

for label, df_trades in results.items():
    if df_trades.empty:
        continue

    plt.figure(figsize=(10, 4))
    plt.plot(df_trades.index, df_trades["equity"])
    plt.title(f"Equity Curve - {label}")
    plt.xlabel("Trade")
    plt.ylabel("U")
    plt.tight_layout()
    plt.savefig(f"output/equity_{label.lower()}.png")
    plt.close()

    monthly = df_trades.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit"].sum()

    plt.figure(figsize=(10, 5))
    monthly_profit.plot(kind="bar")
    plt.title(f"Profitto Mensile {label} (U)")
    plt.xlabel("Mese")
    plt.ylabel("U")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"output/monthly_{label.lower()}.png")
    plt.close()

plt.show()
