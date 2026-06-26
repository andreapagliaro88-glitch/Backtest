import os

import pandas as pd

from compound_config import INITIAL_BANKROLL, UNIT_TIER_PHASES, phase_for_unit_eur
from core.backtest import prepare_grouped
from core.compound_backtest import run_compound_backtest
from core.compound_runner import run_compound_on_trades
from core.loader import load_data
from core.strategy_trades import iter_ht_trades, iter_o15_trades, iter_o25_trades

RISK_LABELS = {
    "normal": "Normale",
    "reduce_25": "Riduzione -25%",
    "reduce_50": "Riduzione -50%",
    "stop": "Stop attivo",
    "stop_triggered": "Stop attivato",
}

EXPORTS = [
    {
        "label": "Combinata",
        "filename": "giocate_combinata.xlsx",
        "source": "combined",
    },
    {
        "label": "HT",
        "filename": "giocate_ht.xlsx",
        "source": "ht",
    },
    {
        "label": "Over 1.5",
        "filename": "giocate_o15.xlsx",
        "source": "o15",
    },
    {
        "label": "Over 2.5",
        "filename": "giocate_o25.xlsx",
        "source": "o25",
    },
]


def _load_compound_df(source, df_raw, df_grouped):
    if source == "combined":
        return run_compound_backtest(df_grouped, df_raw, INITIAL_BANKROLL)
    iterators = {
        "ht": iter_ht_trades,
        "o15": iter_o15_trades,
        "o25": iter_o25_trades,
    }
    return run_compound_on_trades(iterators[source](df_raw), INITIAL_BANKROLL)


def format_trades_df(df):
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["trade_n"] = range(1, len(df) + 1)
    df["esito"] = df["vinto"].map({True: "Vinto", False: "Perso", 0: "Perso", 1: "Vinto"})
    df.loc[df["stake_eur"] == 0, "esito"] = "Saltato"
    if "risk_mode" in df.columns:
        df["modalita"] = df["risk_mode"].map(RISK_LABELS).fillna(df["risk_mode"])
    else:
        df["modalita"] = "CCS"
    df["fase"] = df["unit_eur"].apply(phase_for_unit_eur)

    cols = [
        "trade_n", "date", "system", "esito", "fase",
        "stake_u", "unit_eur", "stake_eur", "profit_eur",
        "bankroll", "peak_eur", "dd_eur", "dd_pct", "modalita",
    ]
    if "signals" in df.columns:
        cols.insert(3, "signals")
    if "equity_u" in df.columns:
        cols.append("equity_u")
    if "equity_eur" in df.columns:
        cols.append("equity_eur")

    rename = {
        "trade_n": "N°",
        "date": "Data",
        "system": "Strategia",
        "signals": "Segnali",
        "esito": "Esito",
        "fase": "Fase",
        "stake_u": "Stake (U)",
        "unit_eur": "Valore 1U (€)",
        "stake_eur": "Stake (€)",
        "profit_eur": "Profit/Loss (€)",
        "bankroll": "Bankroll (€)",
        "peak_eur": "Peak (€)",
        "dd_eur": "Drawdown (€)",
        "dd_pct": "Drawdown (%)",
        "modalita": "Modalità rischio",
        "equity_u": "Equity strategia (U)",
        "equity_eur": "Equity totale (€)",
    }
    return df[[c for c in cols if c in df.columns]].rename(columns=rename)


