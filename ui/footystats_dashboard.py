"""UI dashboard FootyStats — stile mockup Analisi Campionati."""
from __future__ import annotations

import io
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from core.footystats_analyzer import DATA_DIR, list_csv_files
from core.footystats_markets import MARKETS
from core.footystats_simulation import PLOT_LAYOUT, run_dashboard_analysis
from ui.league_edge_discovery import render_edge_discovery

FOOTYSTATS_CSS = """
<style>
    .fs-title { font-size: 1.75rem; font-weight: 700; color: #f0f3f6; margin: 0 0 1rem 0; }
    .fs-panel {
        background: #161b22; border: 1px solid #30363d; border-radius: 12px;
        padding: 1.1rem 1.25rem; margin-bottom: 1rem;
    }
    .fs-chip-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.5rem 0 0.75rem 0; }
    .fs-chip {
        background: #21262d; border: 1px solid #30363d; border-radius: 999px;
        color: #e6edf3; font-size: 0.78rem; padding: 0.25rem 0.75rem;
    }
    .fs-chip.red { background: #3d1214; border-color: #da3633; color: #ff7b72; }
    .fs-status-ok {
        background: linear-gradient(135deg, #0d1f14 0%, #161b22 100%);
        border: 1px solid #238636; border-radius: 12px; padding: 1rem 1.25rem;
    }
    .fs-status-ok h4 { color: #3fb950; margin: 0 0 0.25rem 0; font-size: 0.95rem; }
    .fs-status-ok p { color: #8b949e; margin: 0; font-size: 0.82rem; line-height: 1.45; }
    .fs-kpi {
        background: #161b22; border: 1px solid #30363d; border-radius: 12px;
        padding: 0.9rem 1rem; min-height: 96px;
    }
    .fs-kpi-label { color: #8b949e; font-size: 0.75rem; margin-bottom: 0.25rem; }
    .fs-kpi-value { color: #f0f3f6; font-size: 1.55rem; font-weight: 700; line-height: 1.1; }
    .fs-kpi-value.green { color: #3fb950; }
    .fs-kpi-value.red { color: #f85149; }
    .fs-kpi-sub { color: #6e7681; font-size: 0.72rem; margin-top: 0.25rem; }
    .fs-section { color: #f0f3f6; font-size: 1rem; font-weight: 600; margin: 0.75rem 0 0.5rem 0; }
    .fs-chart-box {
        background: #161b22; border: 1px solid #30363d; border-radius: 12px;
        padding: 0.5rem 0.25rem 0.25rem 0.25rem; margin-bottom: 0.75rem;
    }
    .fs-table-wrap { background: #0d1117; border: 1px solid #30363d; border-radius: 10px; overflow-x: auto; }
    .fs-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    .fs-table th {
        background: #161b22; color: #8b949e; font-weight: 500; text-align: left;
        padding: 0.65rem 0.75rem; border-bottom: 1px solid #30363d; white-space: nowrap;
    }
    .fs-table td {
        color: #e6edf3; padding: 0.7rem 0.75rem; border-bottom: 1px solid #21262d;
        vertical-align: middle;
    }
    .fs-table tr:last-child td { border-bottom: none; }
    .fs-pct { color: #3fb950; font-weight: 600; }
    .fs-pct.neg { color: #f85149; }
    .fs-bar-bg { background: #21262d; border-radius: 4px; height: 5px; width: 70px; margin-top: 0.25rem; }
    .fs-bar-fill { background: linear-gradient(90deg, #238636, #3fb950); height: 5px; border-radius: 4px; }
</style>
"""


def inject_styles():
    st.markdown(FOOTYSTATS_CSS, unsafe_allow_html=True)


def _bar_html(pct: float, max_pct: float = 100) -> str:
    w = min(max(pct / max_pct * 100, 0), 100)
    return f'<div class="fs-bar-bg"><div class="fs-bar-fill" style="width:{w:.0f}%"></div></div>'


