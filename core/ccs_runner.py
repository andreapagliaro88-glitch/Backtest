"""Esegue backtest compound con Controlled Compounding System."""
from __future__ import annotations

import pandas as pd

from compound_config import INITIAL_BANKROLL
from core.tier_config import profit_odds_for
from core.controlled_compounding import ControlledCompounding
from core.strategy_engine import iter_combined_trades


def ccs_to_dict(ccs: ControlledCompounding) -> dict:
    """Serializza CCS per cache Streamlit (no oggetti custom)."""
    return {
        "summary": ccs.summary(),
        "withdrawals": ccs.withdrawals_dataframe_rows(),
        "tiers": ccs.tiers_dataframe_rows(),
    }


def trades_to_ccs_inputs(trades) -> list[dict]:
    rows = []
    for t in trades:
        if t.get("skipped"):
            continue
        system = t["system"]
        rows.append({
            "date": t.get("date"),
            "system": system,
            "vinto": bool(t["vinto"]),
            "profit_odds": profit_odds_for(system),
            "stake_u": float(t.get("stake_u") or 1.0),
            "skipped": False,
        })
    return rows


def unit_backtest_df_to_ccs_inputs(df_trades: pd.DataFrame) -> list[dict]:
    """Converte output backtest in U (stake>0 = ingresso) in input CCS."""
    rows = []
    if df_trades.empty:
        return rows
    for _, row in df_trades.iterrows():
        stake = float(row.get("stake") or 0)
        if stake <= 0:
            continue
        system = str(row["system"])
        if "vinto" in row.index and pd.notna(row["vinto"]):
            vinto = bool(row["vinto"])
        else:
            vinto = float(row.get("profit") or 0) > 0
        rows.append({
            "date": row.get("date"),
            "system": system,
            "vinto": vinto,
            "profit_odds": profit_odds_for(system),
            "stake_u": stake,
            "skipped": False,
        })
    return rows


def run_ccs_on_backtest_df(
    df_trades: pd.DataFrame,
    initial_bankroll: float = INITIAL_BANKROLL,
) -> tuple[pd.DataFrame, ControlledCompounding]:
    """Applica CCS sui trade del backtest unità (ingressi da stake>0)."""
    return run_ccs_on_trades(unit_backtest_df_to_ccs_inputs(df_trades), initial_bankroll)


def enrich_trades_with_eur(df_trades: pd.DataFrame, df_ccs: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge colonne € ai trade unità (inclusi skip)."""
    if df_trades.empty:
        return pd.DataFrame()

    df = df_trades.copy()
    df["ingresso"] = df["stake"].apply(lambda s: "SÌ" if float(s or 0) > 0 else "SKIP")
    df["valore_1u"] = 0.0
    df["stake_eur"] = 0.0
    df["profit_eur"] = pd.NA
    df["bankroll_eur"] = pd.NA
    df["dd_eur"] = pd.NA
    df["esito"] = ""
    if "tier_label" not in df.columns and "tier" in df.columns:
        from core.tier_engine import tier_label
        df["tier_label"] = df["tier"].apply(lambda t: tier_label(int(t)) if t and int(t) > 0 else "SKIP")
    if "patterns_str" not in df.columns and "patterns" in df.columns:
        df["patterns_str"] = df["patterns"]

    ccs = df_ccs.reset_index(drop=True)
    ccs_idx = 0
    for i, row in df.iterrows():
        if float(row.get("stake") or 0) <= 0:
            continue
        if ccs_idx >= len(ccs):
            break
        r = ccs.iloc[ccs_idx]
        df.at[i, "valore_1u"] = r["unit_eur"]
        df.at[i, "stake_eur"] = r["stake_eur"]
        df.at[i, "profit_eur"] = r["profit_eur"]
        df.at[i, "bankroll_eur"] = r["bankroll"]
        df.at[i, "dd_eur"] = r["dd_eur"]
        pe = float(r["profit_eur"])
        df.at[i, "esito"] = "VINTO" if pe > 0 else "PERSO"
        ccs_idx += 1

    return df


def format_trades_eur_display(df: pd.DataFrame) -> pd.DataFrame:
    """Tabella trade formattata per UI (€)."""
    out = df.copy()
    if "patterns_str" in out.columns:
        out["Pattern"] = out["patterns_str"].fillna("").astype(str)
    elif "patterns" in out.columns:
        out["Pattern"] = out["patterns"].fillna("").astype(str)
    else:
        out["Pattern"] = ""

    col_map = {
        "date": "Data",
        "system": "Strategia",
        "tier_label": "Tier",
        "stake": "Stake (U)",
        "n_engines": "Engine",
        "ingresso": "Ingresso",
        "valore_1u": "1U (€)",
        "stake_eur": "Stake CCS (€)",
        "profit_eur": "Profitto (€)",
        "bankroll_eur": "Bankroll (€)",
        "dd_eur": "DD (€)",
        "esito": "Esito",
    }
    order = [
        "date", "system", "tier_label", "Pattern", "n_engines", "stake", "ingresso",
        "valore_1u", "stake_eur", "profit_eur", "bankroll_eur", "dd_eur", "esito",
    ]
    rename = {k: v for k, v in col_map.items() if k in out.columns}
    cols = [c for c in order if c in out.columns or c == "Pattern"]
    return out[cols].rename(columns=rename)


def run_ccs_on_trades(trades, initial_bankroll: float = INITIAL_BANKROLL) -> tuple[pd.DataFrame, ControlledCompounding]:
    ccs = ControlledCompounding(initial_bankroll)

    for t in trades:
        if t.get("skipped"):
            continue
        system = t["system"]
        odds = profit_odds_for(system)
        ccs.settle_trade(
            vinto=bool(t["vinto"]),
            profit_odds=odds,
            date=t.get("date"),
            system=system,
            stake_u=float(t.get("stake_u") or 1.0),
        )

    records = []
    for tr in ccs.trades:
        if tr.stake_eur <= 0:
            continue
        records.append({
            "date": tr.date,
            "system": tr.system,
            "stake_u": tr.stake_u,
            "unit_eur": tr.unit_eur,
            "stake_eur": tr.stake_eur,
            "profit_eur": tr.profit_eur,
            "bankroll": tr.bankroll_eur,
            "equity_eur": tr.equity_eur,
            "peak_eur": tr.peak_eur,
            "dd_eur": tr.dd_eur,
            "dd_pct": tr.dd_pct,
            "tier_threshold": tr.tier_threshold,
            "withdrawn": tr.withdrawn,
            "vinto": tr.vinto,
        })

    return pd.DataFrame(records), ccs


def run_ccs_backtest(df_grouped, df_raw, initial_bankroll: float | None = None) -> tuple[pd.DataFrame, ControlledCompounding]:
    if initial_bankroll is None:
        initial_bankroll = INITIAL_BANKROLL
    trades = list(iter_combined_trades(df_grouped, df_raw))
    return run_ccs_on_trades(trades, initial_bankroll)