def build_summary_df(df_trades, ccs, label):
    active = df_trades[df_trades["Stake (€)"] > 0] if "Stake (€)" in df_trades.columns else df_trades
    wins = (active["Profit/Loss (€)"] > 0).sum() if not active.empty else 0
    losses = (active["Profit/Loss (€)"] < 0).sum() if not active.empty else 0
    total = len(active)

    if hasattr(ccs, "summary"):
        s = ccs.summary()
        initial = s["initial_bankroll"]
        final = s["final_bankroll"]
        profit = s["total_profit_eur"]
        roi = s["roi_pct"]
        max_dd_eur = s["max_dd_eur"]
        max_dd_pct = s["max_dd_pct"]
        n_withdrawals = s["n_withdrawals"]
        withdrawn = s["total_withdrawn"]
    else:
        initial = ccs.initial
        final = ccs.bankroll
        profit = final - initial
        roi = ccs.roi_pct
        max_dd_eur = df_trades["Drawdown (€)"].min() if "Drawdown (€)" in df_trades.columns else 0
        max_dd_pct = df_trades["Drawdown (%)"].min() if "Drawdown (%)" in df_trades.columns else 0
        n_withdrawals = 0
        withdrawn = 0

    equity_u_final = 0
    if "Equity strategia (U)" in df_trades.columns and not df_trades.empty:
        equity_u_final = df_trades["Equity strategia (U)"].iloc[-1]

    metrics = [
        "Strategia",
        "Bankroll iniziale (€)",
        "Bankroll finale (€)",
        "Profit totale (€)",
        "ROI",
        "Prelievi (n)",
        "Capitale prelevato (€)",
        "Trade totali",
        "Trade attivi",
        "Trade saltati/bloccati",
        "Vinte",
        "Perse",
        "Winrate",
        "Max drawdown (€)",
        "Max drawdown (%)",
        "Stake medio (€)",
    ]
    values = [
        label,
        round(initial, 2),
        round(final, 2),
        round(profit, 2),
        f"{roi:.2f}%",
        n_withdrawals,
        round(withdrawn, 2),
        len(df_trades),
        total,
        len(df_trades) - total,
        wins,
        losses,
        f"{wins / total * 100:.2f}%" if total else "0%",
        round(max_dd_eur, 2),
        round(max_dd_pct, 2),
        round(active["Stake (€)"].mean(), 2) if total else 0,
    ]
    if equity_u_final:
        metrics.append("Equity strategia finale (U)")
        values.append(round(equity_u_final, 2))

    return pd.DataFrame({"Metrica": metrics, "Valore": values})


def build_tiers_df():
    rows = []
    for phase, tiers in UNIT_TIER_PHASES:
        for threshold, unit_eur in tiers:
            rows.append({
                "Fase": phase,
                "Bankroll minimo (€)": f"≥ {threshold}",
                "Valore 1U (€)": unit_eur,
            })
    rows.append({"Fase": "—", "Bankroll minimo (€)": "< 150", "Valore 1U (€)": "bankroll / 50"})
    return pd.DataFrame(rows)


def write_excel(path, df_trades, df_summary, df_tiers):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_trades.to_excel(writer, sheet_name="Giocate", index=False)
        df_summary.to_excel(writer, sheet_name="Riepilogo", index=False)
        df_tiers.to_excel(writer, sheet_name="Scaglioni 1U", index=False)

        ws = writer.sheets["Giocate"]
        ws.column_dimensions["B"].width = 20
        for col in "CDEFGHIJKLMNO":
            ws.column_dimensions[col].width = 15

        ws = writer.sheets["Riepilogo"]
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 18


def export_all():
    os.makedirs("output", exist_ok=True)
    df_raw = load_data()
    df_grouped = prepare_grouped(df_raw)
    df_tiers = build_tiers_df()

    for spec in EXPORTS:
        raw_df, bankroll = _load_compound_df(spec["source"], df_raw, df_grouped)
        df_trades = format_trades_df(raw_df)
        if df_trades.empty:
            print(f"  {spec['label']}: nessuna giocata, saltato")
            continue

        path = os.path.join("output", spec["filename"])
        df_summary = build_summary_df(df_trades, bankroll, spec["label"])
        write_excel(path, df_trades, df_summary, df_tiers)

        profit = bankroll.bankroll - bankroll.initial
        print(
            f"  {spec['label']}: {len(df_trades)} righe -> {path} | "
            f"{bankroll.initial:.0f} € -> {bankroll.bankroll:.2f} € (+{profit:.2f} €)"
        )


if __name__ == "__main__":
    print("Export Excel (scaglioni PRO, partenza 150 € / 1U = 3 €)\n")
    export_all()