def kpi_card(label: str, value: str, sub: str, green: bool = False, red: bool = False):
    cls = "fs-kpi-value"
    if green:
        cls += " green"
    elif red:
        cls += " red"
    st.markdown(
        f'<div class="fs-kpi"><div class="fs-kpi-label">{label}</div>'
        f'<div class="{cls}">{value}</div><div class="fs-kpi-sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def format_updated(ts) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        return ts.strftime("%d/%m/%Y %H:%M")
    return str(ts)


def save_uploaded_csvs(uploaded_files) -> int:
    os.makedirs(DATA_DIR, exist_ok=True)
    n = 0
    for f in uploaded_files:
        path = os.path.join(DATA_DIR, f.name)
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        n += 1
    return n


def _apply_plot_style(fig, height: int = 320):
    fig.update_layout(**PLOT_LAYOUT, height=height, showlegend=False)
    return fig


def chart_equity(trades: pd.DataFrame):
    if trades.empty:
        st.info("Nessun trade per equity curve.")
        return
    fig = px.area(
        trades, x="trade_n", y="equity_eur",
        labels={"trade_n": "Trade", "equity_eur": "€"},
    )
    fig.update_traces(line_color="#3fb950", fillcolor="rgba(63,185,80,0.15)")
    fig.add_hline(
        y=trades["equity_eur"].iloc[-1], line_dash="dot", line_color="#8b949e",
        annotation_text=f"{trades['equity_eur'].iloc[-1]:,.0f} €",
    )
    fig.update_layout(title="Equity Curve (€)")
    st.plotly_chart(_apply_plot_style(fig, 340), use_container_width=True)


def chart_drawdown(trades: pd.DataFrame):
    if trades.empty:
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=trades["trade_n"], y=trades["dd_eur"], name="DD €",
                   fill="tozeroy", line_color="#f85149",
                   fillcolor="rgba(248,81,73,0.2)"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=trades["trade_n"], y=trades["dd_pct"], name="DD %",
                   line_color="#a371f7", line_width=1.5),
        secondary_y=True,
    )
    fig.update_layout(title="Drawdown (€) e Drawdown (%)")
    fig.update_yaxes(title_text="€", secondary_y=False)
    fig.update_yaxes(title_text="%", secondary_y=True)
    st.plotly_chart(_apply_plot_style(fig, 300), use_container_width=True)


def chart_profit_dist(trades: pd.DataFrame):
    if trades.empty:
        return
    fig = px.histogram(
        trades, x="profit_eur", nbins=20,
        title="Distribuzione Profitto per Trade (€)",
        color_discrete_sequence=["#3fb950"],
    )
    fig.update_layout(bargap=0.05)
    st.plotly_chart(_apply_plot_style(fig, 280), use_container_width=True)


def chart_rolling(trades: pd.DataFrame):
    if trades.empty:
        return
    c1, c2, c3 = st.columns(3)
    charts = [
        (c1, "wr_roll", "Win Rate (%) Rolling (ultimi 20 trade)", "#3fb950"),
        (c2, "roi_roll", "ROI (%) Rolling (ultimi 20 trade)", "#58a6ff"),
        (c3, "pf_roll", "Profit Factor Rolling (ultimi 20 trade)", "#d29922"),
    ]
    for col, ycol, title, color in charts:
        with col:
            fig = px.line(trades, x="trade_n", y=ycol, labels={"trade_n": "Trade"})
            fig.update_traces(line_color=color)
            fig.update_layout(title=title, title_font_size=11)
            st.plotly_chart(_apply_plot_style(fig, 240), use_container_width=True)


def chart_dd_duration(dd_df: pd.DataFrame):
    if dd_df.empty:
        st.info("Nessun periodo di drawdown.")
        return
    fig = px.bar(
        dd_df, x="start", y="days", title="Drawdown Duration",
        labels={"start": "Inizio", "days": "Giorni"},
        color_discrete_sequence=["#f85149"],
    )
    st.plotly_chart(_apply_plot_style(fig, 280), use_container_width=True)


def chart_heatmap(hm: pd.DataFrame):
    if hm.empty:
        st.info("Heatmap non disponibile.")
        return
    pivot = hm.pivot(index="campionato", columns="range", values="roi_pct")
    vals = pivot.values.astype(float)
    zlim = max(np.nanmax(np.abs(vals)), 1.0)
    fig = go.Figure(data=go.Heatmap(
        z=vals,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[[0, "#3d1214"], [0.5, "#21262d"], [1, "#238636"]],
        zmin=-zlim,
        zmax=zlim,
        colorbar=dict(title="ROI %"),
    ))
    fig.update_layout(title="Heatmap Performance (ROI %) per Range Quota")
    height = max(280, len(pivot) * 28 + 80)
    st.plotly_chart(_apply_plot_style(fig, height), use_container_width=True)


