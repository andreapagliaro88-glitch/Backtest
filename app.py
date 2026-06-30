import pandas as pd
import streamlit as st

from compound_config import INITIAL_BANKROLL
from core.backtest import prepare_grouped, run_backtest
from core.ccs_runner import run_ccs_backtest, ccs_to_dict
from core.ht_backtest import run_ht_backtest
from core.loader import load_data
from core.o15_backtest import run_o15_backtest
from core.o25_backtest import run_o25_backtest
from core.sh0_backtest import run_sh0_backtest
from core.sh1_backtest import run_sh1_backtest
from core.sh2_backtest import run_sh2_backtest
from ui.ccs_dashboard import show_ccs_compound_tab
from ui.daily_trades_tab import show_daily_trades_tab
from ui.footystats_dashboard import show_footystats_tab
from ui.plot_theme import plot_bar, plot_line
from ui.strategy_tabs import show_combined_tab, show_ht_tab, show_o15_tab, show_o25_tab, show_sh0_tab, show_sh1_tab, show_sh2_tab
from ui.manual_strategy_tab import show_manual_strategy_tab, SESSION_DF_KEY as MANUAL_DF_KEY, SESSION_ODDS_KEY as MANUAL_ODDS_KEY
from core.manual_loader import load_from_folder as load_manual_from_folder
from core.manual_strategy import run_manual_backtest, get_manual_label, set_manual_odds

