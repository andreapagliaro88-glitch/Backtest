"""UI tab Compound € con Controlled Compounding System."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.ccs_monte_carlo import run_ccs_monte_carlo
from core.ccs_runner import trades_to_ccs_inputs
from core.strategy_engine import iter_combined_trades
from ui.plot_theme import plot_histogram, plot_line


def _normalize_ccs_data(ccs_data) -> dict:
    """Accetta dict serializzato o oggetto ControlledCompounding (legacy)."""
    if isinstance(ccs_data, dict) and "summary" in ccs_data:
        return ccs_data
    if hasattr(ccs_data, "summary"):
        return {
            "summary": ccs_data.summary(),
            "withdrawals": ccs_data.withdrawals_dataframe_rows(),
            "tiers": ccs_data.tiers_dataframe_rows(),
        }
    raise TypeError("ccs_data deve essere un dict CCS o ControlledCompounding")


def show_ccs_compound_tab(df_trades, ccs_data, initial_bankroll, df_grouped=None, df_raw=None):
    if df_trades.empty:
        st.warning("Nessun dato compound disponibile.")
        return

    data = _normalize_ccs_data(ccs_data)
    s = data["summary"]
    withdrawals = data.get("withdrawals") or []
    tiers = data.get("tiers") or []
    active = df_trades[df_trades["stake_eur"] > 0]

    st.markdown("### Controlled Compounding System (CCS)")
    st.caption(
        "1U a scaglioni fissi · stake = U tier × 1U · upgrade solo fuori DD · "
        f"downgrade dopo 50 trade sotto scaglione · prelievo a 6000€"
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bankroll finale", f"{s['final_bankroll']:,.2f} €")
    c2.metric("Profitto totale", f"{s['total_profit_eur']:,.2f} €")
    c3.metric("ROI", f"{s['roi_pct']:.2f}%")
    c4.metric("Prelievi", f"{s['n_withdrawals']} ({s['total_withdrawn']:,.0f} €)")
    c5.metric("Max DD", f"{s['max_dd_eur']:,.2f} €")
    c6.metric("1U attuale", f"{s['current_unit_eur']:.2f} €")

    c7, c8, c9 = st.columns(3)
    c7.metric("Bankroll iniziale", f"{initial_bankroll:,.2f} €")
    c8.metric("Trade", s["trades"])
    c9.metric("Winrate", f"{s['winrate'] * 100:.1f}%")

    col_eq1, col_eq2 = st.columns(2)
    with col_eq1:
        plot_line(active, y="bankroll", title="Bankroll curve (€)", color="#58a6ff", fill=True, key="ccs_bankroll")
    with col_eq2:
        y_eq = "equity_eur" if "equity_eur" in active.columns else "bankroll"
        plot_line(active, y=y_eq, title="Equity curve (€)", color="#3fb950", fill=True, key="ccs_equity")

    col1, col2 = st.columns(2)
    with col1:
        plot_line(
            active, y="dd_eur", title="Drawdown (€)", color="#f85149",
            fill_to_zero=True, key="ccs_dd_eur",
        )
    with col2:
        plot_line(
            active, y="dd_pct", title="Drawdown (%)", color="#d29922",
            fill_to_zero=True, key="ccs_dd_pct",
        )

    if withdrawals:
        st.markdown("#### Prelievi")
        st.dataframe(pd.DataFrame(withdrawals), use_container_width=True, hide_index=True)

    st.markdown("#### Scaglioni 1U raggiunti")
    st.dataframe(pd.DataFrame(tiers), use_container_width=True, hide_index=True)

    with st.expander("Tabella trade compound"):
        st.dataframe(df_trades, use_container_width=True)

    if df_grouped is not None and df_raw is not None:
        st.markdown("---")
        st.markdown("#### Monte Carlo (robustezza ordine trade)")
        n_sim = st.slider("Simulazioni", 500, 5000, 1000, 500, key="ccs_mc_n")
        if st.button("Esegui Monte Carlo", type="primary", key="ccs_mc_run"):
            trades = list(iter_combined_trades(df_grouped, df_raw))
            inputs = trades_to_ccs_inputs(trades)
            with st.spinner(f"Rimescolamento {n_sim} volte..."):
                mc = run_ccs_monte_carlo(inputs, initial_bankroll, n_simulations=n_sim)
            st.session_state["ccs_mc_results"] = {
                k: v for k, v in mc.items() if not k.startswith("distribution_")
            }
            st.session_state["ccs_mc_profit_dist"] = mc.get("distribution_profit")

        mc = st.session_state.get("ccs_mc_results")
        profit_dist = st.session_state.get("ccs_mc_profit_dist")
        if mc and mc.get("n_simulations"):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Profitto medio", f"{mc['profit_mean']:,.0f} €")
            m2.metric("IC 90% profitto", f"{mc['profit_p5']:,.0f} – {mc['profit_p95']:,.0f} €")
            m3.metric("Prob. rovina", f"{mc['ruin_probability'] * 100:.1f}%")
            m4.metric("DD medio", f"{mc['max_dd_mean']:,.0f} €")

            plot_histogram(
                profit_dist,
                title="Distribuzione profitto finale (simulazioni)",
                color="#58a6ff",
                key="ccs_mc_hist",
            )

            st.caption(
                f"Bankroll finale: media {mc['final_bankroll_mean']:,.0f} € · "
                f"mediana {mc['final_bankroll_median']:,.0f} € · "
                f"IC90% {mc['final_bankroll_p5']:,.0f} – {mc['final_bankroll_p95']:,.0f} €"
            )
