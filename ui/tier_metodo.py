"""Pannello Metodo Tier + ottimizzatori — tutte le strategie con pattern."""
from __future__ import annotations

from dataclasses import replace

import streamlit as st

from core.tier_backtest import tier_summary
from core.strategy_state_store import persist_from_session
from core.tier_config import TIER_SYSTEMS, default_tier_rules
from core.tier_engine import TIER_LABELS, any_pattern_matches
from core.tier_optimizer import (
    list_patterns_for_system,
    optimize_pattern_tiers,
    tier_rules_from_dict,
    tier_rules_to_dict,
)
from ui.metric_table import (
    STAKE_SIM_COLUMNS,
    TIER_OPT_COLUMNS,
    TIER_SUMMARY_COLUMNS,
    render_metric_table,
    render_simple_table,
)


def supports_tier(system: str | None) -> bool:
    return system in TIER_SYSTEMS


def _rules_key(cfg_key: str) -> str:
    return f"{cfg_key}_tier_rules_dict"


def active_tier_rules(cfg_key: str, system: str):
    data = st.session_state.get(_rules_key(cfg_key))
    if data:
        return tier_rules_from_dict(data)
    return default_tier_rules(system)


def format_stakes_summary(cfg_key: str, system: str, rules=None) -> str:
    rules = rules or active_tier_rules(cfg_key, system)
    return (
        f"T1={rules.stake_t1}U · T2={rules.stake_t2}U · "
        f"T3={rules.stake_t3}U · T4={rules.stake_t4}U"
    )


def stakes_fingerprint(cfg_key: str, system: str, rules=None) -> str:
    rules = rules or active_tier_rules(cfg_key, system)
    t3 = "+".join(sorted(rules.tier3_patterns))
    t4 = "+".join(sorted(rules.tier4_patterns))
    return f"{rules.stake_t1}|{rules.stake_t2}|{rules.stake_t3}|{rules.stake_t4}|{t3}|{t4}"


def mark_combos_stale(cfg_key: str):
    st.session_state[f"{cfg_key}_combo_stale"] = True


def apply_tier_rules(cfg_key: str, rules_dict: dict):
    """Applica regole complete (es. assegnazione pattern T3/T4 da ottimizzatore tier)."""
    st.session_state[_rules_key(cfg_key)] = rules_dict
    st.session_state[f"{cfg_key}_workflow_tier_done"] = True
    mark_combos_stale(cfg_key)
    persist_from_session(cfg_key, st.session_state)


def apply_stake_rules(cfg_key: str, system: str, stake_row: dict):
    """Applica stake T1–T4; se la riga ha una combinazione pattern, la imposta anche nel riepilogo."""
    current = active_tier_rules(cfg_key, system)
    updated = replace(
        current,
        stake_t1=float(stake_row["stake_t1"]),
        stake_t2=float(stake_row["stake_t2"]),
        stake_t3=float(stake_row["stake_t3"]),
        stake_t4=float(stake_row["stake_t4"]),
    )
    st.session_state[_rules_key(cfg_key)] = tier_rules_to_dict(updated)
    st.session_state[f"{cfg_key}_workflow_stake_done"] = True
    mark_combos_stale(cfg_key)

    patterns = stake_row.get("patterns")
    combo_name = stake_row.get("combo")
    if patterns and combo_name:
        from ui.strategy_dashboard import set_active_combo
        pats = tuple(patterns) if not isinstance(patterns, tuple) else patterns
        set_active_combo(cfg_key, pats, str(combo_name))
    else:
        persist_from_session(cfg_key, st.session_state)


def show_tier_workflow_guide(cfg_key: str, system: str):
    """Flusso consigliato: tier → stake → combinazioni pattern."""
    tier_done = st.session_state.get(f"{cfg_key}_workflow_tier_done") or st.session_state.get(_rules_key(cfg_key))
    stake_done = st.session_state.get(f"{cfg_key}_workflow_stake_done")

    st.info(
        "**Flusso consigliato**\n\n"
        "1. **🎯 Ottimizza tier** — quali pattern in T3 / T4 / esclusi\n"
        "2. **⚖️ Simula stake** — confronta **ogni combinazione** di pattern (N → 1) con le stake attuali\n"
        "3. **🧩 Combinazioni pattern** — quale subset di pattern usare (con stake già impostate)\n\n"
        f"Stato: tier {'✅' if tier_done else '⬜'} · stake {'✅' if stake_done else '⬜'} · "
        "combinazioni in **Combinazioni pattern** (tutte: da N a 1 file)"
    )


