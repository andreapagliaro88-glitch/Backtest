"""Tab strategia manuale — upload Excel + quota ingresso."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.manual_loader import (
    load_from_folder,
    load_from_uploads,
    list_available_patterns,
    save_uploads_to_folder,
)
from core.manual_strategy import (
    MANUAL_CFG_KEY,
    MANUAL_SYSTEM,
    get_manual_decimal_odds,
    get_manual_label,
    get_manual_profit_odds,
    manual_format_params,
    run_manual_backtest,
    set_manual_label,
    set_manual_odds,
)
from core.pattern_combo_optimizer import make_system_combo_optimizer
from ui.strategy_dashboard import show_strategy_tab, StrategyConfig

optimize_manual_combos = make_system_combo_optimizer(MANUAL_SYSTEM, run_manual_backtest)

SESSION_DF_KEY = f"{MANUAL_CFG_KEY}_df_raw"
SESSION_ODDS_KEY = f"{MANUAL_CFG_KEY}_decimal_odds"
SESSION_LABEL_KEY = f"{MANUAL_CFG_KEY}_label"


def _load_manual_df() -> pd.DataFrame:
    if SESSION_DF_KEY in st.session_state and not st.session_state[SESSION_DF_KEY].empty:
        return st.session_state[SESSION_DF_KEY]
    disk = load_from_folder()
    if not disk.empty:
        st.session_state[SESSION_DF_KEY] = disk
    return disk


def _sync_manual_globals() -> None:
    """Sincronizza quota/nome dai widget in session_state verso il modulo backtest."""
    if SESSION_ODDS_KEY in st.session_state:
        set_manual_odds(float(st.session_state[SESSION_ODDS_KEY]))
    if SESSION_LABEL_KEY in st.session_state:
        set_manual_label(str(st.session_state[SESSION_LABEL_KEY]))


@st.fragment
def _manual_strategy_body():
    """Fragment: quota, nome e upload non resettano la tab principale dell'app."""
    if SESSION_LABEL_KEY not in st.session_state:
        st.session_state[SESSION_LABEL_KEY] = get_manual_label()
    if SESSION_ODDS_KEY not in st.session_state:
        st.session_state[SESSION_ODDS_KEY] = float(get_manual_decimal_odds())

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.text_input(
            "Nome strategia",
            key=SESSION_LABEL_KEY,
        )
    with c2:
        st.number_input(
            "Quota ingresso",
            min_value=1.01,
            max_value=50.0,
            step=0.01,
            format="%.2f",
            key=SESSION_ODDS_KEY,
            help="Quota decimale alla quale entri (es. 1.35 → profitto +0.35U per 1U puntata).",
        )
        _sync_manual_globals()
        st.caption(f"Profitto vinta: **+{get_manual_profit_odds():.2f} U** / U")

    with c3:
        st.caption("Pattern caricati")
        df_preview = _load_manual_df()
        n_pat = len(list_available_patterns(df_preview)) if not df_preview.empty else 0
        st.metric("File / pattern", n_pat)

    uploaded = st.file_uploader(
        "File Excel (.xlsx) — uno per pattern",
        type=["xlsx"],
        accept_multiple_files=True,
        key=f"{MANUAL_CFG_KEY}_uploads",
    )

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("📥 Carica file selezionati", type="primary", key=f"{MANUAL_CFG_KEY}_load_btn"):
            if not uploaded:
                st.warning("Seleziona almeno un file Excel.")
            else:
                df = load_from_uploads(uploaded)
                if df.empty:
                    st.error("Nessuna riga valida. Controlla colonne ID, Data, Gol.")
                else:
                    st.session_state[SESSION_DF_KEY] = df
                    n_loaded = len(list_available_patterns(df))
                    st.success(
                        f"Caricati **{len(uploaded)}** file · **{len(df):,}** righe · **{n_loaded}** pattern."
                    )
    with b2:
        if st.button("💾 Salva in data/manual/", key=f"{MANUAL_CFG_KEY}_save_btn"):
            if not uploaded:
                st.warning("Seleziona i file da salvare.")
            else:
                n = save_uploads_to_folder(uploaded)
                st.success(f"Salvati **{n}** file in `data/manual/`.")
    with b3:
        if st.button("🔄 Ricarica da data/manual/", key=f"{MANUAL_CFG_KEY}_reload_disk"):
            disk = load_from_folder()
            if disk.empty:
                st.warning("Nessun file in `data/manual/`.")
            else:
                st.session_state[SESSION_DF_KEY] = disk
                st.success(f"Ricaricati **{len(list_available_patterns(disk))}** pattern da disco.")

    df_raw = _load_manual_df()
    if df_raw.empty:
        st.info("Carica file Excel per iniziare il backtest.")
        return

    _sync_manual_globals()
    patterns = list_available_patterns(df_raw)
    st.caption(
        f"Pattern: **{', '.join(patterns)}** · Quota **{get_manual_decimal_odds():.2f}** "
        f"(+{get_manual_profit_odds():.2f}U) · {len(df_raw):,} righe"
    )

    def _run_manual_stake(*args, **kwargs):
        st.info("Per la strategia manuale usa **⚖️ Simula stake** (tab tier).")
        baseline = {"profit": 0.0, "max_dd": 0.0, "score": 0.0, "params": {}}
        return baseline, pd.DataFrame()

    show_strategy_tab(StrategyConfig(
        key=MANUAL_CFG_KEY,
        title=f"{get_manual_label()} — Backtest & Ottimizzazione",
        data_hint=(
            f"Quota **{get_manual_decimal_odds():.2f}** · "
            f"**+{get_manual_profit_odds():.2f}U / -1U** per trade (tier) · "
            "file caricati manualmente."
        ),
        system=MANUAL_SYSTEM,
        df_raw=df_raw,
        run_backtest=lambda d, p=None, **kw: run_manual_backtest(d, p, **kw),
        optimize_combos=optimize_manual_combos,
        optimize_stake=_run_manual_stake,
        format_params=manual_format_params,
        stake_label="Ottimizza stake (legacy)",
    ))


def show_manual_strategy_tab():
    st.markdown("### Strategia manuale")
    st.caption(
        "Carica i file Excel come per le altre strategie (colonne **ID**, **Data UTC**, **Gol casa/ospite**, **Vinto**). "
        "Ogni file = un **pattern**. Stesso flusso tier → stake → combinazioni."
    )
    _manual_strategy_body()
