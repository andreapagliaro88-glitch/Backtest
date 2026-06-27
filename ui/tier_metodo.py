"""Pannello Metodo Tier + ottimizzatori — tutte le strategie con pattern."""
from __future__ import annotations

from dataclasses import replace

import streamlit as st

from core.tier_backtest import tier_summary
from core.tier_config import TIER_SYSTEMS, default_tier_rules
from core.tier_engine import TIER_LABELS, any_pattern_matches
from core.tier_optimizer import (
    list_patterns_for_system,
    optimize_pattern_tiers,
    tier_rules_from_dict,
    tier_rules_to_dict,
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


def apply_stake_rules(cfg_key: str, system: str, stake_row: dict):
    """Applica solo stake T1–T4, mantiene T3/T4 pattern del passo tier."""
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


def show_tier_workflow_guide(cfg_key: str, system: str):
    """Flusso consigliato: tier → stake → combinazioni pattern."""
    tier_done = st.session_state.get(f"{cfg_key}_workflow_tier_done") or st.session_state.get(_rules_key(cfg_key))
    stake_done = st.session_state.get(f"{cfg_key}_workflow_stake_done")

    st.info(
        "**Flusso consigliato**\n\n"
        "1. **🎯 Ottimizza tier** — quali pattern in T3 / T4 / esclusi\n"
        "2. **⚖️ Simula stake** — stake T1/T2/T3/T4 con tutti i pattern combinati\n"
        "3. **🧩 Combinazioni pattern** — quale subset di pattern usare (con stake già impostate)\n\n"
        f"Stato: tier {'✅' if tier_done else '⬜'} · stake {'✅' if stake_done else '⬜'} · "
        "poi **Calcola combinazioni**"
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
- **CCS**: stake reale **1U in €**
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
                st.dataframe(sample, use_container_width=True, hide_index=True)
        summary = tier_summary(df_trades)
        if not summary.empty:
            st.markdown("**Performance per tier**")
            st.dataframe(summary, use_container_width=True, hide_index=True)
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
    view = result_df[show_cols].rename(columns={
        "pattern": "Pattern",
        "suggested_tier": "Tier suggerito",
        "trades": "Trade",
        "profit": "Profit (U)",
        "max_dd": "Max DD (U)",
        "score": "Score",
        "winrate_pct": "Winrate %",
        "motivo": "Motivo",
    })
    st.dataframe(view, use_container_width=True, hide_index=True)

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
                st.rerun()
        with col_b:
            if st.button("↩️ Ripristina default", key=f"{cfg_key}_reset_tier_rules"):
                st.session_state.pop(_rules_key(cfg_key), None)
                st.session_state.pop(f"{cfg_key}_tier_opt_result", None)
                st.session_state.pop(f"{cfg_key}_workflow_tier_done", None)
                st.session_state.pop(f"{cfg_key}_workflow_stake_done", None)
                mark_combos_stale(cfg_key)
                st.rerun()

        st.download_button(
            "📥 Scarica CSV",
            result_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{cfg_key}_tier_optimization.csv",
            mime="text/csv",
            key=f"{cfg_key}_dl_tier_opt",
        )


def render_stake_simulator(cfg_key: str, system: str, strategy_label: str, df_raw):
    from core.tier_stake_optimizer import format_stake_combo, simulate_all_patterns_stakes
    from ui.plot_theme import plot_scatter

    st.markdown(f"### Simulazione stake — {strategy_label}")
    st.caption(
        "**Passo 2/3** — Combina **tutti i pattern** e testa stake T1/T2/T3/T4. "
        "Mantiene T3/T4 pattern del passo 1. Poi **Combinazioni pattern**."
    )

    patterns = list_patterns_for_system(df_raw, system)
    if not patterns:
        st.error("Nessun pattern nei file Excel.")
        return

    st.info(f"Pattern inclusi: **{' + '.join(patterns)}**")

    rules = active_tier_rules(cfg_key, system)
    c1, c2, c3 = st.columns(3)
    dd_weight = c1.slider(
        "Penalità DD nello score", 0.2, 1.2, 0.6, 0.05,
        key=f"{cfg_key}_sim_dd_weight",
    )
    max_dd = c2.number_input(
        "Filtro DD minimo (U)", value=-999.0, step=1.0, key=f"{cfg_key}_sim_max_dd",
    )
    extra_random = c3.number_input(
        "Simulazioni extra (random)", 0, 2000, 500, 100, key=f"{cfg_key}_sim_random_n",
    )

    if st.button("⚖️ Avvia simulazione", type="primary", key=f"{cfg_key}_run_stake_sim"):
        with st.spinner("Simulazione stake in corso..."):
            baseline, results, rules_all = simulate_all_patterns_stakes(
                df_raw, system, rules,
                dd_weight=dd_weight,
                max_dd_limit=None if max_dd <= -900 else max_dd,
                include_random=extra_random > 0,
                random_iterations=int(extra_random),
            )
            st.session_state[f"{cfg_key}_stake_sim_baseline"] = baseline
            st.session_state[f"{cfg_key}_stake_sim_results"] = results
            st.session_state[f"{cfg_key}_combo_stakes_label"] = format_stakes_summary(cfg_key, system, rules_all)

    baseline = st.session_state.get(f"{cfg_key}_stake_sim_baseline")
    results = st.session_state.get(f"{cfg_key}_stake_sim_results")

    if baseline is None or results is None:
        st.info("Clicca **Avvia simulazione**.")
        return
    if results.empty:
        st.warning("Nessuna simulazione passa il filtro DD.")
        return

    best_score = results.iloc[0]
    best_profit = results.sort_values("profit", ascending=False).iloc[0]
    best_calmar = results.sort_values("calmar", ascending=False).iloc[0]

    st.markdown(f"**{len(results):,}** simulazioni valide")
    m1, m2, m3 = st.columns(3)
    for col, label, row in [(m1, "Baseline", baseline), (m2, "Miglior score", best_score), (m3, "Max profit", best_profit)]:
        with col:
            st.markdown(f"**{label}**")
            st.write(
                f"Profit **{row['profit']:.1f}U** · DD **{row['max_dd']:.1f}U** · "
                f"Score **{row['score']:.1f}**"
            )
            st.caption(format_stake_combo(row))

    scatter = results.copy()
    scatter["max_dd_abs"] = scatter["max_dd"].abs()
    plot_scatter(
        scatter, x="max_dd_abs", y="profit", color="score",
        title="Profit vs Drawdown — ogni punto è una simulazione",
        labels={"max_dd_abs": "Max DD (U)", "profit": "Profit (U)", "score": "Score"},
        hover_data=["stake_t1", "stake_t2", "stake_t3", "stake_t4", "calmar", "trades"],
        key=f"{cfg_key}_stake_sim_scatter",
    )

    show = results.copy()
    show["winrate_pct"] = (show["winrate"] * 100).round(1)
    show["stakes"] = show.apply(format_stake_combo, axis=1)
    show["#"] = range(1, len(show) + 1)
    st.caption(f"Tabella completa — **{len(show):,}** simulazioni (ordinate per score)")
    st.dataframe(
        show[["#", "stakes", "profit", "max_dd", "score", "calmar", "trades", "winrate_pct"]].rename(
            columns={
                "#": "Rank", "stakes": "Stake T1/T2/T3/T4", "profit": "Profit (U)",
                "max_dd": "Max DD (U)", "score": "Score", "calmar": "Calmar",
                "trades": "Trade", "winrate_pct": "Winrate %",
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=700 if len(show) > 15 else None,
    )

    default_rank = int(st.session_state.get(f"{cfg_key}_sim_pick_rank", 1))
    default_rank = max(1, min(default_rank, len(results)))
    sel_rank = st.number_input(
        "Rank da applicare (#)",
        min_value=1,
        max_value=len(results),
        value=default_rank,
        step=1,
        key=f"{cfg_key}_sim_pick_rank",
        help="Inserisci il numero Rank dalla tabella sopra (es. 16 per la riga #16).",
    )
    sel_idx = int(sel_rank) - 1
    picked = results.iloc[sel_idx]
    st.markdown(
        f"**Selezionato:** {format_stake_combo(picked)} · "
        f"Profit **{picked['profit']:.1f}U** · DD **{picked['max_dd']:.1f}U**"
    )

    if st.button("✅ Applica configurazione selezionata", type="primary", key=f"{cfg_key}_apply_picked"):
        apply_stake_rules(cfg_key, system, picked)
        st.success(
            f"Stake rank #{sel_rank} applicate (T3/T4 pattern invariati). "
            "Vai su **🧩 Combinazioni pattern** → **Calcola combinazioni**."
        )
        st.rerun()

    with st.expander("Scorciatoie rapide"):
        ca, cb, cc = st.columns(3)
        if ca.button("Miglior score", key=f"{cfg_key}_apply_best_score"):
            apply_stake_rules(cfg_key, system, best_score)
            st.rerun()
        if cb.button("Max profit", key=f"{cfg_key}_apply_best_profit"):
            apply_stake_rules(cfg_key, system, best_profit)
            st.rerun()
        if cc.button("Miglior Calmar", key=f"{cfg_key}_apply_best_calmar"):
            apply_stake_rules(cfg_key, system, best_calmar)
            st.rerun()

    st.download_button(
        "📥 Scarica CSV simulazioni",
        results.to_csv(index=False).encode("utf-8"),
        file_name=f"{cfg_key}_stake_simulation.csv",
        mime="text/csv",
        key=f"{cfg_key}_dl_stake_sim",
    )
