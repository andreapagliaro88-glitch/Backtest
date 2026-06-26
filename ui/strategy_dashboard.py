"""Dashboard riutilizzabile: backtest + combinazioni pattern + ottimizza stake."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
import streamlit as st

from compound_config import INITIAL_BANKROLL
from core.ccs_runner import enrich_trades_with_eur, format_trades_eur_display, run_ccs_on_backtest_df
from core.pattern_combo_optimizer import best_combos, list_available_patterns, optimize_pattern_combos
from ui.plot_theme import plot_bar, plot_line
from ui.tier_metodo import (
    active_tier_rules,
    format_stakes_summary,
    render_stake_simulator,
    render_tier_optimizer,
    show_active_config_banner,
    show_tier_metodo_panel,
    stakes_fingerprint,
    supports_tier,
)

STRATEGY_CSS = """
<style>
    .strat-best {
        background: #0d1f14; border: 1px solid #238636; border-radius: 10px;
        padding: 0.75rem 1rem; margin-bottom: 0.5rem;
    }
</style>
"""


@dataclass
class StrategyConfig:
    key: str
    title: str
    data_hint: str
    system: str | None
    run_backtest: Callable
    optimize_stake: Callable
    format_params: Callable
    optimize_combos: Callable | None = None
    df_raw: pd.DataFrame | None = None
    df_grouped: pd.DataFrame | None = None
    stake_label: str = "Ottimizza stake"


def _ccs_metric_cards(ccs, initial_bankroll: float):
    s = ccs.summary()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bankroll finale", f"{s['final_bankroll']:,.2f} €")
    c2.metric("Profitto totale", f"{s['total_profit_eur']:,.2f} €")
    c3.metric("ROI", f"{s['roi_pct']:.2f}%")
    c4.metric("Max DD", f"{s['max_dd_eur']:,.2f} €")
    c5.metric("1U attuale", f"{s['current_unit_eur']:.2f} €")
    c6.metric("Prelievi", f"{s['n_withdrawals']} ({s['total_withdrawn']:,.0f} €)")
    c7, c8, c9 = st.columns(3)
    c7.metric("Bankroll iniziale", f"{initial_bankroll:,.2f} €")
    c8.metric("Trade CCS", s["trades"])
    c9.metric("Winrate", f"{s['winrate'] * 100:.1f}%")


def _ccs_equity_charts(df_ccs: pd.DataFrame, title: str, key_prefix: str = "ccs"):
    if df_ccs.empty:
        st.warning("Nessun trade CCS (bankroll insufficiente o nessun ingresso).")
        return

    col1, col2 = st.columns(2)
    with col1:
        plot_line(
            df_ccs, y="bankroll", title=f"Bankroll — {title}",
            color="#58a6ff", fill=True, key=f"{key_prefix}_bankroll",
        )
    with col2:
        y_eq = "equity_eur" if "equity_eur" in df_ccs.columns else "bankroll"
        plot_line(
            df_ccs, y=y_eq, title=f"Equity — {title}",
            color="#3fb950", fill=True, key=f"{key_prefix}_equity",
        )

    col3, col4 = st.columns(2)
    with col3:
        plot_line(df_ccs, y="dd_eur", title="Drawdown (€)", color="#f85149", key=f"{key_prefix}_dd_eur")
    with col4:
        plot_line(df_ccs, y="dd_pct", title="Drawdown (%)", color="#d29922", key=f"{key_prefix}_dd_pct")

    monthly = df_ccs.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit_eur"].sum().reset_index()
    monthly_profit["date"] = monthly_profit["date"].astype(str)
    plot_bar(
        monthly_profit, x="date", y="profit_eur",
        title=f"Profitto mensile (€) — {title}", color="#58a6ff",
        key=f"{key_prefix}_monthly",
    )


def _render_ccs_backtest(
    df_trades: pd.DataFrame,
    title: str,
    cfg_key: str,
    section: str = "bt",
):
    """Backtest con CCS: la strategia decide gli ingressi, CCS gestisce 1U in €."""
    prefix = f"{cfg_key}_{section}"
    bankroll = st.number_input(
        "Bankroll iniziale (€)",
        min_value=50.0,
        value=float(INITIAL_BANKROLL),
        step=50.0,
        key=f"{prefix}_bankroll_in",
    )
    st.caption(
        "Controlled Compounding: ingressi dalla strategia (stake U > 0) · "
        "stake reale sempre 1U · scaglioni fissi · prelievo a 6000€"
    )

    df_ccs, ccs = run_ccs_on_backtest_df(df_trades, bankroll)
    _ccs_metric_cards(ccs, bankroll)
    _ccs_equity_charts(df_ccs, title, key_prefix=f"{prefix}_plot")

    if ccs.withdrawals:
        with st.expander("Prelievi CCS"):
            st.dataframe(pd.DataFrame(ccs.withdrawals_dataframe_rows()), use_container_width=True, hide_index=True)

    if ccs.tiers_reached:
        with st.expander("Scaglioni 1U raggiunti"):
            st.dataframe(pd.DataFrame(ccs.tiers_dataframe_rows()), use_container_width=True, hide_index=True)

    df_display = enrich_trades_with_eur(df_trades, df_ccs)
    n_skip = int((df_display["ingresso"] == "SKIP").sum()) if not df_display.empty else 0
    expand_trades = supports_tier(cfg_key)
    with st.expander("Dettaglio trade (€)", expanded=expand_trades):
        if n_skip:
            st.caption(f"Ingressi: {len(df_ccs)} · Saltati dalla strategia: {n_skip}")
        if supports_tier(cfg_key) and not df_display.empty and "patterns_str" in df_display.columns:
            skip_pat = df_display.loc[df_display["ingresso"] == "SKIP", "patterns_str"]
            if not skip_pat.empty:
                top_skip = skip_pat.value_counts().head(5)
                st.caption(
                    "Pattern più saltati: "
                    + " · ".join(f"{p} ({n})" for p, n in top_skip.items())
                )
        st.dataframe(format_trades_eur_display(df_display), use_container_width=True, hide_index=True)


SECTIONS = ("📈 Backtest attuale", "🧩 Combinazioni pattern", "⚙️ Ottimizza stake")


def active_patterns_key(cfg_key: str) -> str:
    return f"{cfg_key}_active_patterns"


def active_combo_label_key(cfg_key: str) -> str:
    return f"{cfg_key}_active_combo_label"


def patterns_from_combo_row(row) -> tuple[str, ...] | None:
    raw = row.get("patterns")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    return tuple(raw) if not isinstance(raw, tuple) else raw


def patterns_dirty_key(cfg_key: str) -> str:
    return f"{cfg_key}_patterns_dirty"


def bt_patterns_key(cfg_key: str) -> str:
    return f"{cfg_key}_bt_patterns"


def _sync_bt_patterns_widget(cfg_key: str, options: list[str]) -> None:
    """Aggiorna il multiselect backtest solo prima che il widget venga creato."""
    if not st.session_state.get(patterns_dirty_key(cfg_key)):
        return
    active = st.session_state.get(active_patterns_key(cfg_key))
    if active:
        st.session_state[bt_patterns_key(cfg_key)] = [p for p in active if p in options]
    st.session_state.pop(patterns_dirty_key(cfg_key), None)


def set_active_combo(cfg_key: str, patterns: tuple[str, ...] | None, combo_label: str = ""):
    if patterns:
        st.session_state[active_patterns_key(cfg_key)] = tuple(patterns)
        st.session_state[active_combo_label_key(cfg_key)] = combo_label
        st.session_state[patterns_dirty_key(cfg_key)] = True
    else:
        st.session_state.pop(active_patterns_key(cfg_key), None)
        st.session_state.pop(active_combo_label_key(cfg_key), None)


def get_active_combo_label(cfg_key: str) -> str | None:
    return st.session_state.get(active_combo_label_key(cfg_key))


def _render_combo_tab(cfg: StrategyConfig, patterns: list[str], df_raw: pd.DataFrame):
    st.markdown("### Tutte le combinazioni di pattern")

    if supports_tier(cfg.system):
        rules = active_tier_rules(cfg.key, cfg.system)
        show_active_config_banner(cfg.key, cfg.system, always=True)
        st.caption(
            "Questa tab confronta **quali pattern includere**. "
            "Profit/DD/Score usano gli **stake sopra**. "
            "Dopo nuovi stake in **Simula stake**, clicca **Calcola combinazioni**."
        )
        combo_fp = st.session_state.get(f"{cfg.key}_combo_stakes_fp")
        if combo_fp and combo_fp != stakes_fingerprint(cfg.key, cfg.system, rules):
            st.warning(
                "⚠️ Gli stake sono cambiati dall'ultimo calcolo combinazioni. "
                "Clicca **Calcola combinazioni** per aggiornare i numeri in tabella."
            )
        elif st.session_state.get(f"{cfg.key}_combo_stale"):
            st.warning(
                "⚠️ Hai applicato una nuova configurazione stake. "
                "Clicca **Calcola combinazioni** per vedere i risultati aggiornati."
            )

    if not patterns:
        st.error(
            "Nessun pattern rilevato nei file Excel. "
            "Verifica che i file siano in `data/ht/`, `data/over15/` o `data/over25/` "
            "e clicca **Aggiorna dati** in alto."
        )
        return

    n_combos = (2 ** len(patterns) - 1) if patterns else 0
    st.caption(
        f"Fino a {n_combos} combinazioni testate. Score = Profit + 0.6 × Max DD."
    )

    combo_key = f"{cfg.key}_combo_results"

    if st.button("🔍 Calcola combinazioni", type="primary", key=f"{cfg.key}_run_combos"):
        with st.spinner("Calcolo in corso..."):
            try:
                if supports_tier(cfg.system):
                    tier_rules = active_tier_rules(cfg.key, cfg.system)
                    sys_df = df_raw[df_raw["system"] == cfg.system].copy() if "system" in df_raw.columns else df_raw
                    combo_df = optimize_pattern_combos(
                        sys_df,
                        lambda d, p: cfg.run_backtest(d, p, tier_rules=tier_rules),
                        patterns=patterns,
                    )
                    st.session_state[f"{cfg.key}_combo_stakes_fp"] = stakes_fingerprint(cfg.key, cfg.system, tier_rules)
                    st.session_state[f"{cfg.key}_combo_stakes_label"] = format_stakes_summary(cfg.key, cfg.system, tier_rules)
                    st.session_state[f"{cfg.key}_combo_stale"] = False
                elif cfg.optimize_combos:
                    combo_df = cfg.optimize_combos(df_raw)
                else:
                    combo_df = optimize_pattern_combos(
                        df_raw,
                        lambda d, p: cfg.run_backtest(d, p),
                        patterns=patterns,
                        system=cfg.system,
                    )
                st.session_state[combo_key] = combo_df
                st.session_state[f"{cfg.key}_section"] = "🧩 Combinazioni pattern"
                if combo_df is not None and not combo_df.empty:
                    best = combo_df.sort_values("score", ascending=False).iloc[0]
                    pats = patterns_from_combo_row(best)
                    set_active_combo(cfg.key, pats, str(best.get("combo", "")))
                    st.toast(
                        f"✅ {len(combo_df)} combinazioni — riepilogo aggiornato: {best['combo']}",
                        icon="✅",
                    )
                    st.rerun()
                else:
                    st.warning("Nessuna combinazione ha prodotto risultati.")
            except Exception as exc:
                st.error(f"Errore nel calcolo combinazioni: {exc}")

    combo_df = st.session_state.get(combo_key)
    if combo_df is None or combo_df.empty:
        st.info("Clicca **Calcola combinazioni** per avviare la ricerca.")
        return

    if supports_tier(cfg.system):
        stakes_label = st.session_state.get(f"{cfg.key}_combo_stakes_label") or format_stakes_summary(cfg.key, cfg.system)
        st.markdown(f"**Stake usati nel calcolo:** `{stakes_label}`")

    bests = best_combos(combo_df)
    cols = st.columns(4)
    for col, (label, bkey) in zip(cols, [
        ("Miglior score", "score"),
        ("Max profitto", "profit"),
        ("Min drawdown", "min_dd"),
        ("Miglior Calmar", "calmar"),
    ]):
        row = bests[bkey]
        with col:
            st.markdown(f"**{label}**")
            st.markdown(
                f'<div class="strat-best"><b>{row["combo"]}</b><br>'
                f'Profit {row["profit"]:.1f} U · DD {row["max_dd"]:.1f} U · '
                f'{int(row["trades"])} trade</div>',
                unsafe_allow_html=True,
            )

    sort_by = st.selectbox(
        "Ordina per",
        ["score", "profit", "max_dd", "calmar", "winrate", "trades"],
        key=f"{cfg.key}_combo_sort",
    )
    ascending = sort_by == "max_dd"
    view = combo_df.sort_values(sort_by, ascending=ascending).copy()
    view["winrate"] = (view["winrate"] * 100).round(1)
    if supports_tier(cfg.system):
        show_cols = ["combo", "stakes_used", "n_patterns", "profit", "max_dd", "score", "calmar", "trades", "winrate"]
        view["stakes_used"] = st.session_state.get(f"{cfg.key}_combo_stakes_label") or format_stakes_summary(cfg.key, cfg.system)
    else:
        show_cols = ["combo", "n_patterns", "profit", "max_dd", "score", "calmar", "trades", "winrate"]
    show_cols = [c for c in show_cols if c in view.columns]
    view = view[show_cols]
    col_names = {
        "combo": "Combinazione",
        "stakes_used": "Stake T1/T2/T3/T4",
        "n_patterns": "N° pattern",
        "profit": "Profit (U)",
        "max_dd": "Max DD (U)",
        "score": "Score",
        "calmar": "Calmar",
        "trades": "Trade",
        "winrate": "Winrate %",
    }
    view.columns = [col_names.get(c, c) for c in show_cols]
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.download_button(
        "📥 Scarica CSV combinazioni",
        combo_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{cfg.key}_combo_optimization.csv",
        mime="text/csv",
        key=f"{cfg.key}_dl_combo",
    )

    active_label = get_active_combo_label(cfg.key)
    if active_label:
        st.info(f"**Riepilogo in alto:** {active_label}")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        sel_combo = st.selectbox(
            "Combinazione per riepilogo",
            combo_df["combo"].tolist(),
            index=combo_df["combo"].tolist().index(active_label)
            if active_label in combo_df["combo"].tolist() else 0,
            key=f"{cfg.key}_combo_summary_pick",
        )
    with col_b:
        st.write("")
        st.write("")
        if st.button("Applica al riepilogo", type="primary", key=f"{cfg.key}_apply_summary"):
            row = combo_df[combo_df["combo"] == sel_combo].iloc[0]
            set_active_combo(cfg.key, patterns_from_combo_row(row), sel_combo)
            st.rerun()

    pat_row = combo_df[combo_df["combo"] == sel_combo].iloc[0]

    if cfg.key == "combined":
        detail_trades = cfg.run_backtest(
            df_raw,
            pat_row.get("ht_patterns") or None,
            pat_row.get("o15_patterns") or None,
            pat_row.get("o25_patterns") or None,
        )
    else:
        raw_pats = pat_row.get("patterns")
        if raw_pats is None or (isinstance(raw_pats, float) and pd.isna(raw_pats)):
            pat_tuple = None
        elif isinstance(raw_pats, tuple):
            pat_tuple = raw_pats
        else:
            pat_tuple = tuple(raw_pats)
        if supports_tier(cfg.system):
            detail_trades = cfg.run_backtest(df_raw, pat_tuple, tier_rules=active_tier_rules(cfg.key, cfg.system))
        else:
            detail_trades = cfg.run_backtest(df_raw, pat_tuple)
    _render_ccs_backtest(detail_trades, sel_combo, cfg.key, section="combo")


def _render_stake_tab(cfg: StrategyConfig, patterns: list[str], df_raw: pd.DataFrame):
    st.markdown("### Ottimizzazione parametri")
    opt_patterns = st.multiselect(
        "Pattern attivi",
        options=patterns,
        default=patterns,
        key=f"{cfg.key}_opt_patterns",
    ) if patterns else []
    iterations = st.slider("Iterazioni", 500, 5000, 2000, 500, key=f"{cfg.key}_opt_iter")
    aggressive = False
    max_dd = -999.0
    if cfg.key in ("sh0", "sh1", "sh2"):
        dd_default = -18.0
        max_dd = st.number_input("Filtro DD minimo", value=dd_default, step=1.0, key=f"{cfg.key}_opt_dd")
    elif cfg.key == "o15":
        aggressive = st.checkbox("Modalità aggressiva", key=f"{cfg.key}_opt_agg")
        max_dd = st.number_input("Filtro DD minimo", value=-999.0, step=1.0, key=f"{cfg.key}_opt_dd")

    if st.button(f"⚙️ {cfg.stake_label}", type="primary", key=f"{cfg.key}_run_opt"):
        with st.spinner(f"Test {iterations} configurazioni..."):
            pat = tuple(opt_patterns) if opt_patterns else None
            dd_limit = None if max_dd <= -900 else max_dd
            kwargs = {"iterations": iterations}
            if cfg.key == "combined":
                baseline, results = cfg.optimize_stake(cfg.df_grouped, df_raw, iterations=iterations)
            elif cfg.key == "o15":
                baseline, results = cfg.optimize_stake(
                    df_raw, patterns=pat, iterations=iterations,
                    aggressive=aggressive, max_dd_limit=dd_limit,
                )
            elif cfg.key in ("sh0", "sh1", "sh2"):
                baseline, results = cfg.optimize_stake(
                    df_raw, patterns=pat, iterations=iterations, max_dd_limit=dd_limit,
                )
            else:
                baseline, results = cfg.optimize_stake(df_raw, patterns=pat, iterations=iterations)
            st.session_state[f"{cfg.key}_opt_baseline"] = baseline
            st.session_state[f"{cfg.key}_opt_results"] = results

    baseline = st.session_state.get(f"{cfg.key}_opt_baseline")
    results = st.session_state.get(f"{cfg.key}_opt_results")

    if baseline and results is not None and not results.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Baseline (attuale)**")
            st.write(
                f"Profit {baseline['profit']:.2f} U · DD {baseline['max_dd']:.2f} U · "
                f"Score {baseline['score']:.2f}"
            )
            st.caption(cfg.format_params(baseline["params"]))
        with c2:
            best = results.iloc[0]
            st.markdown("**Migliore (#1 per score)**")
            st.write(
                f"Profit {best['profit']:.2f} U · DD {best['max_dd']:.2f} U · "
                f"Score {best['score']:.2f} · Calmar {best['calmar']:.2f}"
            )
            st.caption(cfg.format_params(best["params"]))

        show = results.head(20).copy()
        show["winrate"] = (show["winrate"] * 100).round(1)
        show["params_str"] = show["params"].apply(cfg.format_params)
        st.dataframe(
            show[["profit", "max_dd", "score", "calmar", "trades", "winrate", "params_str"]],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "📥 Scarica CSV ottimizzazione",
            results.to_csv(index=False).encode("utf-8"),
            file_name=f"{cfg.key}_optimization.csv",
            mime="text/csv",
            key=f"{cfg.key}_dl_opt",
        )
    elif results is not None and results.empty:
        st.warning("Nessun risultato con i filtri impostati.")
    else:
        st.info(f"Clicca **{cfg.stake_label}** per avviare la ricerca.")


def show_strategy_tab(cfg: StrategyConfig):
    st.markdown(STRATEGY_CSS, unsafe_allow_html=True)
    st.markdown(f"### {cfg.title}")
    st.caption(cfg.data_hint)

    df_raw = cfg.df_raw if cfg.df_raw is not None else pd.DataFrame()
    if df_raw.empty and cfg.key != "combined":
        st.warning(f"Nessun dato per {cfg.title}. Carica file Excel in `data/`.")
        return
    if cfg.key == "combined" and df_raw.empty:
        st.warning("Nessun dato Combined. Carica file in `data/ht`, `data/over15`, `data/over25`.")
        return

    if cfg.system:
        patterns = list_available_patterns(df_raw, cfg.system)
        sub = df_raw[df_raw["system"] == cfg.system]
        st.caption(
            f"{len(sub):,} righe · {sub['match_id'].nunique():,} partite · "
            f"Pattern: {', '.join(patterns) if patterns else '—'}"
        )
    else:
        patterns = []
        for sys in ("HT", "O15", "O25"):
            p = list_available_patterns(df_raw, sys)
            if p:
                patterns.extend([f"{sys}:{x}" for x in p])
        st.caption(f"Dati combinati HT + O15 + O25 · {len(df_raw):,} righe totali")

    tier_extra = ["🎯 Ottimizza tier", "⚖️ Simula stake"] if supports_tier(cfg.system) else []
    tab_bt, tab_combo, tab_opt, *extra = st.tabs(list(SECTIONS) + tier_extra)
    tab_tier = extra[0] if supports_tier(cfg.system) else None
    tab_stake_sim = extra[1] if supports_tier(cfg.system) else None

    if st.session_state.get(f"{cfg.key}_combo_results") is not None:
        done = st.session_state.get(f"{cfg.key}_combo_results")
        if done is not None and not done.empty:
            st.success(
                f"Combinazioni pronte ({len(done)} risultati) — apri **Combinazioni pattern**",
                icon="✅",
            )

    with tab_bt:
        if cfg.system and patterns:
            pat_options = list_available_patterns(df_raw, cfg.system)
            _sync_bt_patterns_widget(cfg.key, pat_options)
            bt_key = bt_patterns_key(cfg.key)
            if bt_key not in st.session_state:
                active = st.session_state.get(active_patterns_key(cfg.key))
                fallback = [p for p in (active or pat_options) if p in pat_options] or pat_options
                st.session_state[bt_key] = fallback
            sel = st.multiselect(
                "Pattern attivi (vuoto = tutti)",
                options=pat_options,
                key=bt_key,
            )
            pat = tuple(sel) if sel else None
            tier_rules = active_tier_rules(cfg.key, cfg.system) if supports_tier(cfg.system) else None
            if supports_tier(cfg.system):
                df_trades = cfg.run_backtest(df_raw, pat, tier_rules=tier_rules)
            else:
                df_trades = cfg.run_backtest(df_raw, pat)
            if st.button("Usa questi pattern nel riepilogo", key=f"{cfg.key}_bt_apply_summary"):
                set_active_combo(
                    cfg.key,
                    pat,
                    " + ".join(sel) if sel else "Tutti i pattern",
                )
                st.rerun()
        elif cfg.key == "combined":
            df_trades = cfg.run_backtest(df_raw)
        else:
            tier_rules = active_tier_rules(cfg.key, cfg.system) if supports_tier(cfg.system) else None
            if supports_tier(cfg.system):
                df_trades = cfg.run_backtest(df_raw, tier_rules=tier_rules)
            else:
                df_trades = cfg.run_backtest(df_raw)
        if supports_tier(cfg.system):
            show_tier_metodo_panel(cfg.key, cfg.system, cfg.title.split("—")[0].strip(), df_trades, df_raw)
        _render_ccs_backtest(df_trades, cfg.title, cfg.key, section="bt")

    with tab_combo:
        pat_list = list_available_patterns(df_raw, cfg.system) if cfg.system else patterns
        _render_combo_tab(cfg, pat_list, df_raw)

    with tab_opt:
        pat_list = list_available_patterns(df_raw, cfg.system) if cfg.system else []
        _render_stake_tab(cfg, pat_list, df_raw)

    if tab_tier is not None:
        with tab_tier:
            render_tier_optimizer(cfg.key, cfg.system, cfg.title.split("—")[0].strip(), df_raw)

    if tab_stake_sim is not None:
        with tab_stake_sim:
            render_stake_simulator(cfg.key, cfg.system, cfg.title.split("—")[0].strip(), df_raw)