st.set_page_config(
    page_title="Sistema Backtest",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    [data-testid="stAppViewContainer"] > section.main > div {
        max-width: 100%;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def load_all_data():
    df_raw = load_data()
    if df_raw.empty:
        return df_raw, pd.DataFrame()
    return df_raw, prepare_grouped(df_raw)


@st.cache_data
def load_sh0_data_cached():
    from core.sh0_loader import load_sh0_data
    return load_sh0_data()


@st.cache_data
def load_sh1_data_cached():
    from core.sh1_loader import load_sh1_data
    return load_sh1_data()


@st.cache_data
def load_sh2_data_cached():
    from core.sh2_loader import load_sh2_data
    return load_sh2_data()


@st.cache_data
def run_unit_backtests(_df_raw, _df_grouped, _df_sh0, _df_sh1, _df_sh2):
    results = {
        "Combined": run_backtest(_df_grouped, df_raw=_df_raw),
        "HT": run_ht_backtest(_df_raw),
        "O15": run_o15_backtest(_df_raw),
        "O25": run_o25_backtest(_df_raw),
    }
    if not _df_sh0.empty:
        results["SH0"] = run_sh0_backtest(_df_sh0)
    else:
        results["SH0"] = pd.DataFrame()
    if not _df_sh1.empty:
        results["SH1"] = run_sh1_backtest(_df_sh1)
    else:
        results["SH1"] = pd.DataFrame()
    if not _df_sh2.empty:
        results["SH2"] = run_sh2_backtest(_df_sh2)
    else:
        results["SH2"] = pd.DataFrame()
    return results


@st.cache_data
def run_compound(_df_raw, _df_grouped, initial_bankroll, _ccs_cache_v=2):
    df, ccs = run_ccs_backtest(
        _df_grouped,
        _df_raw,
        initial_bankroll=initial_bankroll,
    )
    return df, ccs_to_dict(ccs)


def unit_stats(df, label, note: str = ""):
    if df.empty:
        return {"Strategia": label, "Profit (U)": 0, "Max DD (U)": 0, "Trade": 0, "Winrate": 0, "Pattern": note}

    active = df[df["stake"] > 0]
    return {
        "Strategia": label,
        "Profit (U)": round(df["profit"].sum(), 2),
        "Max DD (U)": round(df["dd"].min(), 2),
        "Trade": len(active),
        "Winrate": round((active["profit"] > 0).mean() * 100, 2) if len(active) else 0,
        "Pattern": note,
    }


SUMMARY_RESULTS_KEY = "app_summary_unit_results"
SUMMARY_NOTES_KEY = "app_summary_pattern_notes"
COMPOUND_DF_KEY = "app_compound_df"
COMPOUND_CCS_KEY = "app_compound_ccs"


def _empty_unit_results():
    return {
        "Combined": pd.DataFrame(),
        "HT": pd.DataFrame(),
        "O15": pd.DataFrame(),
        "O25": pd.DataFrame(),
        "SH0": pd.DataFrame(),
        "SH1": pd.DataFrame(),
        "SH2": pd.DataFrame(),
    }


def compute_all_unit_results(df_raw, df_grouped, df_sh0, df_sh1, df_sh2, df_manual):
    """Calcola tutti i backtest unità (solo su richiesta utente)."""
    unit_results = run_unit_backtests(df_raw, df_grouped, df_sh0, df_sh1, df_sh2)
    from core.tier_config import TIER_SYSTEMS
    from ui.tier_metodo import active_tier_rules

    tier_runners = {
        "HT": ("ht", run_ht_backtest, df_raw),
        "O15": ("o15", run_o15_backtest, df_raw),
        "O25": ("o25", run_o25_backtest, df_raw),
        "SH0": ("sh0", run_sh0_backtest, df_sh0),
        "SH1": ("sh1", run_sh1_backtest, df_sh1),
        "SH2": ("sh2", run_sh2_backtest, df_sh2),
        "MANUAL": ("manual", run_manual_backtest, df_manual),
    }
    if MANUAL_ODDS_KEY in st.session_state:
        set_manual_odds(st.session_state[MANUAL_ODDS_KEY])
    for system in TIER_SYSTEMS:
        key, fn, df = tier_runners[system]
        if df is None or df.empty:
            continue
        unit_results[system] = fn(df, tier_rules=active_tier_rules(key, system))
    pattern_notes = apply_summary_pattern_filters(unit_results, df_raw, df_sh0, df_sh1, df_sh2)
    return unit_results, pattern_notes


def apply_summary_pattern_filters(unit_results, df_raw, df_sh0, df_sh1, df_sh2):
    """Applica le combinazioni pattern scelte nelle tab al riepilogo."""
    from ui.strategy_dashboard import active_patterns_key, get_active_combo_label
    from ui.tier_metodo import active_tier_rules, format_stakes_summary, supports_tier

    runners = [
        ("ht", "HT", df_raw, run_ht_backtest),
        ("o15", "O15", df_raw, run_o15_backtest),
        ("o25", "O25", df_raw, run_o25_backtest),
        ("sh0", "SH0", df_sh0, run_sh0_backtest),
        ("sh1", "SH1", df_sh1, run_sh1_backtest),
        ("sh2", "SH2", df_sh2, run_sh2_backtest),
    ]
    df_manual = st.session_state.get(MANUAL_DF_KEY)
    if df_manual is None or (hasattr(df_manual, "empty") and df_manual.empty):
        df_manual = load_manual_from_folder()
    if MANUAL_ODDS_KEY in st.session_state:
        set_manual_odds(st.session_state[MANUAL_ODDS_KEY])
    if not df_manual.empty:
        runners.append(("manual", "MANUAL", df_manual, run_manual_backtest))
    notes: dict[str, str] = {}
    for key, label, df, run_fn in runners:
        pats = st.session_state.get(active_patterns_key(key))
        if not pats or df.empty:
            continue
        if supports_tier(label):
            unit_results[label] = run_fn(df, tuple(pats), tier_rules=active_tier_rules(key, label))
            combo = get_active_combo_label(key) or " + ".join(pats)
            notes[label] = f"{combo} · {format_stakes_summary(key, label)}"
        else:
            unit_results[label] = run_fn(df, tuple(pats))
            notes[label] = get_active_combo_label(key) or " + ".join(pats)
    return notes


def show_unit_tab(df, label):
    if df.empty:
        st.warning("Nessun dato disponibile. Carica file Excel in `data/`.")
        return

    active = df[df["stake"] > 0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Profitto", f"{df['profit'].sum():.2f} U")
    c2.metric("Max Drawdown", f"{df['dd'].min():.2f} U")
    c3.metric("Trade attivi", len(active))
    c4.metric("Winrate", f"{(active['profit'] > 0).mean() * 100:.1f}%")

    plot_line(active, y="equity", title=f"Equity Curve — {label}", color="#3fb950", fill=True, key=f"unit_eq_{label}")

    monthly = df.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit"].sum().reset_index()
    monthly_profit["date"] = monthly_profit["date"].astype(str)
    plot_bar(monthly_profit, x="date", y="profit", title=f"Profitto mensile — {label}", key=f"unit_bar_{label}")

    with st.expander("Tabella trade"):
        st.dataframe(df, use_container_width=True)


def show_compound_tab(df_trades, ccs, initial_bankroll):
    """Retrocompatibilità — delega al dashboard CCS."""
    show_ccs_compound_tab(df_trades, ccs, initial_bankroll)


def main():
    initial_bankroll = INITIAL_BANKROLL

    df_raw, df_grouped = load_all_data()
    df_sh0 = load_sh0_data_cached()
    df_sh1 = load_sh1_data_cached()
    df_sh2 = load_sh2_data_cached()

    df_manual = st.session_state.get(MANUAL_DF_KEY)
    if df_manual is None or (hasattr(df_manual, "empty") and df_manual.empty):
        df_manual = load_manual_from_folder()
    if MANUAL_ODDS_KEY in st.session_state:
        set_manual_odds(st.session_state[MANUAL_ODDS_KEY])

    hdr1, hdr2, hdr3 = st.columns([4, 1, 1])
    with hdr1:
        st.title("Sistema Backtest")
        st.caption("HT · Over 1.5 · Over 2.5 · 0 SH · 1 SH · 2 SH · Manuale · Combined · Compound · FootyStats")
    with hdr2:
        if st.button("Aggiorna riepilogo", type="primary", use_container_width=True):
            with st.spinner("Calcolo backtest..."):
                unit_results, pattern_notes = compute_all_unit_results(
                    df_raw, df_grouped, df_sh0, df_sh1, df_sh2, df_manual,
                )
                st.session_state[SUMMARY_RESULTS_KEY] = unit_results
                st.session_state[SUMMARY_NOTES_KEY] = pattern_notes
    with hdr3:
        if st.button("Aggiorna dati", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if not df_raw.empty and "pattern" not in df_raw.columns:
        st.cache_data.clear()
        st.warning("Dati aggiornati — ricarico con i pattern dei file.")
        st.rerun()

    if df_raw.empty and df_sh0.empty and df_sh1.empty and df_sh2.empty and load_manual_from_folder().empty:
        if MANUAL_DF_KEY not in st.session_state or st.session_state.get(MANUAL_DF_KEY) is None or st.session_state[MANUAL_DF_KEY].empty:
            st.error(
                "Nessun file trovato. Aggiungi file `.xlsx` in `data/`, `data/sh0/`, `data/sh1/`, `data/sh2/` "
                "oppure caricali nella tab **Manuale**."
            )
            st.stop()

    unit_results = st.session_state.get(SUMMARY_RESULTS_KEY)
    pattern_notes = st.session_state.get(SUMMARY_NOTES_KEY) or {}

    tabs = st.tabs([
        "Trade Giornaliero",
        "Combined", "HT", "Over 1.5", "Over 2.5", "0 SH", "1 SH", "2 SH", "Manuale",
        "Compound €", "Analisi Campionati",
    ])

    with tabs[0]:
        show_daily_trades_tab(initial_bankroll)
    with tabs[1]:
        show_combined_tab(df_raw, df_grouped)
    with tabs[2]:
        show_ht_tab(df_raw)
    with tabs[3]:
        show_o15_tab(df_raw)
    with tabs[4]:
        show_o25_tab(df_raw)
    with tabs[5]:
        show_sh0_tab()
    with tabs[6]:
        show_sh1_tab()
    with tabs[7]:
        show_sh2_tab()
    with tabs[8]:
        show_manual_strategy_tab()
    with tabs[9]:
        if df_raw.empty:
            st.info("Compound richiede dati HT/O15/O25 in `data/`.")
        else:
            if st.button("▶️ Esegui compound CCS", type="primary", key="app_run_compound"):
                with st.spinner("Calcolo compound..."):
                    df_c, ccs_c = run_compound(df_raw, df_grouped, initial_bankroll)
                    st.session_state[COMPOUND_DF_KEY] = df_c
                    st.session_state[COMPOUND_CCS_KEY] = ccs_c
            df_compound = st.session_state.get(COMPOUND_DF_KEY, pd.DataFrame())
            ccs_data = st.session_state.get(COMPOUND_CCS_KEY)
            if ccs_data is not None and not df_compound.empty:
                show_ccs_compound_tab(
                    df_compound, ccs_data, initial_bankroll,
                    df_grouped=df_grouped, df_raw=df_raw,
                )
            else:
                st.info("Clicca **Esegui compound CCS** per avviare il backtest compound.")
    with tabs[10]:
        show_footystats_tab()

    from ui.tier_metodo import format_stakes_summary

    def _tier_note(label: str, key: str) -> str:
        base = pattern_notes.get(label) or f"Tutti · {format_stakes_summary(key, label)}"
        return base

    with st.expander("📊 Riepilogo tutte le strategie (unità)", expanded=unit_results is not None):
        if unit_results is None:
            st.info("Clicca **Aggiorna riepilogo** in alto per calcolare profit, DD e winrate.")
        else:
            summary_rows = [
                unit_stats(unit_results["Combined"], "Combined", pattern_notes.get("Combined", "")),
                unit_stats(unit_results["HT"], "HT", _tier_note("HT", "ht")),
                unit_stats(unit_results["O15"], "O15", _tier_note("O15", "o15")),
                unit_stats(unit_results["O25"], "O25", _tier_note("O25", "o25")),
            ]
            if not unit_results["SH0"].empty:
                summary_rows.append(unit_stats(unit_results["SH0"], "SH0", _tier_note("SH0", "sh0")))
            if not unit_results["SH1"].empty:
                summary_rows.append(unit_stats(unit_results["SH1"], "SH1", _tier_note("SH1", "sh1")))
            if not unit_results["SH2"].empty:
                summary_rows.append(unit_stats(unit_results["SH2"], "SH2", _tier_note("SH2", "sh2")))
            if unit_results.get("MANUAL") is not None and not unit_results["MANUAL"].empty:
                summary_rows.append(unit_stats(
                    unit_results["MANUAL"],
                    get_manual_label(),
                    _tier_note("MANUAL", "manual"),
                ))
            if pattern_notes:
                st.caption(
                    "Pattern attivi: "
                    + " · ".join(f"**{k}** → {v}" for k, v in pattern_notes.items())
                )
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
