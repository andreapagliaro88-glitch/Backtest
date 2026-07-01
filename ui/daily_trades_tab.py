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
from core.strategy_daily_plan import StrategyDailyPlanConfig
from core.strategy_daily_fixtures import (
    DEFAULT_FIXTURE_HINT,
    FIXTURE_HINTS,
    fixture_files_as_upload_tuples,
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
    strat = str(r.get("strategia") or "")
    if strat in ("SH1", "SH2"):
        parts.append(f"{strat}:{int(r.get('segnali') or 0)}")
    return " · ".join(parts) if parts else "—"


def render_daily_trades_panel(
    *,
    scope: str = "dt",
    title: str = "Trade del Giorno",
    subtitle: str,
    initial_bankroll: float,
    allowed_systems: tuple[str, ...] | None = None,
    forced_system: str | None = None,
    journal_strategia_filter: str | tuple[str, ...] | None = None,
    fixture_hint: str | None = None,
    cfg_key: str | None = None,
    tier_plan: StrategyDailyPlanConfig | None = None,
) -> None:
    """Pannello trade giornaliero condiviso (tab principale e tab per strategia)."""
    st.markdown(DAILY_CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="dt-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="dt-sub">{subtitle}</div>', unsafe_allow_html=True)

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
                key=f"{scope}_dl_template",
            )
    with col2:
        bankroll_input = st.number_input(
            "Bankroll attuale (€)",
            min_value=0.0,
            value=float(initial_bankroll),
            step=50.0,
            key=f"{scope}_bankroll",
        )
    with col3:
        st.caption("Scaglioni 1U")
        st.caption("Partenza: ≥150€ → 3€/U")

    tab_fix, tab_man = st.tabs(["📂 File Fixtures", "📝 Template manuale"])

    journal = load_journal()
    hint = fixture_hint or DEFAULT_FIXTURE_HINT
    upload_kwargs = {
        "journal": journal,
        "initial_bankroll": bankroll_input,
        "allowed_systems": allowed_systems,
        "forced_system": forced_system,
        "tier_plan": tier_plan,
    }

    with tab_fix:
        st.markdown('<div class="dt-card">', unsafe_allow_html=True)
        st.markdown("**1.** Trascina qui i file Excel del giorno (export Fixtures)")
        fixture_files = st.file_uploader(
            "Carica tutti i file Fixtures (.xlsx)",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key=f"{scope}_fixtures",
        )
        st.markdown(f"<small>{hint}</small>", unsafe_allow_html=True)
        st.markdown(
            "<small><b>2.</b> Dopo il caricamento clicca <b>Merge e calcola giocate</b> "
            "per vedere stake e giocate consigliate.</small>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if cfg_key and fixture_files_as_upload_tuples(cfg_key):
            if st.button("📁 Usa file salvati nella cartella strategia", key=f"{scope}_from_folder"):
                try:
                    file_list = fixture_files_as_upload_tuples(cfg_key)
                    plan_df, journal_new, live, merged = process_fixture_upload(file_list, **upload_kwargs)
                    st.session_state[f"{scope}_plan"] = plan_df
                    st.session_state[f"{scope}_journal_preview"] = journal_new
                    st.session_state[f"{scope}_merged"] = merged
                    st.session_state[f"{scope}_live"] = {
                        "bankroll": live.ccs.bankroll,
                        "unit_eur": live.ccs.current_unit_eur,
                        "equity_u": live.strategy.equity_u,
                        "dd_u": live.strategy.equity_u - live.strategy.peak_u,
                    }
                except Exception as e:
                    st.error(f"Errore merge Fixtures: {e}")

        if fixture_files:
            st.caption(f"{len(fixture_files)} file caricati")
            if st.button("🔍 Merge e calcola giocate", type="primary", key=f"{scope}_btn_fixtures"):
                try:
                    file_list = [(f, f.name) for f in fixture_files]
                    plan_df, journal_new, live, merged = process_fixture_upload(file_list, **upload_kwargs)
                    st.session_state[f"{scope}_plan"] = plan_df
                    st.session_state[f"{scope}_journal_preview"] = journal_new
                    st.session_state[f"{scope}_merged"] = merged
                    st.session_state[f"{scope}_live"] = {
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
            key=f"{scope}_upload",
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

                if st.button("🔍 Calcola giocate", type="primary", key=f"{scope}_btn_manual"):
                    plan_df, journal_new, live = process_daily_upload(upload_df, **upload_kwargs)
                    st.session_state[f"{scope}_plan"] = plan_df
                    st.session_state[f"{scope}_journal_preview"] = journal_new
                    st.session_state.pop(f"{scope}_merged", None)
                    st.session_state[f"{scope}_live"] = {
                        "bankroll": live.ccs.bankroll,
                        "unit_eur": live.ccs.current_unit_eur,
                        "equity_u": live.strategy.equity_u,
                        "dd_u": live.strategy.equity_u - live.strategy.peak_u,
                    }
            except Exception as e:
                st.error(f"Errore lettura file: {e}")

    plan_df = st.session_state.get(f"{scope}_plan")
    merged = st.session_state.get(f"{scope}_merged")
    live_info = st.session_state.get(f"{scope}_live")

    if merged is not None and not merged.empty:
        with st.expander("Riepilogo merge segnali", expanded=False):
            merge_cols = [
                {"key": "data", "label": "Data", "kind": "text"},
                {"key": "ora", "label": "Ora", "kind": "text"},
                {"key": "campionato", "label": "Campionato", "kind": "text_muted"},
                {"key": "partita", "label": "Partita", "kind": "text"},
                {"key": "strategia", "label": "Strategia", "kind": "pill"},
                {"key": "patterns_str", "label": "Pattern", "kind": "text_muted"},
                {"key": "segnali", "label": "Segnali", "kind": "badge"},
                {"key": "fonti", "label": "Fonti", "kind": "text_muted"},
            ]
            show_merged = merged.copy()
            if "data" in show_merged.columns:
                show_merged["data"] = pd.to_datetime(show_merged["data"]).dt.strftime("%Y-%m-%d")
            show_cols = ["data", "ora", "campionato", "partita", "strategia", "segnali", "fonti"]
            if "patterns_str" in show_merged.columns:
                show_cols.insert(5, "patterns_str")
            render_simple_table(
                show_merged[show_cols],
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
                    f"Stake: <b>{r['stake_eur']:.2f} €</b> ({r['stake_u']:.2f}U @ {r['valore_1u']:.2f} €/U)<br>"
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

        if st.button("💾 Salva nel journal", type="primary", key=f"{scope}_save_journal"):
            save_journal(st.session_state[f"{scope}_journal_preview"])
            st.success("Journal aggiornato.")
            st.session_state.pop(f"{scope}_plan", None)
            st.session_state.pop(f"{scope}_journal_preview", None)
            st.session_state.pop(f"{scope}_merged", None)
            st.rerun()

    st.divider()
    render_journal_section(
        load_journal(),
        bankroll_input,
        initial_bankroll,
        key_prefix=f"{scope}_jn",
        strategia_filter=journal_strategia_filter,
        title="Journal trade",
        tier_plan=tier_plan,
    )


def show_daily_trades_tab(initial_bankroll: float):
    render_daily_trades_panel(
        scope="dt",
        title="Trade del Giorno",
        subtitle=(
            "Strategia <b>combinata</b> + CCS (Controlled Compounding). "
            "Stake fisso 1U a scaglioni · Carica i file Fixtures (HT / Over 1.5 / Over 2.5 / 0 SH)."
        ),
        initial_bankroll=initial_bankroll,
        allowed_systems=None,
        forced_system=None,
        journal_strategia_filter=None,
        fixture_hint=DEFAULT_FIXTURE_HINT,
    )
