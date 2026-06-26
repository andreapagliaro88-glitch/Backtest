# Sistema compound — crescita composta con bankroll in €
# Configura bankroll e risk in compound_config.py
# Uso: python compound_main.py
import os
import matplotlib.pyplot as plt
import pandas as pd
from compound_config import INITIAL_BANKROLL
from core.loader import load_data
from core.backtest import prepare_grouped
from core.compound_backtest import run_compound_backtest, print_compound_stats

OUTPUT_DIR = "output/compound"

df_raw = load_data()
df_grouped = prepare_grouped(df_raw)
os.makedirs(OUTPUT_DIR, exist_ok=True)

df_trades, ccs = run_compound_backtest(
    df_grouped, df_raw, initial_bankroll=INITIAL_BANKROLL
)
df_trades.to_csv(os.path.join(OUTPUT_DIR, "trades_compound.csv"), index=False)
print_compound_stats(df_trades, ccs)

if df_trades.empty:
    raise SystemExit(0)

active = df_trades[df_trades["stake_eur"] > 0].reset_index(drop=True)

plt.figure(figsize=(10, 5))
plt.plot(active.index, active["bankroll"])
plt.title("Equity Curve (€) - Compound")
plt.xlabel("Trade")
plt.ylabel("€")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "equity_compound.png"))
plt.close()

plt.figure(figsize=(10, 5))
plt.plot(active.index, active["dd_eur"])
plt.title("Drawdown (€) - Compound")
plt.xlabel("Trade")
plt.ylabel("€")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "drawdown_compound.png"))
plt.close()

plt.figure(figsize=(10, 5))
plt.plot(active.index, active["dd_pct"])
plt.title("Drawdown (%) - Compound")
plt.xlabel("Trade")
plt.ylabel("%")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "drawdown_pct_compound.png"))
plt.close()

monthly = df_trades.copy()
monthly["date"] = pd.to_datetime(monthly["date"])
monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit_eur"].sum()

plt.figure(figsize=(10, 5))
monthly_profit.plot(kind="bar")
plt.title("Profitto Mensile (€) - Compound")
plt.xlabel("Mese")
plt.ylabel("€")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "monthly_compound.png"))
plt.close()

plt.show()