def show_active_config_banner(cfg_key: str, system: str, *, always: bool = False):
    rules = active_tier_rules(cfg_key, system)
    custom = bool(st.session_state.get(_rules_key(cfg_key)))
    if not custom and not always:
        return
    title = "Configurazione stake applicata" if custom else "Stake in uso"
    st.success(
        f"**{title}** — {format_stakes_summary(cfg_key, system, rules)} · "
        f"T3: {', '.join(rules.tier3_patterns) or '—'} · "
        f"T4: {', '.join(rules.tier4_patterns) or '—'}"
    )


def show_tier_metodo_panel(cfg_key: str, system: str, strategy_label: str, df_trades=None, df_raw=None):
    rules = active_tier_rules(cfg_key, system)
    patterns = list_patterns_for_system(df_raw, system) if df_raw is not None else []

    st.markdown(f"#### Metodo {strategy_label} — Tier")

    if patterns:
        st.markdown(f"**Pattern rilevati ({len(patterns)}):**")
        st.code(" · ".join(patterns), language=None)
        uncovered = [
            p for p in patterns
            if not any_pattern_matches([p], rules.tier3_patterns + rules.tier4_patterns)
        ]
        if uncovered:
            st.warning(
                f"**{', '.join(uncovered)}** non è in T3/T4: a **1 engine** verranno **saltati**. "
                "Usa **🎯 Ottimizza tier** → **Calcola** → **Applica al backtest**."
            )
    else:
        st.warning("Nessun pattern trovato nei file Excel. Clicca **Aggiorna dati**.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"""
**Classificazione attiva**
- **T1** ({rules.stake_t1}U): 3+ engine
- **T2** ({rules.stake_t2}U): 2 engine
- **T3** ({rules.stake_t3}U): 1 engine — {", ".join(rules.tier3_patterns) or "—"}
- **T4** ({rules.stake_t4}U): 1 engine — {", ".join(rules.tier4_patterns) or "—"}
- **Skip**: 1 engine non in T3/T4
"""
        )
    with c2:
        st.markdown(
            """
**Rischio (unità backtest)**
- 2 loss → stop T4 (5 trade), T2/T3 −20%
- 3 loss → pausa shock (×0.6)
- **CCS**: stake in € = **Stake (U) × 1U** allo scaglione
"""
        )
        if st.session_state.get(_rules_key(cfg_key)):
            st.success(
                f"Configurazione personalizzata — **{format_stakes_summary(cfg_key, system, rules)}**"
            )

    if df_trades is not None and not df_trades.empty and "tier" in df_trades.columns:
        active = df_trades[df_trades["stake"] > 0]
        if "patterns_str" in df_trades.columns:
            with st.expander("Anteprima pattern nei trade", expanded=False):
                sample = df_trades[df_trades["patterns_str"].astype(str).str.len() > 0][
                    ["date", "tier_label", "patterns_str", "stake", "profit"]
                ].head(20)
                preview_cols = [
                    {"key": "date", "label": "Data", "kind": "text"},
                    {"key": "tier_label", "label": "Tier", "kind": "pill"},
                    {"key": "patterns_str", "label": "Pattern", "kind": "text_muted"},
                    {"key": "stake", "label": "Stake (U)", "kind": "text"},
                    {"key": "profit", "label": "Profit (U)", "kind": "profit_signed"},
                ]
                render_simple_table(sample, preview_cols, seed_col="patterns_str")
        summary = tier_summary(df_trades)
        if not summary.empty:
            st.markdown("**Performance per tier**")
            render_metric_table(summary, TIER_SUMMARY_COLUMNS, seed_col="Tier")
            if not active.empty and "tier" in active.columns:
                by_tier = active.groupby("tier").size()
                st.caption(
                    "Distribuzione trade: "
                    + " · ".join(f"{TIER_LABELS.get(int(t), f'T{t}')}: {n}" for t, n in by_tier.items())
                )


def render_tier_optimizer(cfg_key: str, system: str, strategy_label: str, df_raw):
    st.markdown(f"### Ottimizzatore tier — {strategy_label}")
    st.caption(
        "**Passo 1/3** — Backtest ogni pattern da solo → suggerisce **T3** (edge forte) "
        "vs **T4** (marginali) vs **esclusi**. Poi vai su **Simula stake**."
    )

    patterns = list_patterns_for_system(df_raw, system)
    if not patterns:
        st.error("Nessun pattern nei file Excel.")
        return

    st.info(f"Pattern disponibili: {', '.join(patterns)}")

    c1, c2, c3 = st.columns(3)
    min_trades = c1.number_input("Trade minimo", 5, 100, 10, key=f"{cfg_key}_tier_min_trades")
    q3 = c2.slider("Soglia T3 (quantile score)", 0.5, 0.95, 0.70, 0.05, key=f"{cfg_key}_tier_q3")
    q4 = c3.slider("Soglia T4 (quantile score)", 0.1, 0.6, 0.35, 0.05, key=f"{cfg_key}_tier_q4")

    if st.button("🔍 Calcola assegnazione tier", type="primary", key=f"{cfg_key}_run_tier_opt"):
        with st.spinner("Backtest per pattern..."):
            result_df, suggested = optimize_pattern_tiers(
                df_raw, system, min_trades=int(min_trades), t3_quantile=q3, t4_quantile=q4,
            )
            st.session_state[f"{cfg_key}_tier_opt_result"] = result_df
            st.session_state[f"{cfg_key}_tier_opt_suggested"] = tier_rules_to_dict(suggested)

    result_df = st.session_state.get(f"{cfg_key}_tier_opt_result")
    suggested_dict = st.session_state.get(f"{cfg_key}_tier_opt_suggested")

    if result_df is None or result_df.empty:
        st.info("Clicca **Calcola assegnazione tier**.")
        return

    show_cols = ["pattern", "suggested_tier", "trades", "profit", "max_dd", "score", "winrate_pct", "motivo"]
    show_cols = [c for c in show_cols if c in result_df.columns]
    render_metric_table(result_df[show_cols], TIER_OPT_COLUMNS, seed_col="pattern")

    if suggested_dict:
        t3 = suggested_dict.get("tier3_patterns", [])
        t4 = suggested_dict.get("tier4_patterns", [])
        excl = [p for p in patterns if p not in t3 and p not in t4]
        st.markdown("**Proposta**")
        st.markdown(f"- **T3:** {', '.join(t3) or '—'}")
        st.markdown(f"- **T4:** {', '.join(t4) or '—'}")
        st.markdown(f"- **Esclusi:** {', '.join(excl) or '—'}")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("✅ Applica al backtest", type="primary", key=f"{cfg_key}_apply_tier_rules"):
                apply_tier_rules(cfg_key, suggested_dict)
                st.success("Regole tier applicate. Ricalcola **Combinazioni pattern** se necessario.")
        with col_b:
            if st.button("↩️ Ripristina default", key=f"{cfg_key}_reset_tier_rules"):
                st.session_state.pop(_rules_key(cfg_key), None)
                st.session_state.pop(f"{cfg_key}_tier_opt_result", None)
                st.session_state.pop(f"{cfg_key}_workflow_tier_done", None)
                st.session_state.pop(f"{cfg_key}_workflow_stake_done", None)
                mark_combos_stale(cfg_key)
                st.success("Regole tier ripristinate ai default.")

        st.download_button(
            "📥 Scarica CSV",
            result_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{cfg_key}_tier_optimization.csv",
            mime="text/csv",
            key=f"{cfg_key}_dl_tier_opt",
        )


def render_stake_simulator(cfg_key: str, system: str, strategy_label: str, df_raw):
    from core.pattern_combo_optimizer import combos_per_size, count_pattern_combos
    from core.tier_stake_optimizer import format_stake_combo, simulate_stakes_by_pattern_combos
    from ui.plot_theme import plot_scatter

    st.markdown(f"### Simulazione stake — {strategy_label}")
    st.caption(
        "**Passo 2/3** — Confronta **ogni combinazione di pattern** (5, 4, 3, 2, 1 file) "
        "con le stake T1/T2/T3/T4 attuali. Poi **Combinazioni pattern**."
    )

    patterns = list_patterns_for_system(df_raw, system)
    if not patterns:
        st.error("Nessun pattern nei file Excel.")
        return

    n_pat = len(patterns)
    n_combos = count_pattern_combos(n_pat)
    per_size = combos_per_size(n_pat)
    breakdown = " + ".join(f"{k}×{v}" for k, v in sorted(per_size.items(), reverse=True))
    rules = active_tier_rules(cfg_key, system)
    st.info(
        f"Pattern: **{' + '.join(patterns)}** · "
        f"**{n_combos}** combinazioni ({breakdown}) · "
        f"Stake: **{format_stakes_summary(cfg_key, system, rules)}**"
    )

    c1, c2 = st.columns(2)
    dd_weight = c1.slider(
        "Penalità DD nello score", 0.2, 1.2, 0.6, 0.05,
        key=f"{cfg_key}_sim_dd_weight",
    )
    max_dd = c2.number_input(
        "Filtro DD minimo (U)", value=-999.0, step=1.0, key=f"{cfg_key}_sim_max_dd",
    )

    if st.button("⚖️ Avvia simulazione", type="primary", key=f"{cfg_key}_run_stake_sim"):
        progress = st.progress(0.0, text="Simulazione combinazioni…") if n_combos > 1 else None

        def _on_progress(p: float):
            if progress is not None:
                progress.progress(p, text=f"Simulazione combinazioni… {int(p * 100)}%")

        with st.spinner("Calcolo combinazioni in corso..."):
            baseline, results, best_per_combo, rules_all = simulate_stakes_by_pattern_combos(
                df_raw, system, rules,
                dd_weight=dd_weight,
                max_dd_limit=None if max_dd <= -900 else max_dd,
                progress_callback=_on_progress if progress else None,
            )
            st.session_state[f"{cfg_key}_stake_sim_baseline"] = baseline
            st.session_state[f"{cfg_key}_stake_sim_results"] = results
            st.session_state[f"{cfg_key}_stake_sim_best_combo"] = best_per_combo
            st.session_state[f"{cfg_key}_combo_stakes_label"] = format_stakes_summary(cfg_key, system, rules_all)
        if progress is not None:
            progress.empty()

    baseline = st.session_state.get(f"{cfg_key}_stake_sim_baseline")
    results = st.session_state.get(f"{cfg_key}_stake_sim_results")
    best_per_combo = st.session_state.get(f"{cfg_key}_stake_sim_best_combo")

    if baseline is None or results is None:
        st.info("Clicca **Avvia simulazione**.")
        return
    if results.empty:
        st.warning("Nessuna simulazione passa il filtro DD.")
        return

    size_options = ["Tutte le dimensioni"] + [f"{k} pattern" for k in range(n_pat, 0, -1)]
    size_filter = st.selectbox(
        "Filtra per n° pattern",
        size_options,
        key=f"{cfg_key}_sim_size_filter",
    )

    view_df = results

    if size_filter != "Tutte le dimensioni":
        try:
            n_filter = int(size_filter.split()[0])
            view_df = view_df[view_df["n_patterns"] == n_filter]
        except ValueError:
            pass

    if view_df.empty:
        st.warning("Nessun risultato con i filtri selezionati.")
        return

    best_score = view_df.iloc[0]
    best_profit = view_df.sort_values("profit", ascending=False).iloc[0]
    best_calmar = view_df.sort_values("calmar", ascending=False).iloc[0]

    st.markdown(f"**{len(view_df):,}** combinazioni mostrate")
    m1, m2, m3 = st.columns(3)
    for col, label, row in [(m1, "Miglior score", best_score), (m2, "Max profit", best_profit), (m3, "Miglior Calmar", best_calmar)]:
        with col:
            st.markdown(f"**{label}**")
            st.write(
                f"**{row.get('combo', '—')}** · Profit **{row['profit']:.1f}U** · "
                f"DD **{row['max_dd']:.1f}U** · Score **{row['score']:.1f}**"
            )
            st.caption(format_stake_combo(row))

    scatter = view_df.copy()
    scatter["max_dd_abs"] = scatter["max_dd"].abs()
    plot_scatter(
        scatter, x="max_dd_abs", y="profit", color="score",
        title="Profit vs Drawdown — per combinazione pattern",
        labels={"max_dd_abs": "Max DD (U)", "profit": "Profit (U)", "score": "Score"},
        hover_data=["combo", "n_patterns", "stake_t1", "stake_t2", "stake_t3", "stake_t4", "calmar", "trades"],
        key=f"{cfg_key}_stake_sim_scatter_{len(scatter)}",
    )

    show = view_df.copy()
    show["winrate_pct"] = (show["winrate"] * 100).round(1)
    show["stakes"] = show.apply(format_stake_combo, axis=1)
    show["#"] = range(1, len(show) + 1)
    st.caption(f"Tabella — **{len(show):,}** combinazioni (ordinate per score)")
    table_cols = ["#", "n_patterns", "combo", "stakes", "profit", "max_dd", "score", "calmar", "trades", "winrate_pct"]
    table_cols = [c for c in table_cols if c in show.columns]
    render_metric_table(show[table_cols], STAKE_SIM_COLUMNS, seed_col="combo")

    default_rank = int(st.session_state.get(f"{cfg_key}_sim_pick_rank", 1))
    default_rank = max(1, min(default_rank, len(view_df)))
    sel_rank = st.number_input(
        "Rank da applicare (#)",
        min_value=1,
        max_value=len(view_df),
        value=default_rank,
        step=1,
        key=f"{cfg_key}_sim_pick_rank",
        help="Numero Rank dalla tabella sopra.",
    )
    picked = view_df.iloc[int(sel_rank) - 1]
    st.markdown(
        f"**Selezionato:** **{picked.get('combo', '—')}** · {format_stake_combo(picked)} · "
        f"Profit **{picked['profit']:.1f}U** · DD **{picked['max_dd']:.1f}U**"
    )

    if st.button("✅ Applica configurazione selezionata", type="primary", key=f"{cfg_key}_apply_picked"):
        apply_stake_rules(cfg_key, system, picked.to_dict())
        st.success(
            f"Stake e combinazione **{picked.get('combo', '')}** applicate. "
            "Opzionale: ricalcola **Combinazioni pattern**."
        )

    with st.expander("Scorciatoie rapide"):
        ca, cb, cc = st.columns(3)
        if ca.button("Miglior score", key=f"{cfg_key}_apply_best_score"):
            apply_stake_rules(cfg_key, system, best_score.to_dict())
            st.success(f"Applicato: {best_score.get('combo')} · {format_stake_combo(best_score)}")
        if cb.button("Max profit", key=f"{cfg_key}_apply_best_profit"):
            apply_stake_rules(cfg_key, system, best_profit.to_dict())
            st.success(f"Applicato: {best_profit.get('combo')} · {format_stake_combo(best_profit)}")
        if cc.button("Miglior Calmar", key=f"{cfg_key}_apply_best_calmar"):
            apply_stake_rules(cfg_key, system, best_calmar.to_dict())
            st.success(f"Applicato: {best_calmar.get('combo')} · {format_stake_combo(best_calmar)}")

    st.download_button(
        "📥 Scarica CSV simulazioni",
        view_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{cfg_key}_stake_simulation.csv",
        mime="text/csv",
        key=f"{cfg_key}_dl_stake_sim",
    )


@st.fragment
def render_tier_optimizer_fragment(cfg_key: str, system: str, strategy_label: str, df_raw):
    """Fragment: click su Calcola tier non resetta la tab attiva."""
    try:
        render_tier_optimizer(cfg_key, system, strategy_label, df_raw)
    except Exception as exc:
        st.error(f"Errore ottimizzatore tier: {exc}")


@st.fragment
def render_stake_simulator_fragment(cfg_key: str, system: str, strategy_label: str, df_raw):
    """Fragment: i click non resettano la tab attiva."""
    try:
        render_stake_simulator(cfg_key, system, strategy_label, df_raw)
    except Exception as exc:
        st.error(f"Errore simulazione stake: {exc}")