def render_detail_table(df: pd.DataFrame):
    if df.empty:
        st.info("Nessun risultato.")
        return
    rows = []
    for _, r in df.iterrows():
        wr = float(r.get("winrate_base", 0))
        roi_best = float(r.get("miglior_roi", 0))
        wr_rob = float(r.get("wr_robusto") or r.get("wr_sim_pct") or 0)
        roi_rob = float(r.get("roi_robusto") or r.get("roi_sim_pct") or 0)
        pf = float(r.get("profit_factor", 0))
        dd_e = float(r.get("dd_max_eur", 0))
        dd_p = float(r.get("dd_max_pct", 0))
        rows.append(f"""
        <tr>
            <td>{r['campionato']}</td>
            <td>{int(r.get('partite_sim') or r.get('partite', 0))}</td>
            <td><span class="fs-pct">{wr:.1f}%</span>{_bar_html(wr)}</td>
            <td>{r.get('miglior_range', '—')}</td>
            <td><span class="fs-pct">{roi_best:+.1f}%</span></td>
            <td>{r.get('range_robusto') or '—'}</td>
            <td><span class="fs-pct">{wr_rob:.1f}%</span>{_bar_html(wr_rob)}</td>
            <td><span class="fs-pct">{roi_rob:+.1f}%</span></td>
            <td>{pf:.2f}</td>
            <td><span class="fs-pct neg">{dd_e:,.0f} €</span></td>
            <td><span class="fs-pct neg">{dd_p:.1f}%</span></td>
        </tr>""")
    html = f"""
    <div class="fs-table-wrap"><table class="fs-table">
    <thead><tr>
        <th>Campionato</th><th>Partite</th><th>WR base %</th>
        <th>Miglior range (Odd)</th><th>ROI % (miglior range)</th>
        <th>Range robusto (Odd)</th><th>WR robusto %</th><th>ROI robusto %</th>
        <th>Profit Factor</th><th>Drawdown max (€)</th><th>Drawdown max (%)</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>"""
    st.markdown(html, unsafe_allow_html=True)


def _filter_trades(trades: pd.DataFrame, league: str | None, market: str | None) -> pd.DataFrame:
    t = trades.copy()
    if league and league != "Tutti":
        t = t[t["campionato"] == league]
    if market and market != "Tutti":
        t = t[t["mercato"] == market]
    return t


def enrich_trades_reset(trades: pd.DataFrame, initial: float = 10_000.0) -> pd.DataFrame:
    from core.footystats_simulation import enrich_trades
    t = trades.sort_values("date").reset_index(drop=True)
    return enrich_trades(t, initial)


def render_dashboard(data: dict, view_league: str, view_market: str, initial_bankroll: float):
    summary = data["summary"]
    trades_all = data["trades"]
    sub = summary.copy()
    if view_league and view_league != "Tutti":
        sub = sub[sub["campionato"] == view_league]
    if view_market and view_market != "Tutti":
        sub = sub[sub["mercato"] == view_market]

    trades = _filter_trades(trades_all, view_league, view_market)
    if not trades.empty:
        trades = enrich_trades_reset(trades, initial_bankroll)

    from core.footystats_simulation import metrics_from_trades
    m = metrics_from_trades(trades) if not trades.empty else data["metrics"]
    roi_best = float(sub["miglior_roi"].mean()) if not sub.empty else data.get("roi_best_avg", 0)
    roi_rob = float(sub["roi_robusto"].dropna().mean()) if not sub.empty else data.get("roi_robusto_avg", 0)

    k = st.columns(7)
    with k[0]:
        kpi_card("ROI %", f"{roi_best:+.1f}%", "Margine atteso (miglior range)", green=roi_best > 0)
    with k[1]:
        kpi_card("ROI robusto %", f"{roi_rob:+.1f}%", "Margine atteso robusto", green=roi_rob > 0)
    with k[2]:
        kpi_card("Win Rate %", f"{m['winrate']:.1f}%", "Percentuale di vincite")
    with k[3]:
        pf = m["profit_factor"]
        kpi_card("Profit Factor", f"{pf:.2f}" if pf != float("inf") else "∞", "Rapporto profitti/perdite")
    with k[4]:
        kpi_card("Partite analizzate", str(m["partite"]), "Totale partite simulate")
    with k[5]:
        kpi_card("Drawdown max", f"{m['dd_max_eur']:,.0f} €", "Peggior drawdown", red=True)
    with k[6]:
        kpi_card("Drawdown max %", f"{m['dd_max_pct']:.1f}%", "Peggior drawdown %", red=True)

    r1c1, r1c2 = st.columns([1.4, 1])
    with r1c1:
        st.markdown('<div class="fs-chart-box">', unsafe_allow_html=True)
        chart_equity(trades)
        st.markdown("</div>", unsafe_allow_html=True)
    with r1c2:
        st.markdown('<div class="fs-chart-box">', unsafe_allow_html=True)
        chart_drawdown(trades)
        st.markdown("</div>", unsafe_allow_html=True)

    r2c1, r2c2 = st.columns([1, 1.2])
    with r2c1:
        st.markdown('<div class="fs-chart-box">', unsafe_allow_html=True)
        chart_profit_dist(trades)
        st.markdown("</div>", unsafe_allow_html=True)
    with r2c2:
        chart_rolling(trades)

    r3c1, r3c2 = st.columns([1, 1.4])
    with r3c1:
        st.markdown('<div class="fs-chart-box">', unsafe_allow_html=True)
        from core.footystats_simulation import drawdown_duration
        chart_dd_duration(drawdown_duration(trades))
        st.markdown("</div>", unsafe_allow_html=True)
    with r3c2:
        st.markdown('<div class="fs-chart-box">', unsafe_allow_html=True)
        chart_heatmap(data.get("heatmap", pd.DataFrame()))
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<p class="fs-section">Dettaglio Campionato</p>', unsafe_allow_html=True)
    render_detail_table(sub)


