"""UI Probability Pattern Engine."""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.probability_discovery import MODE_PRESETS, discover_probability_patterns
from core.probability_storage import (
    list_saved_runs,
    load_saved_run,
    load_latest_for_league,
    save_results,
)

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _parse_json(val) -> dict | list:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return []
    return val


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _leaderboard_html(df: pd.DataFrame) -> str:
    rows = ""
    for _, r in df.head(15).iterrows():
        medal = MEDALS.get(int(r["rank"]), str(int(r["rank"])))
        label = r["event_label"]
        desc = str(r["description"])[:50]
        if len(str(r["description"])) > 50:
            desc += "…"
        rows += (
            f"<tr>"
            f"<td style='text-align:center;font-size:1.1rem'>{medal}</td>"
            f"<td><b>{label}</b><br><span style='color:#8b949e;font-size:0.75rem'>{desc}</span></td>"
            f"<td style='text-align:center'><b style='color:#3fb950'>{r['robustness_score']:.0f}/100</b></td>"
            f"<td style='text-align:center'>{_fmt_pct(r['probability'])}</td>"
            f"<td style='text-align:center'>×{r['lift']:.2f}</td>"
            f"<td style='text-align:center'>{int(r['n'])}</td>"
            f"<td style='text-align:center'>{_fmt_pct(r['oos_probability'])}</td>"
            f"</tr>"
        )
    return f"""
    <table class="fs-table" style="margin-top:0.5rem">
      <thead><tr>
        <th>Rank</th><th>Pattern</th><th>Robustezza</th><th>Prob.</th><th>Lift</th><th>N</th><th>OOS</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


def _chart_prob_timeline(monthly: dict) -> go.Figure:
    if not monthly:
        return go.Figure()
    months = sorted(monthly.keys())
    vals = [monthly[m] * 100 if monthly[m] is not None else None for m in months]
    fig = go.Figure(go.Scatter(
        x=months, y=vals, mode="lines+markers",
        line=dict(color="#58a6ff", width=2), connectgaps=False,
    ))
    fig.update_layout(
        height=240, margin=dict(l=40, r=20, t=30, b=60),
        title="Probabilità mensile (%)", paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
        font=dict(color="#e6edf3"), yaxis=dict(gridcolor="#21262d", range=[0, 100]),
        xaxis=dict(showgrid=False, tickangle=-45),
    )
    return fig


def _render_pattern_detail(row: pd.Series) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Robustness Score", f"{row['robustness_score']:.0f}/100")
    c2.metric("Probabilità", _fmt_pct(row["probability"]))
    c3.metric("Lift", f"×{row['lift']:.2f}")
    c4.metric("Partite", int(row["n"]))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("CI 95%", f"{_fmt_pct(row['ci_low'])} – {_fmt_pct(row['ci_high'])}")
    c6.metric("p-value", f"{row['p_value']:.4f}")
    c7.metric("OOS prob.", _fmt_pct(row["oos_probability"]))
    c8.metric("OOS partite", int(row["oos_n"]))

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Support", f"{row['support']*100:.1f}%")
    c10.metric("Confidence", _fmt_pct(row["confidence"]))
    c11.metric("Odds Ratio", f"{row['odds_ratio']:.2f}")
    c12.metric("Conviction", f"{row['conviction']:.2f}")

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("MC mediana", _fmt_pct(row.get("mc_median_prob", 0)))
    mc2.metric("MC P5", _fmt_pct(row.get("mc_p5_prob", 0)))
    mc3.metric("MC P95", _fmt_pct(row.get("mc_p95_prob", 0)))
    mc4.metric("Stab. mensile", f"{row['monthly_stability']*100:.0f}%")

    st.plotly_chart(_chart_prob_timeline(_parse_json(row.get("monthly_probs"))), use_container_width=True)

    with st.expander("Condizioni e metriche", expanded=True):
        st.markdown(f"**Evento previsto:** {row['event_label']} ({row['event_group']})")
        st.markdown(f"**Condizioni:** `{row['description']}`")
        d1, d2, d3 = st.columns(3)
        d1.write(f"**Baseline campionato:** {_fmt_pct(row['base_rate'])}")
        d1.write(f"**Expected frequency:** {row['expected_frequency']:.1f}")
        d1.write(f"**Leverage:** {row['leverage']*100:.1f} pp")
        d2.write(f"**Stabilità stagionale:** {row['seasonal_stability']*100:.0f}%")
        d2.write(f"**Walk-forward:** {'✓' if row.get('walk_forward_pass') else '✗'}")
        d2.write(f"**Metodi:** {', '.join(_parse_json(row.get('methods')) if isinstance(row.get('methods'), str) else row.get('methods', []))}")
        d3.write(f"**Hits:** {int(row['hits'])}/{int(row['n'])}")
        if row.get("date_from") and row.get("date_to"):
            d3.write(f"**Periodo:** {row['date_from']} → {row['date_to']}")
        if row.get("train_n"):
            d3.write(f"**Train (70%):** {_fmt_pct(row.get('train_probability', 0))} su {int(row['train_n'])} partite")

    if row.get("edge_explanation"):
        st.markdown("**Perché funziona (statistica)**")
        st.info(str(row["edge_explanation"]).replace("**", ""))

    st.markdown("### TRADING OPPORTUNITIES")
    st.caption("Mercati coerenti con il comportamento osservato — **senza uso di quote**.")
    markets = _parse_json(row.get("trading_opportunities"))
    if markets:
        for m in markets:
            st.markdown(f"- {m}")
    else:
        st.write("Nessun mapping disponibile.")


def render_edge_discovery(name_to_path: dict[str, str], league_names: list[str]) -> None:
    st.markdown('<div class="fs-section">Probability Pattern Engine</div>', unsafe_allow_html=True)
    st.caption(
        "Scoperta autonoma di **pattern di probabilità** pre-match. "
        "Nessun ROI, nessuna quota — solo eventi, lift, significatività e robustezza."
    )

    if not league_names:
        st.warning("Carica CSV in data/footystats/.")
        return

    c1, c2, c3, c4 = st.columns([2, 1.2, 1, 1])
    with c1:
        league = st.selectbox("Campionato", league_names, key="edge_league")
    with c2:
        mode = st.selectbox(
            "Modalità",
            options=list(MODE_PRESETS.keys()),
            format_func=lambda k: MODE_PRESETS[k]["label"],
            index=0,
            key="prob_discovery_mode",
        )
    with c3:
        min_n = st.number_input("Min. partite", min_value=200, max_value=500, value=200, step=10)
    with c4:
        run_all = st.checkbox("Tutti i campionati", value=False)

    if mode == "fast":
        st.caption(
            "**Veloci:** meno candidati, 4 gruppi eventi, no clustering/apriori — ideale per una prima scansione."
        )
    else:
        st.caption(
            "**Full:** tutti i gruppi eventi, ML esteso, clustering, apriori, combo fino a 6 variabili — analisi completa."
        )

    run = st.button("Scopri pattern robusti", type="primary", use_container_width=True)

    cache_key = "probability_pattern_results"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = {}

    if run:
        targets = league_names if run_all else [league]
        progress = st.progress(0.0, text="Avvio...")
        status = st.empty()
        results = dict(st.session_state[cache_key])

        for i, lg in enumerate(targets):
            status.info(f"Analisi **{lg}** ({i + 1}/{len(targets)})...")

            def _log(msg: str, _lg=lg):
                status.info(f"**{_lg}**: {msg}")

            df, meta = discover_probability_patterns(
                path=name_to_path[lg],
                min_n=int(min_n),
                mode=mode,
                progress_cb=_log,
            )
            now = datetime.now()
            save_path = save_results(lg, df, meta, updated=now)
            results[lg] = {
                "df": df,
                "meta": meta,
                "updated": now,
                "saved_path": save_path,
                "mode": mode,
            }
            progress.progress((i + 1) / len(targets))

        st.session_state[cache_key] = results
        progress.empty()
        status.success(f"Completato su {len(targets)} campionato/i. Risultati salvati in output/probability_patterns/.")
        st.rerun()

    # Carica ultimo salvataggio su disco se sessione vuota per quel campionato
    if league in league_names and league not in st.session_state.get(cache_key, {}):
        loaded = load_latest_for_league(league)
        if loaded:
            df_l, meta_l, upd_l = loaded
            st.session_state.setdefault(cache_key, {})[league] = {
                "df": df_l,
                "meta": meta_l,
                "updated": upd_l,
                "from_disk": True,
            }

    results = st.session_state.get(cache_key, {})
    if not results:
        st.info("Clicca **Scopri pattern robusti** per avviare l'analisi.")
        return

    view = st.selectbox("Risultati", sorted(results.keys()), key="prob_view_league")
    pack = results.get(view)
    if not pack:
        return

    meta = pack.get("meta", {})
    df: pd.DataFrame = pack.get("df", pd.DataFrame())
    updated = pack.get("updated")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Partite (file intero)", meta.get("n_matches", "—"))
    m2.metric("Eventi analizzati", meta.get("n_events", "—"))
    m3.metric("Pattern validati", meta.get("n_validated", 0))
    m4.metric("Train / Test (validazione)", f"{meta.get('n_train', '—')} / {meta.get('n_test', '—')}")
    if meta.get("date_from") and meta.get("date_to"):
        st.caption(
            f"**Periodo analisi:** {meta['date_from']} → {meta['date_to']} "
            f"(dall'inizio alla fine del file CSV selezionato)"
        )
    if meta.get("mode_label"):
        st.caption(f"**Modalità:** {meta['mode_label']}")
    st.caption(f"Candidati valutati: {meta.get('n_candidates', '—')}")

    if updated:
        src = " (caricato da disco)" if pack.get("from_disk") else ""
        st.caption(f"Ultimo run: {updated.strftime('%d/%m/%Y %H:%M')}{src}")
    if pack.get("saved_path"):
        st.caption(f"File: `{pack['saved_path']}`")

    saved_runs = list_saved_runs()
    if saved_runs:
        with st.expander("Archivio salvataggi"):
            opts = {
                f"{r.get('league', '?')} — {r.get('saved_at', '')[:16].replace('T', ' ')} "
                f"({r.get('n_patterns', 0)} pattern)": r["csv_path"]
                for r in saved_runs[:30]
            }
            pick = st.selectbox("Carica run salvato", ["—"] + list(opts.keys()), key="load_saved_run")
            if pick != "—":
                if st.button("Carica selezionato", key="btn_load_saved"):
                    df_s, meta_s, upd_s = load_saved_run(opts[pick])
                    lg_name = meta_s.get("league") or pick.split(" — ")[0]
                    st.session_state[cache_key][lg_name] = {
                        "df": df_s,
                        "meta": meta_s,
                        "updated": upd_s,
                        "from_disk": True,
                    }
                    st.rerun()
    if meta.get("error"):
        st.error(meta["error"])
        return

    if df.empty:
        st.warning(f"Nessun pattern supera i filtri su **{view}**.")
        return

    st.markdown("### Classifica pattern")
    st.markdown('<div class="fs-table-wrap">' + _leaderboard_html(df) + "</div>", unsafe_allow_html=True)

    st.download_button(
        "Scarica CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"probability_patterns_{view}.csv",
        mime="text/csv",
    )
    if st.button("Salva di nuovo su disco", key="resave_btn"):
        path = save_results(view, df, meta, updated=updated or datetime.now())
        st.success(f"Salvato: `{path}`")

    st.markdown("### Dettaglio pattern")
    labels = [
        f"{MEDALS.get(int(r['rank']), '#' + str(int(r['rank'])))} "
        f"{r['event_label']} — {r['robustness_score']:.0f}/100"
        for _, r in df.iterrows()
    ]
    sel = st.selectbox("Seleziona", range(len(labels)), format_func=lambda i: labels[i])
    _render_pattern_detail(df.iloc[sel])

    with st.expander("Tabella completa"):
        show = df.copy()
        for col in ("probability", "ci_low", "ci_high", "base_rate", "oos_probability", "confidence", "support"):
            if col in show.columns:
                show[col] = show[col].map(lambda x: f"{x*100:.1f}%")
        st.dataframe(show, use_container_width=True, hide_index=True)
