"""Tab strategia con backtest, combinazioni pattern e ottimizzazione."""
from __future__ import annotations

import streamlit as st

from core.backtest import run_backtest
from core.combined_combo_optimizer import optimize_combined_combos, run_combined_with_patterns
from core.combined_optimizer import format_params as combined_format, optimize_combined
from core.ht_backtest import run_ht_backtest
from core.ht_optimizer import format_params as ht_format, optimize_ht
from core.o15_backtest import run_o15_backtest
from core.o15_optimizer import format_params as o15_format, optimize_o15
from core.o25_backtest import run_o25_backtest
from core.o25_optimizer import format_params as o25_format, optimize_o25
from core.sh0_backtest import run_sh0_backtest
from core.sh0_combo_optimizer import optimize_sh0_combos
from core.sh0_loader import load_sh0_data
from core.sh1_backtest import run_sh1_backtest
from core.sh1_combo_optimizer import optimize_sh1_combos
from core.sh1_loader import load_sh1_data
from core.sh0_optimizer import format_params as sh0_format, optimize_sh0
from core.sh1_optimizer import format_params as sh1_format, optimize_sh1
from core.sh2_backtest import run_sh2_backtest
from core.sh2_combo_optimizer import optimize_sh2_combos
from core.sh2_loader import load_sh2_data
from core.sh2_optimizer import format_params as sh2_format, optimize_sh2
from core.pattern_combo_optimizer import make_system_combo_optimizer
from ui.strategy_dashboard import StrategyConfig, show_strategy_tab

optimize_ht_combos = make_system_combo_optimizer("HT", run_ht_backtest)
optimize_o15_combos = make_system_combo_optimizer("O15", run_o15_backtest)
optimize_o25_combos = make_system_combo_optimizer("O25", run_o25_backtest)


def show_ht_tab(df_raw):
    show_strategy_tab(StrategyConfig(
        key="ht",
        title="HT — Backtest & Ottimizzazione",
        data_hint="File Excel in `data/ht/` (ATTACK CORE, MOMENTUM, ...).",
        system="HT",
        df_raw=df_raw,
        run_backtest=lambda d, p=None, **kw: run_ht_backtest(d, p, **kw),
        optimize_combos=optimize_ht_combos,
        optimize_stake=optimize_ht,
        format_params=ht_format,
    ))


def show_o15_tab(df_raw):
    show_strategy_tab(StrategyConfig(
        key="o15",
        title="Over 1.5 — Backtest & Ottimizzazione",
        data_hint="File Excel in `data/over15/` (Boost, Flow, Trigger, ...).",
        system="O15",
        df_raw=df_raw,
        run_backtest=lambda d, p=None, **kw: run_o15_backtest(d, p, **kw),
        optimize_combos=optimize_o15_combos,
        optimize_stake=optimize_o15,
        format_params=o15_format,
    ))


def show_o25_tab(df_raw):
    show_strategy_tab(StrategyConfig(
        key="o25",
        title="Over 2.5 — Backtest & Ottimizzazione",
        data_hint="File Excel in `data/over25/` (Core, Edge, Flux, ...).",
        system="O25",
        df_raw=df_raw,
        run_backtest=lambda d, p=None, **kw: run_o25_backtest(d, p, **kw),
        optimize_combos=optimize_o25_combos,
        optimize_stake=optimize_o25,
        format_params=o25_format,
    ))


def show_combined_tab(df_raw, df_grouped):
    def run_combined_bt(d, ht=None, o15=None, o25=None):
        if ht is None and o15 is None and o25 is None:
            return run_backtest(df_grouped, df_raw=d)
        return run_combined_with_patterns(d, ht, o15, o25)

    show_strategy_tab(StrategyConfig(
        key="combined",
        title="Combined — Backtest & Ottimizzazione",
        data_hint="Combina HT + O15 + O25. Testa combinazioni pattern e parametri di priorità.",
        system=None,
        df_raw=df_raw,
        df_grouped=df_grouped,
        run_backtest=run_combined_bt,
        optimize_combos=optimize_combined_combos,
        optimize_stake=optimize_combined,
        format_params=combined_format,
        stake_label="Ottimizza parametri",
    ))


@st.cache_data
def _load_sh0_data():
    return load_sh0_data()


@st.cache_data
def _load_sh1_data():
    return load_sh1_data()


@st.cache_data
def _load_sh2_data():
    return load_sh2_data()


def show_sh0_tab():
    try:
        df_raw = _load_sh0_data()
    except Exception as exc:
        st.error(f"Errore caricamento 0 SH: {exc}")
        return
    if df_raw.empty:
        st.error("Nessun file in `data/sh0/`. Copia i file `.xlsx` e clicca **Aggiorna dati**.")
        return

    try:
        show_strategy_tab(StrategyConfig(
            key="sh0",
            title="0 SH — Backtest & Ottimizzazione",
            data_hint="Quota **1.3** · **+0.3U / -1U** per trade · **1U** fissa (Composta Controllata) · stop DD **-18U** · combinazioni **senza duplicati** per partita.",
            system="SH0",
            df_raw=df_raw,
            run_backtest=lambda d, p=None, **kw: run_sh0_backtest(d, p, **kw),
            optimize_combos=optimize_sh0_combos,
            optimize_stake=optimize_sh0,
            format_params=sh0_format,
        ))
    except Exception as exc:
        st.error(f"Errore tab 0 SH: {exc}")


def show_sh1_tab():
    try:
        df_raw = _load_sh1_data()
    except Exception as exc:
        st.error(f"Errore caricamento 1 SH: {exc}")
        return
    if df_raw.empty:
        st.error("Nessun file in `data/sh1/`. Copia i file `.xlsx` e clicca **Aggiorna dati**.")
        return

    show_strategy_tab(StrategyConfig(
        key="sh1",
        title="1 SH — Backtest & Ottimizzazione",
        data_hint="Quota **1.3** · **+0.3U / -1U** per trade · **1U** fissa (Composta Controllata) · stop DD **-18U** · combinazioni senza duplicati.",
        system="SH1",
        df_raw=df_raw,
        run_backtest=lambda d, p=None, **kw: run_sh1_backtest(d, p, **kw),
        optimize_combos=optimize_sh1_combos,
        optimize_stake=optimize_sh1,
        format_params=sh1_format,
    ))


def show_sh2_tab():
    try:
        df_raw = _load_sh2_data()
    except Exception as exc:
        st.error(f"Errore caricamento 2 SH: {exc}")
        return
    if df_raw.empty:
        st.error("Nessun file in `data/sh2/`. Copia i file `.xlsx` e clicca **Aggiorna dati**.")
        return

    show_strategy_tab(StrategyConfig(
        key="sh2",
        title="2 SH — Backtest & Ottimizzazione",
        data_hint="Quota **1.3** · **+0.3U / -1U** per trade · **1U** fissa (Composta Controllata) · stop DD **-18U** · combinazioni senza duplicati.",
        system="SH2",
        df_raw=df_raw,
        run_backtest=lambda d, p=None, **kw: run_sh2_backtest(d, p, **kw),
        optimize_combos=optimize_sh2_combos,
        optimize_stake=optimize_sh2,
        format_params=sh2_format,
    ))
