"""UI Trade Giornaliero — upload partite e journal."""
import os

import pandas as pd
import streamlit as st

from compound_config import INITIAL_BANKROLL
from core.daily_trades import (
    TEMPLATE_PATH,
    create_template,
    load_journal,
    process_daily_upload,
    process_fixture_upload,
    save_journal,
)
from ui.journal_dashboard import render_journal_section
from ui.metric_table import render_simple_table

DAILY_CSS = """
<style>
    .dt-title { font-size: 1.6rem; font-weight: 700; color: #f0f3f6; margin-bottom: 0.25rem; }
    .dt-sub { color: #8b949e; font-size: 0.85rem; margin-bottom: 1rem; }
    .dt-card {
        background: #161b22; border: 1px solid #30363d; border-radius: 12px;
        padding: 1rem 1.25rem; margin-bottom: 1rem;
    }
    .dt-play {
        background: #0d1f14; border: 1px solid #238636; border-radius: 10px;
        padding: 0.85rem 1rem; margin-bottom: 0.5rem;
    }
    .dt-play strong { color: #3fb950; }
    .dt-skip { color: #8b949e; font-size: 0.85rem; }
    .dt-sig { color: #58a6ff; font-size: 0.8rem; }
</style>
"""


def _signal_summary(r) -> str:
    parts = []
    for label, col in [("HT", "signals_ht"), ("O15", "signals_o15"), ("O25", "signals_o25"), ("SH0", "signals_sh0")]:
        n = int(r.get(col) or 0)
        if n > 0:
            parts.append(f"{label}:{n}")
    return " · ".join(parts) if parts else "—"


