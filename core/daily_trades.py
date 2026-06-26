"""Trade giornaliero — strategia combinata + stake compound."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

import pandas as pd

from compound_config import INITIAL_BANKROLL, PROFIT_ODDS, phase_for_unit_eur
from core.combined_config import CombinedParams
from core.controlled_compounding import ControlledCompounding
from core.ht_backtest import HTState, ht_base_stake, process_ht_trade
from core.o15_backtest import O15State, o15_base_stake, process_o15_trade
from core.o25_backtest import O25State, o25_base_stake, process_o25_trade
from core.sh0_backtest import SH0State, preview_sh_stake, sh0_base_stake, process_sh0_trade
from core.strategy_engine import StrategyState

JOURNAL_DIR = os.path.join("data", "daily_trades")
JOURNAL_PATH = os.path.join(JOURNAL_DIR, "journal.csv")
STATE_PATH = os.path.join(JOURNAL_DIR, "state.json")
TEMPLATE_PATH = os.path.join(JOURNAL_DIR, "template_giornata.xlsx")

JOURNAL_COLUMNS = [
    "trade_id", "data", "ora", "campionato", "partita", "match_id",
    "strategia", "segnali", "signals_ht", "signals_o15", "signals_o25", "signals_sh0",
    "stake_u", "valore_1u", "stake_eur", "fase",
    "modalita_rischio", "esito", "profit_u", "profit_eur",
    "bankroll_eur", "equity_u", "dd_u", "fonti", "note",
]

ESITO_NO_TRADE = "NO TRADE"
SETTLED_ESITI = ("VINTO", "PERSO")
SKIPPED_ESITI = ("SALTATO", ESITO_NO_TRADE)

# Minuti stimati dopo kickoff prima di poter registrare l'esito
MATCH_DURATION_MIN = {"HT": 55, "O15": 110, "O25": 110, "SH0": 110}
DEFAULT_MATCH_MIN = 110

def parse_kickoff(data, ora) -> pd.Timestamp | None:
    try:
        d = pd.Timestamp(data)
        t = str(ora or "00:00").strip()[:5]
        return pd.Timestamp(f"{d.date()} {t}")
    except (TypeError, ValueError):
        return None


def trade_settle_status(row, now: pd.Timestamp | None = None) -> str:
    """future = non iniziata, live = in corso, ready = registrabile."""
    now = now or pd.Timestamp.now()
    ko = parse_kickoff(row.get("data") if hasattr(row, "get") else row["data"],
                       row.get("ora") if hasattr(row, "get") else row["ora"])
    if ko is None:
        return "ready"
    strat = str(row.get("strategia", "") if hasattr(row, "get") else row["strategia"])
    mins = MATCH_DURATION_MIN.get(strat, DEFAULT_MATCH_MIN)
    end = ko + pd.Timedelta(minutes=mins)
    if now < ko:
        return "future"
    if now < end:
        return "live"
    return "ready"


def can_settle_trade(row, now: pd.Timestamp | None = None) -> bool:
    return trade_settle_status(row, now) == "ready"


def _slot_key(row) -> tuple[str, str]:
    d = pd.Timestamp(row["data"]).date()
    ora = str(row.get("ora", "")).strip()[:5]
    return str(d), ora


def _slot_after(slot_a: tuple[str, str], slot_b: tuple[str, str]) -> bool:
    if slot_a[0] > slot_b[0]:
        return True
    if slot_a[0] < slot_b[0]:
        return False
    return slot_a[1] > slot_b[1]


SYSTEM_ALIASES = {
    "ht": "HT", "half time": "HT", "1ht": "HT",
    "o15": "O15", "over 1.5": "O15", "over15": "O15", "over 1,5": "O15",
    "o25": "O25", "over 2.5": "O25", "over25": "O25", "over 2,5": "O25",
    "sh0": "SH0", "0 sh": "SH0", "0sh": "SH0",
    "sh1": "SH1", "1 sh": "SH1", "1sh": "SH1",
    "sh2": "SH2", "2 sh": "SH2", "2sh": "SH2",
}


def ensure_dirs():
    os.makedirs(JOURNAL_DIR, exist_ok=True)


def normalize_system(value) -> str | None:
    if pd.isna(value):
        return None
    key = str(value).strip().lower()
    if key in SYSTEM_ALIASES:
        return SYSTEM_ALIASES[key]
    upper = str(value).strip().upper()
    if upper in ("HT", "O15", "O25", "SH0", "SH1", "SH2"):
        return upper
    return None


def parse_upload(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizza file upload (wide o long)."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    rename = {}
    for col in df.columns:
        if col in ("id", "match id"):
            rename[col] = "match_id"
        elif col in ("data", "date", "data (utc)"):
            rename[col] = "data"
        elif col in ("ora", "orario", "time", "kickoff"):
            rename[col] = "ora"
        elif col in ("campionato", "league", "lega"):
            rename[col] = "campionato"
        elif col in ("partita", "match", "evento"):
            rename[col] = "partita"
        elif col in ("strategia", "system", "sistema"):
            rename[col] = "strategia"
        elif col in ("segnali", "signals", "signal"):
            rename[col] = "segnali"
    df = df.rename(columns=rename)

    # Formato wide: segnali_ht, segnali_o15, segnali_o25
    wide_rows = []
    if "strategia" not in df.columns:
        for sys_col, sys_name in [
            ("segnali_ht", "HT"), ("ht", "HT"),
            ("segnali_o15", "O15"), ("o15", "O15"),
            ("segnali_o25", "O25"), ("o25", "O25"),
            ("segnali_sh0", "SH0"), ("sh0", "SH0"), ("0 sh", "SH0"),
        ]:
            if sys_col in df.columns:
                part = df[df[sys_col].notna() & (pd.to_numeric(df[sys_col], errors="coerce").fillna(0) > 0)].copy()
                if part.empty:
                    continue
                part["strategia"] = sys_name
                part["segnali"] = pd.to_numeric(part[sys_col], errors="coerce").fillna(0).astype(int)
                wide_rows.append(part)
        if wide_rows:
            df = pd.concat(wide_rows, ignore_index=True)

    if "match_id" not in df.columns:
        df["match_id"] = range(1, len(df) + 1)
    if "data" not in df.columns:
        df["data"] = datetime.now().date()
    if "strategia" not in df.columns or "segnali" not in df.columns:
        raise ValueError(
            "File non valido. Servono colonne: strategia + segnali "
            "(oppure segnali_ht / segnali_o15 / segnali_o25 / segnali_sh0)."
        )

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["strategia"] = df["strategia"].apply(normalize_system)
    df["segnali"] = pd.to_numeric(df["segnali"], errors="coerce").fillna(0).astype(int)
    df = df[df["strategia"].notna() & (df["segnali"] > 0)]

    for col in ("campionato", "partita", "ora", "fonti"):
        if col not in df.columns:
            df[col] = ""

    return df.sort_values(["data", "ora", "match_id"]).reset_index(drop=True)


def load_journal() -> pd.DataFrame:
    ensure_dirs()
    if not os.path.exists(JOURNAL_PATH):
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    df = pd.read_csv(JOURNAL_PATH)
    for col in JOURNAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    for col in ("note", "fonti", "campionato", "partita", "ora", "strategia", "esito", "fase", "modalita_rischio"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    return df[JOURNAL_COLUMNS]


def save_journal(df: pd.DataFrame):
    ensure_dirs()
    df.to_csv(JOURNAL_PATH, index=False)


def create_template():
    ensure_dirs()
    sample = pd.DataFrame(columns=[
        "data", "ora", "campionato", "partita", "match_id", "strategia", "segnali",
    ])
    sample.to_excel(TEMPLATE_PATH, index=False)
    return TEMPLATE_PATH


@dataclass
class LiveState:
    ccs: ControlledCompounding
    strategy: StrategyState = field(default_factory=StrategyState)
    full_stop: int = 0
    params: CombinedParams = field(default_factory=CombinedParams)


def _stake_for_system(system: str, signals: int, row: pd.Series, state: StrategyState) -> tuple[float, str]:
    fake = {"signals": signals, "vinto": 0, "base_stake": 0}

    if system == "HT":
        fake["base_stake"] = ht_base_stake(signals)
        if fake["base_stake"] == 0:
            return 0.0, "Segnali insufficienti"
        state.ht.equity = state.equity_u
        state.ht.peak = state.peak_u
        stake_u, _, _ = process_ht_trade(fake, state.ht)
        return stake_u, ""

    if system == "O15":
        fake["base_stake"] = o15_base_stake(signals)
        if fake["base_stake"] == 0:
            return 0.0, "Segnali insufficienti"
        state.o15.equity = state.equity_u
        state.o15.peak = state.peak_u
        stake_u, _, _ = process_o15_trade(fake, state.o15)
        return stake_u, ""

    if system == "O25":
        fake["base_stake"] = o25_base_stake(signals)
        if fake["base_stake"] == 0:
            return 0.0, "Segnali insufficienti"
        state.o25.equity = state.equity_u
        state.o25.peak = state.peak_u
        stake_u, _, _ = process_o25_trade(fake, state.o25)
        if stake_u == 0:
            return 0.0, "Skip T2 (drawdown)"
        return stake_u, ""

    if system == "SH0":
        fake["base_stake"] = sh0_base_stake(signals)
        if fake["base_stake"] == 0:
            return 0.0, "Segnali insufficienti"
        state.sh0.equity = state.equity_u
        state.sh0.peak = state.peak_u
        stake_u = preview_sh_stake(fake, state.sh0)
        if stake_u <= 0:
            reason = "Pausa shock" if state.sh0.shock_mode > 0 else "Stop DD -18U"
            return 0.0, reason
        return stake_u, ""

    if system in ("SH1", "SH2"):
        from core.sh_common import preview_sh_stake as _preview
        fake["base_stake"] = 1.0 if signals >= 1 else 0.0
        if fake["base_stake"] == 0:
            return 0.0, "Segnali insufficienti"
        sub = state.sh0
        sub.equity = state.equity_u
        sub.peak = state.peak_u
        stake_u = _preview(fake, sub)
        if stake_u <= 0:
            return 0.0, "Stop DD / pausa shock"
        return stake_u, ""

    return 0.0, "Strategia sconosciuta"


def plan_match(
    match_id,
    match_rows: pd.DataFrame,
    live: LiveState,
    signals_map: dict | None = None,
) -> dict:
    """Decide cosa giocare su una partita (combinata)."""
    if live.full_stop > 0:
        live.full_stop -= 1
        return _skip_row(match_rows.iloc[0], "Full stop attivo", signals_map)

    drawdown_u = live.strategy.equity_u - live.strategy.peak_u
    params = live.params

    if params.full_stop_dd is not None and drawdown_u < params.full_stop_dd:
        live.full_stop = params.full_stop_trades

    if signals_map:
        systems = {k: v for k, v in signals_map.items() if v > 0}
    else:
        systems = {}
        for _, r in match_rows.iterrows():
            systems[r["strategia"]] = int(r["segnali"])

    blocked = params.allowed_systems(drawdown_u) or set()
    priority = params.priority_for(drawdown_u)

    chosen_sys = None
    chosen_signals = 0
    for sys_name in priority:
        if sys_name in systems and sys_name not in blocked:
            chosen_sys = sys_name
            chosen_signals = systems[sys_name]
            break

    if chosen_sys is None:
        reason = "Nessuna strategia disponibile"
        if blocked:
            reason += f" (bloccate: {', '.join(sorted(blocked))})"
        return _skip_row(match_rows.iloc[0], reason, signals_map)

    stake_u, extra = _stake_for_system(chosen_sys, chosen_signals, match_rows.iloc[0], live.strategy)
    if stake_u <= 0:
        return _skip_row(match_rows.iloc[0], extra or "Stake 0", signals_map)

    unit_eur = live.ccs.stake_eur()
    if not live.ccs.can_bet():
        return _skip_row(match_rows.iloc[0], "Bankroll insufficiente per 1U", signals_map)

    stake_u = 1.0
    stake_eur = unit_eur
    risk_mode = "CCS"

    row0 = match_rows.iloc[0]
    sig = _signals_dict(systems, signals_map)
    return _plan_row(row0, match_id, chosen_sys, chosen_signals, stake_u, unit_eur, stake_eur,
                     risk_mode, live, drawdown_u, systems, sig, row0.get("fonti", ""))


def _signals_dict(systems: dict, signals_map: dict | None) -> dict:
    if signals_map:
        return {
            "signals_ht": int(signals_map.get("HT", 0)),
            "signals_o15": int(signals_map.get("O15", 0)),
            "signals_o25": int(signals_map.get("O25", 0)),
            "signals_sh0": int(signals_map.get("SH0", 0)),
        }
    return {
        "signals_ht": int(systems.get("HT", 0)),
        "signals_o15": int(systems.get("O15", 0)),
        "signals_o25": int(systems.get("O25", 0)),
        "signals_sh0": int(systems.get("SH0", 0)),
    }


def _plan_row(row0, match_id, chosen_sys, chosen_signals, stake_u, unit_eur, stake_eur,
              risk_mode, live, drawdown_u, systems, sig, fonti=""):
    return {
        "trade_id": str(uuid.uuid4())[:8],
        "data": row0["data"],
        "ora": row0.get("ora", ""),
        "campionato": row0.get("campionato", ""),
        "partita": row0.get("partita", ""),
        "match_id": match_id,
        "strategia": chosen_sys,
        "segnali": chosen_signals,
        "signals_ht": sig["signals_ht"],
        "signals_o15": sig["signals_o15"],
        "signals_o25": sig["signals_o25"],
        "signals_sh0": sig["signals_sh0"],
        "stake_u": round(stake_u, 2),
        "valore_1u": round(unit_eur, 2),
        "stake_eur": round(stake_eur, 2),
        "fase": phase_for_unit_eur(unit_eur),
        "modalita_rischio": risk_mode,
        "esito": "DA GIOCARE",
        "profit_u": None,
        "profit_eur": None,
        "bankroll_eur": round(live.ccs.bankroll, 2),
        "equity_u": round(live.strategy.equity_u, 2),
        "dd_u": round(drawdown_u, 2),
        "fonti": fonti,
        "note": f"Disponibili: {systems}",
    }


def _skip_row(row, reason: str, signals_map: dict | None = None) -> dict:
    sig = _signals_dict({}, signals_map) if signals_map else {
        "signals_ht": 0, "signals_o15": 0, "signals_o25": 0, "signals_sh0": 0,
    }
    if signals_map is None and "strategia" in row.index:
        pass
    return {
        "trade_id": str(uuid.uuid4())[:8],
        "data": row["data"],
        "ora": row.get("ora", ""),
        "campionato": row.get("campionato", ""),
        "partita": row.get("partita", ""),
        "match_id": row.get("match_id"),
        "strategia": "—",
        "segnali": 0,
        "signals_ht": sig["signals_ht"],
        "signals_o15": sig["signals_o15"],
        "signals_o25": sig["signals_o25"],
        "signals_sh0": sig["signals_sh0"],
        "stake_u": 0,
        "valore_1u": 0,
        "stake_eur": 0,
        "fase": "",
        "modalita_rischio": "",
        "esito": "SALTATO",
        "profit_u": 0,
        "profit_eur": 0,
        "bankroll_eur": None,
        "equity_u": None,
        "dd_u": None,
        "fonti": row.get("fonti", ""),
        "note": reason,
    }


def _sync_subsystem_after_settlement(system: str, vinto: bool, profit_u: float, live: LiveState):
    """Aggiorna streak/shock dei sottosistemi senza ricalcolare la stake."""
    state_map = {"HT": live.strategy.ht, "O15": live.strategy.o15, "O25": live.strategy.o25,
                 "SH0": live.strategy.sh0, "SH1": live.strategy.sh0, "SH2": live.strategy.sh0}
    state = state_map.get(system)
    if state is None:
        return

    new_equity = live.strategy.equity_u + profit_u
    state.profits.append(profit_u)
    state.equity = new_equity
    state.equity_history.append(new_equity)
    state.peak = max(state.peak, new_equity)

    if system == "O15":
        from core.o15_backtest import O15_LOSS_STREAK_TRIGGER, O15_SHOCK_TRADES
        if vinto:
            state.loss_streak = 0
        else:
            state.loss_streak += 1
            if state.loss_streak >= O15_LOSS_STREAK_TRIGGER:
                state.shock_mode = O15_SHOCK_TRADES
                state.loss_streak = 0
    elif system == "O25":
        from core.o25_backtest import O25_LOSS_STREAK_TRIGGER, O25_SHOCK_TRADES
        if vinto:
            state.loss_streak = 0
        else:
            state.loss_streak += 1
            if state.loss_streak >= O25_LOSS_STREAK_TRIGGER:
                state.shock_mode = O25_SHOCK_TRADES
                state.loss_streak = 0
    elif system in ("SH0", "SH1", "SH2"):
        from core.sh0_backtest import SH0_LOSS_STREAK_TRIGGER, SH0_SHOCK_TRADES
        if vinto:
            state.loss_streak = 0
        else:
            state.loss_streak += 1
            if state.loss_streak >= SH0_LOSS_STREAK_TRIGGER:
                state.shock_mode = SH0_SHOCK_TRADES
                state.loss_streak = 0


def apply_settlement(trade: dict, vinto: bool, live: LiveState):
    """Registra esito con CCS: stake = 1U, profitto in €."""
    system = trade["strategia"]
    odds = PROFIT_ODDS[system]

    profit_eur = live.ccs.settle_trade(
        vinto=vinto,
        profit_odds=odds,
        date=trade.get("data"),
        system=system,
    )
    profit_u = round(odds, 2) if vinto else -1.0

    _sync_subsystem_after_settlement(system, vinto, profit_u, live)

    live.strategy.equity_u = round(live.strategy.equity_u + profit_u, 2)
    live.strategy.peak_u = max(live.strategy.peak_u, live.strategy.equity_u)

    trade["esito"] = "VINTO" if vinto else "PERSO"
    trade["profit_u"] = profit_u
    trade["profit_eur"] = profit_eur
    trade["bankroll_eur"] = round(live.ccs.bankroll, 2)
    trade["equity_u"] = round(live.strategy.equity_u, 2)
    trade["dd_u"] = round(live.strategy.equity_u - live.strategy.peak_u, 2)
    return trade


def rebuild_live_state(journal: pd.DataFrame, initial_bankroll: float = INITIAL_BANKROLL) -> LiveState:
    live = LiveState(ccs=ControlledCompounding(initial_bankroll))
    journal = journal.sort_values(["data", "ora"]).reset_index(drop=True)

    for _, row in journal.iterrows():
        if row["esito"] in SKIPPED_ESITI:
            continue
        if row["esito"] == "DA GIOCARE":
            continue
        if row["esito"] not in SETTLED_ESITI:
            continue
        apply_settlement(row.to_dict(), row["esito"] == "VINTO", live)

    return live


def process_daily_upload(
    upload_df: pd.DataFrame,
    journal: pd.DataFrame | None = None,
    initial_bankroll: float | None = None,
    skip_existing: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, LiveState]:
    """Pianifica trade del giorno e aggiorna journal."""
    parsed = parse_upload(upload_df)
    journal = load_journal() if journal is None else journal.copy()
    bankroll_start = initial_bankroll if initial_bankroll is not None else INITIAL_BANKROLL

    if journal.empty:
        live = LiveState(ccs=ControlledCompounding(bankroll_start))
    else:
        settled = journal[journal["esito"].isin(SETTLED_ESITI)]
        live = rebuild_live_state(settled, bankroll_start)

    existing_keys = set()
    if skip_existing and not journal.empty:
        for _, r in journal.iterrows():
            existing_keys.add((r["data"], r["match_id"]))

    new_rows = []
    for match_id, group in parsed.groupby("match_id"):
        key = (group.iloc[0]["data"], match_id)
        if skip_existing and key in existing_keys:
            continue
        signals_map = {
            "HT": int(group[group["strategia"] == "HT"]["segnali"].sum()) if "HT" in group["strategia"].values else 0,
            "O15": int(group[group["strategia"] == "O15"]["segnali"].sum()) if "O15" in group["strategia"].values else 0,
            "O25": int(group[group["strategia"] == "O25"]["segnali"].sum()) if "O25" in group["strategia"].values else 0,
            "SH0": int(group[group["strategia"] == "SH0"]["segnali"].sum()) if "SH0" in group["strategia"].values else 0,
        }
        group = group.copy()
        if "fonti" in group.columns:
            group["fonti"] = ", ".join(sorted(set(group["fonti"].dropna().astype(str))))
        plan = plan_match(match_id, group, live, signals_map=signals_map)
        new_rows.append(plan)

    plan_df = pd.DataFrame(new_rows)
    if not plan_df.empty:
        journal = pd.concat([journal, plan_df], ignore_index=True)
        journal = recompute_journal(journal, bankroll_start)
        live = rebuild_live_state(journal[journal["esito"].isin(SETTLED_ESITI)], bankroll_start)

    return plan_df, journal, live


def _signals_group_from_row(row: dict) -> pd.DataFrame:
    rows = []
    base = {
        "data": row["data"], "ora": row.get("ora", ""),
        "campionato": row.get("campionato", ""), "partita": row.get("partita", ""),
        "match_id": row.get("match_id"), "fonti": row.get("fonti", ""),
    }
    for sys, col in [("HT", "signals_ht"), ("O15", "signals_o15"), ("O25", "signals_o25"), ("SH0", "signals_sh0")]:
        n = int(row.get(col) or 0)
        if n > 0:
            rows.append({**base, "strategia": sys, "segnali": n})
    if not rows:
        return pd.DataFrame([{**base, "strategia": "HT", "segnali": 0}])
    return pd.DataFrame(rows)


def recompute_journal(journal: pd.DataFrame, initial_bankroll: float = INITIAL_BANKROLL) -> pd.DataFrame:
    """Ricalcola stake pending in ordine cronologico dopo Win/Lose."""
    if journal.empty:
        return journal

    journal = journal.sort_values(["data", "ora", "trade_id"]).reset_index(drop=True)
    live = LiveState(ccs=ControlledCompounding(initial_bankroll))
    out = []
    last_settled_slot = None

    for _, row in journal.iterrows():
        r = row.to_dict()
        esito = r.get("esito", "DA GIOCARE")
        sig = {
            "HT": int(r.get("signals_ht") or 0),
            "O15": int(r.get("signals_o15") or 0),
            "O25": int(r.get("signals_o25") or 0),
            "SH0": int(r.get("signals_sh0") or 0),
        }
        group_df = _signals_group_from_row(r)

        if esito in SKIPPED_ESITI:
            out.append(r)
            continue

        if esito in SETTLED_ESITI:
            apply_settlement(r, esito == "VINTO", live)
            last_settled_slot = _slot_key(r)
            out.append(r)
            continue

        cur_slot = _slot_key(r)
        if last_settled_slot and not _slot_after(cur_slot, last_settled_slot):
            out.append(r)
            continue

        plan = plan_match(r["match_id"], group_df, live, signals_map=sig)
        plan["trade_id"] = r.get("trade_id", plan["trade_id"])
        plan["esito"] = "DA GIOCARE"
        out.append(plan)

    return pd.DataFrame(out)


def process_fixture_upload(
    file_list: list[tuple],
    journal: pd.DataFrame | None = None,
    initial_bankroll: float | None = None,
    skip_existing: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, LiveState, pd.DataFrame]:
    """Merge file Fixtures e pianifica trade combinati."""
    from core.fixture_parser import merge_fixture_files, merge_to_daily_format

    merged = merge_fixture_files(file_list)
    daily = merge_to_daily_format(merged)
    plan_df, journal_out, live = process_daily_upload(
        daily, journal=journal, initial_bankroll=initial_bankroll, skip_existing=skip_existing,
    )
    return plan_df, journal_out, live, merged


def settle_trade(trade_id: str, vinto: bool, initial_bankroll: float = INITIAL_BANKROLL) -> pd.DataFrame:
    journal = load_journal()
    mask = journal["trade_id"] == trade_id
    if not mask.any():
        raise ValueError(f"Trade {trade_id} non trovato")

    if journal.loc[mask, "esito"].iloc[0] != "DA GIOCARE":
        raise ValueError("Trade già regolato")

    journal.loc[mask, "esito"] = "VINTO" if vinto else "PERSO"
    journal = recompute_journal(journal, initial_bankroll)
    save_journal(journal)
    return journal


def mark_no_trade(trade_id: str, initial_bankroll: float = INITIAL_BANKROLL) -> pd.DataFrame:
    """Segna un trade pianificato come saltato manualmente (nessun P&L)."""
    journal = load_journal()
    mask = journal["trade_id"] == trade_id
    if not mask.any():
        raise ValueError(f"Trade {trade_id} non trovato")

    if journal.loc[mask, "esito"].iloc[0] != "DA GIOCARE":
        raise ValueError("Trade già regolato")

    idx = journal.index[mask][0]
    note = str(journal.at[idx, "note"] or "").strip()
    if note.lower() == "nan":
        note = ""
    journal.at[idx, "esito"] = ESITO_NO_TRADE
    journal.at[idx, "profit_u"] = 0
    journal.at[idx, "profit_eur"] = 0
    journal.at[idx, "note"] = f"{note} | Saltato manualmente".strip(" |")

    journal = recompute_journal(journal, initial_bankroll)
    save_journal(journal)
    return journal


def _time_to_minutes(ora: str) -> int | None:
    try:
        parts = str(ora or "").strip()[:5].split(":")
        if len(parts) < 2:
            return None
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, TypeError):
        return None


def trades_in_period_mask(
    journal: pd.DataFrame,
    date_from=None,
    date_to=None,
    time_from: str | None = None,
    time_to: str | None = None,
) -> pd.Series:
    """Maschera True per i trade nel periodo indicato (data + opzionale fascia oraria)."""
    if journal.empty:
        return pd.Series(dtype=bool)

    dates = pd.to_datetime(journal["data"], errors="coerce").dt.normalize()
    mask = pd.Series(True, index=journal.index)

    if date_from is not None:
        mask &= dates >= pd.Timestamp(date_from).normalize()
    if date_to is not None:
        mask &= dates <= pd.Timestamp(date_to).normalize()

    t_from = _time_to_minutes(time_from) if time_from else None
    t_to = _time_to_minutes(time_to) if time_to else None
    if t_from is not None or t_to is not None:
        minutes = journal["ora"].astype(str).str[:5].apply(_time_to_minutes)
        if t_from is not None and t_to is not None:
            if t_from <= t_to:
                mask &= minutes.between(t_from, t_to)
            else:
                mask &= (minutes >= t_from) | (minutes <= t_to)
        elif t_from is not None:
            mask &= minutes >= t_from
        elif t_to is not None:
            mask &= minutes <= t_to

    return mask.fillna(False)


def delete_trades_in_period(
    date_from=None,
    date_to=None,
    time_from: str | None = None,
    time_to: str | None = None,
    initial_bankroll: float = INITIAL_BANKROLL,
) -> tuple[pd.DataFrame, int]:
    """Elimina trade nel periodo e ricalcola stake/bankroll."""
    journal = load_journal()
    mask = trades_in_period_mask(journal, date_from, date_to, time_from, time_to)
    n = int(mask.sum())
    if n == 0:
        return journal, 0
    journal = journal.loc[~mask].reset_index(drop=True)
    journal = recompute_journal(journal, initial_bankroll)
    save_journal(journal)
    return journal, n


def delete_all_trades() -> pd.DataFrame:
    """Svuota completamente il journal."""
    journal = pd.DataFrame(columns=JOURNAL_COLUMNS)
    save_journal(journal)
    return journal


def _summary_row(group: pd.DataFrame) -> dict:
    played = group[group["esito"].isin(SETTLED_ESITI)]
    profits = played["profit_eur"].dropna()
    win_sum = profits[profits > 0].sum()
    loss_sum = profits[profits < 0].sum()
    return {
        "giocati": len(played),
        "vinti": int((group["esito"] == "VINTO").sum()),
        "persi": int((group["esito"] == "PERSO").sum()),
        "no_trade": int((group["esito"] == ESITO_NO_TRADE).sum()),
        "saltati": int((group["esito"] == "SALTATO").sum()),
        "da_giocare": int((group["esito"] == "DA GIOCARE").sum()),
        "profit_eur": round(float(win_sum), 2),
        "loss_eur": round(abs(float(loss_sum)), 2),
        "netto_eur": round(float(profits.sum()), 2),
        "netto_u": round(float(played["profit_u"].dropna().sum()), 2),
    }


def daily_summary(journal: pd.DataFrame) -> pd.DataFrame:
    """Riepilogo P&L per giorno."""
    if journal.empty:
        return pd.DataFrame(columns=[
            "giorno", "giocati", "vinti", "persi", "no_trade", "saltati",
            "da_giocare", "profit_eur", "loss_eur", "netto_eur", "netto_u",
        ])

    df = journal.copy()
    df["giorno"] = pd.to_datetime(df["data"]).dt.date
    rows = []
    for giorno, group in df.groupby("giorno", sort=False):
        row = {"giorno": giorno, **_summary_row(group)}
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("giorno", ascending=False).reset_index(drop=True)
    return out


def monthly_summary(journal: pd.DataFrame) -> pd.DataFrame:
    """Riepilogo P&L per mese."""
    if journal.empty:
        return pd.DataFrame(columns=[
            "mese", "giocati", "vinti", "persi", "no_trade", "saltati",
            "da_giocare", "profit_eur", "loss_eur", "netto_eur", "netto_u",
        ])

    df = journal.copy()
    df["mese"] = pd.to_datetime(df["data"]).dt.to_period("M").astype(str)
    rows = []
    for mese, group in df.groupby("mese", sort=False):
        row = {"mese": mese, **_summary_row(group)}
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("mese", ascending=False).reset_index(drop=True)
    return out