@st.cache_data(show_spinner="Analisi in corso...")
def cached_dashboard(file_paths: tuple, market_ids: tuple, date_from, date_to, stake_eur, initial_bankroll):
    return run_dashboard_analysis(
        list(file_paths), list(market_ids),
        date_from=date_from, date_to=date_to,
        stake_eur=stake_eur, initial_bankroll=initial_bankroll,
    )


def show_footystats_tab():
    inject_styles()
    os.makedirs(DATA_DIR, exist_ok=True)
    all_files = list_csv_files(DATA_DIR)

    name_to_path = {os.path.splitext(os.path.basename(p))[0]: p for p in all_files}
    league_names = sorted(name_to_path.keys())
    market_options = {cfg["label"]: mid for mid, cfg in MARKETS.items()}
    market_labels = list(market_options.keys())

    tab_sim, tab_edge = st.tabs(["Simulazione mercati", "Probability Patterns"])

    with tab_edge:
        render_edge_discovery(name_to_path, league_names)

    with tab_sim:
        _show_simulation_tab(name_to_path, league_names, market_options, market_labels, all_files)


def _show_simulation_tab(
    name_to_path: dict,
    league_names: list[str],
    market_options: dict,
    market_labels: list[str],
    all_files: list[str],
):

    if "fs_leagues" not in st.session_state:
        st.session_state["fs_leagues"] = []
    if "fs_markets" not in st.session_state:
        st.session_state["fs_markets"] = [
            lbl for lbl in market_labels if "Over 0.5 HT" in lbl or "Over 2.5" in lbl
        ]

    # Header
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown('<div class="fs-title">Analisi Campionati</div>', unsafe_allow_html=True)
    with h2:
        done = st.session_state.get("footystats_data") is not None
        leagues_n = len(st.session_state.get("footystats_leagues", []))
        markets_n = len(st.session_state.get("footystats_markets", []))
        if done:
            st.markdown(
                f'<div class="fs-status-ok"><h4>✅ Analisi completata</h4>'
                f'<p>Analizzati {leagues_n} campionati × {markets_n} mercati</p>'
                f'<p>Ultimo aggiornamento: {format_updated(st.session_state.get("footystats_updated"))}</p></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="fs-status-ok" style="border-color:#30363d;">'
                '<h4 style="color:#8b949e;">⏳ In attesa</h4>'
                '<p>Seleziona campionati e mercati, poi analizza</p></div>',
                unsafe_allow_html=True,
            )

    # Upload + controlli (logica esistente)
    st.markdown('<div class="fs-panel">', unsafe_allow_html=True)
    up_col, ctrl_col = st.columns([1, 2])
    with up_col:
        st.markdown("**Carica CSV FootyStats**")
        uploaded = st.file_uploader(
            "Upload file",
            type=["csv"],
            accept_multiple_files=True,
            key="fs_upload",
            label_visibility="collapsed",
        )
        if uploaded:
            if st.button("💾 Salva CSV in database", use_container_width=True):
                n = save_uploaded_csvs(uploaded)
                cached_dashboard.clear()
                st.success(f"{n} file salvati in data/footystats/")
                st.rerun()
        st.caption(f"Database locale: **{len(all_files)}** file CSV")

    with ctrl_col:
        sel_leagues = st.multiselect(
            "Campionato",
            league_names,
            key="fs_leagues",
            placeholder="Scegli campionati...",
        )
        sel_markets = st.multiselect(
            "Mercati",
            market_labels,
            key="fs_markets",
            placeholder="Scegli mercati...",
        )
        chips = ""
        for lg in sel_leagues[:3]:
            chips += f'<span class="fs-chip red">{lg}</span>'
        for mk in sel_markets[:2]:
            chips += f'<span class="fs-chip red">{mk}</span>'
        if chips:
            st.markdown(f'<div class="fs-chip-row">{chips}</div>', unsafe_allow_html=True)

    opt1, opt2, opt3, opt4, opt5 = st.columns([1, 1, 1, 1.2, 1.2])
    with opt1:
        if st.button("Tutti", key="fs_all_leagues"):
            st.session_state["fs_leagues"] = league_names
            st.rerun()
    with opt2:
        if st.button("Nessuno", key="fs_no_leagues"):
            st.session_state["fs_leagues"] = []
            st.rerun()
    with opt3:
        if st.button("Gol/Over", key="fs_gol_markets"):
            st.session_state["fs_markets"] = [
                lbl for lbl in market_labels
                if any(x in lbl for x in ("HT", "2T", "Over", "BTTS"))
            ]
            st.rerun()
    with opt4:
        stake_eur = st.number_input("Stake simulazione (€)", min_value=10.0, value=100.0, step=10.0)
    with opt5:
        initial_bankroll = st.number_input("Bankroll iniziale sim. (€)", min_value=1000.0, value=10000.0, step=500.0)

    if all_files:
        min_date = pd.to_datetime("2020-01-01")
        max_date = pd.to_datetime("today")
        try:
            sample = pd.read_csv(all_files[0], sep=";", usecols=["date_GMT"], nrows=500)
            min_date = pd.to_datetime(sample["date_GMT"], format="mixed", errors="coerce").min()
            max_date = pd.to_datetime(sample["date_GMT"], format="mixed", errors="coerce").max()
        except Exception:
            pass
        dcol1, dcol2, dcol3 = st.columns([1.5, 1.5, 1])
        with dcol1:
            date_from = st.date_input("Da", value=min_date.date() if pd.notna(min_date) else datetime(2023, 1, 1).date())
        with dcol2:
            date_to = st.date_input("A", value=max_date.date() if pd.notna(max_date) else datetime(2023, 12, 31).date())
        with dcol3:
            analyze = st.button(
                "🔍 Analizza selezionati",
                type="primary",
                use_container_width=True,
                disabled=not sel_leagues or not sel_markets,
            )
    else:
        st.warning("Nessun CSV in `data/footystats/`. Carica i file sopra.")
        analyze = False
        date_from = date_to = None

    st.markdown("</div>", unsafe_allow_html=True)

    if analyze and sel_leagues and sel_markets:
        paths = tuple(name_to_path[l] for l in sel_leagues)
        mids = tuple(market_options[m] for m in sel_markets)
        cached_dashboard.clear()
        with st.spinner("Analisi in corso..."):
            data = cached_dashboard(paths, mids, date_from, date_to, stake_eur, initial_bankroll)
        st.session_state["footystats_data"] = data
        st.session_state["footystats_leagues"] = sel_leagues
        st.session_state["footystats_markets"] = sel_markets
        st.session_state["footystats_updated"] = datetime.now()
        st.rerun()

    data = st.session_state.get("footystats_data")
    if data and not data["summary"].empty:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            data["summary"].to_excel(writer, sheet_name="Riepilogo", index=False)
            if not data["trades"].empty:
                data["trades"].to_excel(writer, sheet_name="Trade", index=False)
            if not data.get("heatmap", pd.DataFrame()).empty:
                data["heatmap"].to_excel(writer, sheet_name="Heatmap", index=False)
        st.download_button(
            "📥 Esporta report",
            buf.getvalue(),
            file_name="report_footystats.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if not data or data["summary"].empty:
        st.info("Seleziona campionati e mercati, poi clicca **Analizza selezionati**.")
        return

    leagues_done = st.session_state.get("footystats_leagues", [])
    markets_done = st.session_state.get("footystats_markets", [])

    vf1, vf2 = st.columns(2)
    with vf1:
        view_league = st.selectbox("Filtra campionato", ["Tutti"] + leagues_done, key="fs_view_league")
    with vf2:
        view_market = st.selectbox("Filtra mercato", ["Tutti"] + markets_done, key="fs_view_market")

    render_dashboard(data, view_league, view_market, initial_bankroll)