def show_daily_trades_tab(initial_bankroll: float):
    st.markdown(DAILY_CSS, unsafe_allow_html=True)
    st.markdown('<div class="dt-title">Trade del Giorno</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="dt-sub">Strategia <b>combinata</b> + CCS (Controlled Compounding). '
        "Stake fisso 1U a scaglioni · Carica i file Fixtures (HT / Over 1.5 / Over 2.5 / 0 SH).</div>",
        unsafe_allow_html=True,
    )

    if not os.path.exists(TEMPLATE_PATH):
        create_template()

    col1, col2, col3 = st.columns(3)
    with col1:
        with open(TEMPLATE_PATH, "rb") as f:
            st.download_button(
                "📥 Scarica template Excel",
                f,
                file_name="template_giornata.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    with col2:
        bankroll_input = st.number_input(
            "Bankroll attuale (€)",
            min_value=0.0,
            value=float(initial_bankroll),
            step=50.0,
            key="dt_bankroll",
        )
    with col3:
        st.caption("Scaglioni 1U")
        st.caption("Partenza: ≥150€ → 3€/U")

    tab_fix, tab_man = st.tabs(["📂 File Fixtures", "📝 Template manuale"])

    journal = load_journal()

    with tab_fix:
        st.markdown('<div class="dt-card">', unsafe_allow_html=True)
        fixture_files = st.file_uploader(
            "Carica tutti i file Fixtures (.xlsx)",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="dt_fixtures",
        )
        st.markdown(
            "<small>Nome file riconosciuto: <code>Fixtures_HT ...</code>, "
            "<code>Fixtures_Ov. 1.5 ...</code>, <code>Fixtures_Ov. 2.5 ...</code>, "
            "<code>0 SH ...</code> (Push, Carry, Rise, Chain, Momentum, 0-0). "
            "Ogni riga = 1 segnale; più file sulla stessa partita vengono sommati.</small>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if fixture_files:
            st.caption(f"{len(fixture_files)} file caricati")
            if st.button("🔍 Merge e calcola giocate", type="primary", key="btn_fixtures"):
                try:
                    file_list = [(f, f.name) for f in fixture_files]
                    plan_df, journal_new, live, merged = process_fixture_upload(
                        file_list,
                        journal=journal,
                        initial_bankroll=bankroll_input,
                    )
                    st.session_state["dt_plan"] = plan_df
                    st.session_state["dt_journal_preview"] = journal_new
                    st.session_state["dt_merged"] = merged
                    st.session_state["dt_live"] = {
                        "bankroll": live.ccs.bankroll,
                        "unit_eur": live.ccs.current_unit_eur,
                        "equity_u": live.strategy.equity_u,
                        "dd_u": live.strategy.equity_u - live.strategy.peak_u,
                    }
                except Exception as e:
                    st.error(f"Errore merge Fixtures: {e}")

    with tab_man:
        st.markdown('<div class="dt-card">', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Carica partite del giorno (.xlsx / .csv)",
            type=["xlsx", "xls", "csv"],
            key="dt_upload",
        )
        st.markdown(
            "<small>Colonne: <code>data, ora, campionato, partita, match_id, strategia, segnali</code> "
            "— oppure <code>segnali_ht / segnali_o15 / segnali_o25</code>.</small>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if uploaded is not None:
            try:
                if uploaded.name.endswith(".csv"):
                    upload_df = pd.read_csv(uploaded)
                else:
                    upload_df = pd.read_excel(uploaded)

                if st.button("🔍 Calcola giocate", type="primary", key="btn_manual"):
                    plan_df, journal_new, live = process_daily_upload(
                        upload_df,
                        journal=journal,
                        initial_bankroll=bankroll_input,
                    )
                    st.session_state["dt_plan"] = plan_df
                    st.session_state["dt_journal_preview"] = journal_new
                    st.session_state.pop("dt_merged", None)
                    st.session_state["dt_live"] = {
                        "bankroll": live.ccs.bankroll,
                        "unit_eur": live.ccs.current_unit_eur,
                        "equity_u": live.strategy.equity_u,
                        "dd_u": live.strategy.equity_u - live.strategy.peak_u,
                    }
            except Exception as e:
                st.error(f"Errore lettura file: {e}")

    plan_df = st.session_state.get("dt_plan")
    merged = st.session_state.get("dt_merged")
    live_info = st.session_state.get("dt_live")

    if merged is not None and not merged.empty:
        with st.expander("Riepilogo merge segnali", expanded=False):
            merge_cols = [
                {"key": "data", "label": "Data", "kind": "text"},
                {"key": "ora", "label": "Ora", "kind": "text"},
                {"key": "campionato", "label": "Campionato", "kind": "text_muted"},
                {"key": "partita", "label": "Partita", "kind": "text"},
                {"key": "strategia", "label": "Strategia", "kind": "pill"},
                {"key": "segnali", "label": "Segnali", "kind": "badge"},
                {"key": "fonti", "label": "Fonti", "kind": "text_muted"},
            ]
            render_simple_table(
                merged[["data", "ora", "campionato", "partita", "strategia", "segnali", "fonti"]],
                merge_cols,
                seed_col="partita",
            )

    if plan_df is not None and not plan_df.empty:
        if live_info:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Bankroll (settled)", f"{live_info['bankroll']:,.2f} €")
            m2.metric("1U corrente", f"{live_info.get('unit_eur', 0):.2f} €")
            m3.metric("Equity U", f"{live_info['equity_u']:.2f}")
            m4.metric("Drawdown U", f"{live_info['dd_u']:.2f}")

        st.subheader("Giocate consigliate")
        for _, r in plan_df.iterrows():
            sig_txt = _signal_summary(r)
            if r["esito"] == "DA GIOCARE":
                st.markdown(
                    f'<div class="dt-play">'
                    f"<strong>▶ {r['partita']}</strong> ({r['campionato']}) — {r['ora']}<br>"
                    f"Strategia: <b>{r['strategia']}</b> · Segnali scelti: {int(r['segnali'])}<br>"
                    f'<span class="dt-sig">Segnali totali: {sig_txt}</span><br>'
                    f"Stake: <b>{r['stake_eur']:.2f} €</b> (1 U @ {r['valore_1u']:.2f} €/U)<br>"
                    f"Fase: {r['fase']} · Rischio: {r['modalita_rischio']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="dt-skip">⏭ {r["partita"]} — SALTATO: {r["note"]} '
                    f'({sig_txt})</div>',
                    unsafe_allow_html=True,
                )

        if st.button("💾 Salva nel journal", type="primary"):
            save_journal(st.session_state["dt_journal_preview"])
            st.success("Journal aggiornato.")
            st.session_state.pop("dt_plan", None)
            st.session_state.pop("dt_journal_preview", None)
            st.session_state.pop("dt_merged", None)
            st.rerun()

    st.divider()
    render_journal_section(load_journal(), bankroll_input, initial_bankroll)
