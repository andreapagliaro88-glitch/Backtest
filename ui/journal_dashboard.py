"""Dashboard Journal trade — stile mockup."""
from __future__ import annotations

import math
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.plot_theme import PLOT_LAYOUT, PLOTLY_CONFIG, style_figure

from compound_config import PROFIT_ODDS
from core.daily_trades import (
    JOURNAL_PATH,
    can_settle_trade,
    delete_all_trades,
    delete_trades_in_period,
    mark_no_trade,
    settle_trade,
    trade_settle_status,
    trades_in_period_mask,
)

JOURNAL_CSS = """
<style>
    .jn-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; }
    .jn-title { font-size:1.35rem; font-weight:700; color:#f0f3f6; margin:0; }
    .jn-panel {
        background:#161b22; border:1px solid #30363d; border-radius:12px;
        padding:1rem 1.15rem; margin-bottom:0.85rem;
    }
    .jn-chip-row { display:flex; flex-wrap:wrap; gap:0.45rem; margin-bottom:0.75rem; }
    .jn-chip {
        display:inline-flex; align-items:center; gap:0.35rem;
        padding:0.35rem 0.75rem; border-radius:999px; font-size:0.78rem;
        border:1px solid #30363d; background:#21262d; color:#8b949e;
    }
    .jn-chip.on { border-color:#388bfd; background:#13253d; color:#e6edf3; }
    .jn-chip .cnt {
        background:#30363d; border-radius:999px; padding:0.05rem 0.45rem;
        font-weight:600; font-size:0.72rem;
    }
    .jn-chip.on .cnt { background:#388bfd; color:#fff; }
    .jn-kpi {
        background:#161b22; border:1px solid #30363d; border-radius:12px;
        padding:0.75rem 0.85rem; min-height:82px;
    }
    .jn-kpi-lbl { color:#8b949e; font-size:0.72rem; margin-bottom:0.2rem; }
    .jn-kpi-val { color:#f0f3f6; font-size:1.35rem; font-weight:700; line-height:1.1; }
    .jn-kpi-sub { color:#6e7681; font-size:0.68rem; margin-top:0.2rem; }
    .jn-kpi-val.green { color:#3fb950; }
    .jn-kpi-val.red { color:#f85149; }
    .jn-chart-box {
        background:#161b22; border:1px solid #30363d; border-radius:12px;
        padding:0.35rem 0.25rem 0.15rem 0.25rem; margin-bottom:0.5rem;
    }
    .jn-table-wrap {
        background:#0d1117; border:1px solid #30363d; border-radius:10px;
        overflow-x:auto; margin-top:0.5rem;
    }
    .jn-table { width:100%; border-collapse:collapse; font-size:0.78rem; }
    .jn-table th {
        background:#161b22; color:#8b949e; font-weight:500; text-align:left;
        padding:0.65rem 0.7rem; border-bottom:1px solid #30363d; white-space:nowrap;
    }
    .jn-table td {
        color:#e6edf3; padding:0.65rem 0.7rem; border-bottom:1px solid #21262d;
        vertical-align:middle;
    }
    .jn-table tr:hover td { background:#161b22; }
    .jn-pill {
        display:inline-block; padding:0.15rem 0.55rem; border-radius:999px;
        font-size:0.68rem; font-weight:600;
    }
    .jn-pill.win { background:#0d2818; color:#3fb950; border:1px solid #238636; }
    .jn-pill.lose { background:#3d1214; color:#f85149; border:1px solid #da3633; }
    .jn-pill.pending { background:#2a2a1a; color:#d29922; border:1px solid #6e5a00; }
    .jn-pill.skip { background:#21262d; color:#8b949e; border:1px solid #30363d; }
    .jn-profit-pos { color:#3fb950; font-weight:600; }
    .jn-profit-neg { color:#f85149; font-weight:600; }
    .jn-icon-win { color:#3fb950; }
    .jn-icon-lose { color:#f85149; }
    .jn-icon-neutral { color:#8b949e; }
</style>
"""

PLOT = PLOT_LAYOUT

ESITI = ["DA GIOCARE", "VINTO", "PERSO", "NO TRADE", "SALTATO"]
DEFAULT_ESITI = ["DA GIOCARE", "VINTO", "PERSO", "NO TRADE"]

STATUS_LABEL = {
    "future": ("⏳ In attesa", "pending"),
    "live": ("⚽ In corso", "skip"),
    "ready": ("✅ Registra esito", "win"),
}


def _quota(row) -> float | None:
    sys = str(row.get("strategia", ""))
    stake = float(row.get("stake_eur") or 0)
    if row.get("esito") == "VINTO" and stake > 0:
        prof = float(row.get("profit_eur") or 0)
        return round(1 + prof / stake, 2)
    if sys in PROFIT_ODDS:
        return round(1 + PROFIT_ODDS[sys], 2)
    return None


def _prepare_df(journal: pd.DataFrame) -> pd.DataFrame:
    df = journal.copy()
    now = pd.Timestamp.now()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["quota"] = df.apply(_quota, axis=1)
    df["ora_h"] = pd.to_numeric(df["ora"].astype(str).str[:2], errors="coerce")
    df["risk_mode"] = df["modalita_rischio"].fillna("").astype(str)
    df["profit_eur"] = pd.to_numeric(df["profit_eur"], errors="coerce")
    df["stake_eur"] = pd.to_numeric(df["stake_eur"], errors="coerce")
    df["bankroll_eur"] = pd.to_numeric(df["bankroll_eur"], errors="coerce")
    df["stato_partita"] = df.apply(lambda r: trade_settle_status(r, now), axis=1)
    return df.sort_values(["data", "ora"], ascending=False).reset_index(drop=True)


def _filter_df(
    df: pd.DataFrame,
    esiti: list[str],
    date_from,
    date_to,
    campionato: str,
    strategia: str,
    risk_mode: str,
) -> pd.DataFrame:
    out = df[df["esito"].isin(esiti)].copy()
    if date_from:
        out = out[out["data"] >= pd.Timestamp(date_from)]
    if date_to:
        out = out[out["data"] <= pd.Timestamp(date_to)]
    if campionato and campionato != "Tutti":
        out = out[out["campionato"] == campionato]
    if strategia and strategia != "Tutte":
        out = out[out["strategia"] == strategia]
    if risk_mode and risk_mode != "Tutti":
        out = out[out["risk_mode"] == risk_mode]
    return out


def _kpi_card(label: str, value: str, sub: str = "", green: bool = False, red: bool = False):
    cls = "jn-kpi-val"
    if green:
        cls += " green"
    elif red:
        cls += " red"
    st.markdown(
        f'<div class="jn-kpi"><div class="jn-kpi-lbl">{label}</div>'
        f'<div class="{cls}">{value}</div>'
        f'<div class="jn-kpi-sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def _esito_chips(df: pd.DataFrame):
    counts = {e: int((df["esito"] == e).sum()) for e in ESITI}
    if "jn_esiti" not in st.session_state:
        st.session_state["jn_esiti"] = DEFAULT_ESITI.copy()

    c1, c2, c3, c4 = st.columns(4)
    toggles = [
        (c1, "DA GIOCARE"), (c2, "VINTO"), (c3, "PERSO"), (c4, "NO TRADE"),
    ]
    for col, esito in toggles:
        with col:
            on = esito in st.session_state["jn_esiti"]
            label = f"{'● ' if on else '○ '}{esito} ({counts.get(esito, 0)})"
            if st.button(label, key=f"chip_{esito}", use_container_width=True):
                cur = st.session_state["jn_esiti"]
                if esito in cur:
                    st.session_state["jn_esiti"] = [e for e in cur if e != esito]
                else:
                    st.session_state["jn_esiti"] = cur + [esito]
                st.rerun()


def _chart_profit_line(settled: pd.DataFrame):
    if settled.empty:
        st.info("Nessun trade regolato.")
        return
    s = settled.sort_values(["data", "ora"])
    s = s.copy()
    s["cum_profit"] = s["profit_eur"].cumsum()
    fig = px.area(s, x="data", y="cum_profit", labels={"cum_profit": "€", "data": ""})
    fig.update_traces(line_color="#3fb950", fillcolor="rgba(63,185,80,0.2)")
    fig.update_layout(title="Andamento profitto (€)", height=260, **PLOT)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _chart_esito_donut(jf: pd.DataFrame):
    counts = jf[jf["esito"].isin(["VINTO", "PERSO", "NO TRADE", "DA GIOCARE"])]["esito"].value_counts()
    if counts.empty:
        st.info("Nessun dato.")
        return
    colors = {"VINTO": "#3fb950", "PERSO": "#f85149", "NO TRADE": "#8b949e", "DA GIOCARE": "#d29922"}
    fig = go.Figure(data=[go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        hole=0.55,
        marker=dict(colors=[colors.get(l, "#58a6ff") for l in counts.index]),
        textinfo="percent",
        textfont_size=11,
    )])
    fig.update_layout(
        title=f"Esito trade · {int(counts.sum())} totale",
        height=260, showlegend=True, legend=dict(font=dict(size=10)), **PLOT,
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _chart_profit_by_esito(settled: pd.DataFrame):
    if settled.empty:
        st.info("Nessun dato.")
        return
    rows = []
    for esito, color in [("VINTO", "#3fb950"), ("PERSO", "#f85149")]:
        sub = settled[settled["esito"] == esito]
        if not sub.empty:
            rows.append({"esito": esito, "profitto": sub["profit_eur"].sum()})
    if not rows:
        st.info("Nessun dato.")
        return
    d = pd.DataFrame(rows)
    fig = px.bar(d, x="profitto", y="esito", orientation="h", color="esito",
                 color_discrete_map={"VINTO": "#3fb950", "PERSO": "#f85149"})
    fig.update_layout(title="Profitto per esito", height=260, showlegend=False, **PLOT)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _chart_profit_by_hour(settled: pd.DataFrame):
    if settled.empty or settled["ora_h"].isna().all():
        st.info("Nessun dato.")
        return
    by_h = settled.groupby("ora_h", dropna=True)["profit_eur"].sum().reset_index()
    by_h["ora_h"] = by_h["ora_h"].astype(int)
    colors = ["#3fb950" if v >= 0 else "#f85149" for v in by_h["profit_eur"]]
    fig = go.Figure(data=[go.Bar(x=by_h["ora_h"], y=by_h["profit_eur"], marker_color=colors)])
    fig.update_layout(title="Profitto per ora del giorno", height=260, **PLOT)
    fig.update_xaxes(title="Ora", dtick=3)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _esito_pill(esito: str) -> str:
    cls = {"VINTO": "win", "PERSO": "lose", "DA GIOCARE": "pending", "NO TRADE": "skip"}.get(esito, "skip")
    return f'<span class="jn-pill {cls}">{esito}</span>'


def _status_icon(esito: str, stato_partita: str = "") -> str:
    if esito == "VINTO":
        return '<span class="jn-icon-win">✓</span>'
    if esito == "PERSO":
        return '<span class="jn-icon-lose">✗</span>'
    if esito == "DA GIOCARE":
        if stato_partita == "future":
            return '<span class="jn-icon-neutral">⏳</span>'
        if stato_partita == "live":
            return '<span class="jn-icon-neutral">⚽</span>'
        return '<span class="jn-icon-win">○</span>'
    return '<span class="jn-icon-neutral">○</span>'


def _profit_cell(val) -> str:
    if pd.isna(val) or val == "" or val is None:
        return "—"
    v = float(val)
    if v > 0:
        return f'<span class="jn-profit-pos">+{v:.2f}</span>'
    if v < 0:
        return f'<span class="jn-profit-neg">{v:.2f}</span>'
    return "0.00"


def _render_table(page_df: pd.DataFrame):
    rows = []
    for _, r in page_df.iterrows():
        data_s = pd.Timestamp(r["data"]).strftime("%Y-%m-%d") if pd.notna(r["data"]) else ""
        quota = f"{r['quota']:.2f}" if pd.notna(r.get("quota")) and r.get("quota") else "—"
        stake = f"{r['stake_eur']:.2f}" if pd.notna(r.get("stake_eur")) else "—"
        br = f"{r['bankroll_eur']:.2f}" if pd.notna(r.get("bankroll_eur")) else "—"
        note = str(r.get("note") or "")[:40]
        stato = r.get("stato_partita", "")
        stato_txt = ""
        if r["esito"] == "DA GIOCARE" and stato in STATUS_LABEL:
            lbl, cls = STATUS_LABEL[stato]
            stato_txt = f'<span class="jn-pill {cls}">{lbl}</span>'
        rows.append(f"""
        <tr>
            <td>{_status_icon(r['esito'], stato)}</td>
            <td>{data_s}</td>
            <td>{r.get('ora','')}</td>
            <td>{r.get('campionato','')}</td>
            <td><b>{r.get('partita','')}</b></td>
            <td>{r.get('strategia','')}</td>
            <td>{int(r.get('segnali') or 0)}</td>
            <td>{stake}</td>
            <td>{quota}</td>
            <td>{r.get('risk_mode') or '—'}</td>
            <td>{_esito_pill(r['esito'])} {stato_txt}</td>
            <td>{_profit_cell(r.get('profit_eur'))}</td>
            <td>{br}</td>
            <td><small>{note}</small></td>
        </tr>""")
    html = f"""
    <div class="jn-table-wrap"><table class="jn-table">
    <thead><tr>
        <th></th><th>Data</th><th>Ora</th><th>Campionato</th><th>Partita</th>
        <th>Strategia</th><th>Segnali</th><th>Stake (€)</th><th>Quota</th>
        <th>Risk mode</th><th>Esito</th><th>Profitto (€)</th><th>Bankroll (€)</th><th>Note</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_journal_section(journal: pd.DataFrame, bankroll_input: float, initial_bankroll: float):
    st.markdown(JOURNAL_CSS, unsafe_allow_html=True)

    hdr_l, hdr_r = st.columns([3, 1])
    with hdr_l:
        st.markdown('<p class="jn-title">Journal trade</p>', unsafe_allow_html=True)
    with hdr_r:
        if os.path.exists(JOURNAL_PATH):
            with open(JOURNAL_PATH, "rb") as f:
                st.download_button(
                    "📥 Esporta CSV",
                    f,
                    file_name="journal_trade.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    if journal.empty:
        st.info("Nessun trade nel journal. Carica i file Fixtures per iniziare.")
        return

    df = _prepare_df(journal)

    st.markdown('<div class="jn-panel">', unsafe_allow_html=True)
    _esito_chips(df)

    min_d = df["data"].min().date() if df["data"].notna().any() else None
    max_d = df["data"].max().date() if df["data"].notna().any() else None
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        date_from = st.date_input("Periodo — Da", value=min_d, key="jn_date_from")
    with fc2:
        date_to = st.date_input("A", value=max_d, key="jn_date_to")
    with fc3:
        camps = ["Tutti"] + sorted(df["campionato"].dropna().astype(str).unique().tolist())
        campionato = st.selectbox("Campionato", camps, key="jn_camp")
    with fc4:
        strats = ["Tutte"] + sorted(df["strategia"].dropna().astype(str).unique().tolist())
        strategia = st.selectbox("Strategia", strats, key="jn_strat")

    risks = ["Tutti"] + sorted([r for r in df["risk_mode"].unique().tolist() if r])
    risk_mode = st.selectbox("Risk mode", risks, key="jn_risk")
    st.markdown("</div>", unsafe_allow_html=True)

    esiti = st.session_state.get("jn_esiti", DEFAULT_ESITI)
    jf = _filter_df(df, esiti, date_from, date_to, campionato, strategia, risk_mode)

    settled = jf[jf["esito"].isin(["VINTO", "PERSO"])]
    played = settled
    total_settled = len(settled)
    n_win = int((jf["esito"] == "VINTO").sum())
    n_lose = int((jf["esito"] == "PERSO").sum())
    n_pending = int((jf["esito"] == "DA GIOCARE").sum())
    n_skip = int((jf["esito"] == "NO TRADE").sum())
    profit = float(jf["profit_eur"].dropna().sum())
    roi = (profit / initial_bankroll * 100) if initial_bankroll else 0
    last_br = df.sort_values(["data", "ora"])[df["bankroll_eur"].notna()]["bankroll_eur"]
    ultimo_br = float(last_br.iloc[-1]) if len(last_br) else bankroll_input
    avg_stake = float(played["stake_eur"].mean()) if not played.empty else 0
    quotas = played["quota"].dropna()
    avg_quota = float(quotas.mean()) if not quotas.empty else 0

    k = st.columns(8)
    with k[0]:
        _kpi_card("Da giocare", str(n_pending))
    with k[1]:
        pct = f"{n_win / total_settled * 100:.1f}%" if total_settled else "—"
        _kpi_card("Vinti", str(n_win), pct, green=True)
    with k[2]:
        pct = f"{n_lose / total_settled * 100:.1f}%" if total_settled else "—"
        _kpi_card("Persi", str(n_lose), pct, red=True)
    with k[3]:
        _kpi_card("No trade", str(n_skip))
    with k[4]:
        sign = "+" if profit >= 0 else ""
        _kpi_card("Profitto journal", f"{sign}{profit:.2f} €", f"ROI: {sign}{roi:.2f}%", green=profit >= 0, red=profit < 0)
    with k[5]:
        _kpi_card("Ultimo bankroll", f"{ultimo_br:.2f} €")
    with k[6]:
        _kpi_card("Stake medio", f"{avg_stake:.2f} €")
    with k[7]:
        _kpi_card("Quota media", f"{avg_quota:.2f}" if avg_quota else "—")

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    with r1c1:
        st.markdown('<div class="jn-chart-box">', unsafe_allow_html=True)
        _chart_profit_line(settled)
        st.markdown("</div>", unsafe_allow_html=True)
    with r1c2:
        st.markdown('<div class="jn-chart-box">', unsafe_allow_html=True)
        _chart_esito_donut(jf)
        st.markdown("</div>", unsafe_allow_html=True)
    with r1c3:
        st.markdown('<div class="jn-chart-box">', unsafe_allow_html=True)
        _chart_profit_by_esito(settled)
        st.markdown("</div>", unsafe_allow_html=True)
    with r1c4:
        st.markdown('<div class="jn-chart-box">', unsafe_allow_html=True)
        _chart_profit_by_hour(settled)
        st.markdown("</div>", unsafe_allow_html=True)

    page_size = st.selectbox("Mostra righe", [10, 25, 50, 100], index=0, key="jn_page_size")
    total_pages = max(1, math.ceil(len(jf) / page_size))
    page = st.number_input("Pagina", min_value=1, max_value=total_pages, value=1, step=1, key="jn_page")
    start = (page - 1) * page_size
    page_df = jf.iloc[start:start + page_size]
    st.caption(f"{len(jf)} trade · pagina {page}/{total_pages}")
    _render_table(page_df)

    st.markdown('<div class="jn-panel">', unsafe_allow_html=True)
    st.markdown("**Elimina trade**")
    st.caption("Rimuove i trade dal journal e ricalcola stake/bankroll sui restanti.")

    ec1, ec2, ec3, ec4 = st.columns(4)
    with ec1:
        del_date_from = st.date_input("Elimina da (data)", value=min_d, key="jn_del_date_from")
    with ec2:
        del_date_to = st.date_input("Elimina a (data)", value=max_d, key="jn_del_date_to")
    with ec3:
        del_time_from = st.text_input("Ora da (opz.)", value="", placeholder="es. 14:00", key="jn_del_time_from")
    with ec4:
        del_time_to = st.text_input("Ora a (opz.)", value="", placeholder="es. 22:00", key="jn_del_time_to")

    preview_mask = trades_in_period_mask(
        df,
        del_date_from,
        del_date_to,
        del_time_from.strip() or None,
        del_time_to.strip() or None,
    )
    n_preview = int(preview_mask.sum())
    st.caption(f"Nel periodo selezionato: **{n_preview}** trade da eliminare (su {len(df)} totali).")

    bc_del, bc_all = st.columns(2)
    with bc_del:
        if st.button(
            f"🗑 Elimina {n_preview} trade nel periodo",
            use_container_width=True,
            disabled=n_preview == 0,
            key="jn_delete_period",
        ):
            _, n = delete_trades_in_period(
                del_date_from,
                del_date_to,
                del_time_from.strip() or None,
                del_time_to.strip() or None,
                initial_bankroll,
            )
            st.success(f"Eliminati {n} trade.")
            st.rerun()
    with bc_all:
        confirm_all = st.checkbox("Confermo eliminazione di TUTTI i trade", key="jn_confirm_delete_all")
        if st.button(
            "🗑 Elimina tutti i trade",
            use_container_width=True,
            disabled=not confirm_all or journal.empty,
            key="jn_delete_all",
        ):
            delete_all_trades()
            st.success("Journal svuotato.")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    pending = journal[journal["esito"] == "DA GIOCARE"].copy()
    pending = _prepare_df(pending) if not pending.empty else pending

    if not pending.empty:
        now = pd.Timestamp.now()
        ready = pending[pending.apply(lambda r: can_settle_trade(r, now), axis=1)]
        live = pending[pending["stato_partita"] == "live"]
        future = pending[pending["stato_partita"] == "future"]

        st.markdown('<div class="jn-panel">', unsafe_allow_html=True)
        st.markdown("**Registra esito**")

        if not ready.empty:
            tmp = ready.copy()
            tmp["data_s"] = tmp["data"].astype(str)
            same_slot = tmp.groupby(["data_s", "ora"]).size()
            if (same_slot > 1).any():
                st.info(
                    "Hai più partite **allo stesso orario**. Giocale tutte con la stake indicata, "
                    "poi registrale **dopo il fischio finale**, in **qualsiasi ordine**. "
                    "Le stake allo stesso orario **non cambiano** finché non registri quelle successive."
                )

        st.caption(f"⏳ In attesa: {len(future)} · ⚽ In corso: {len(live)} · ✅ Registrabili: {len(ready)}")

        if ready.empty:
            st.warning(
                "Nessuna partita pronta da registrare. "
                "Aspetta che finisca la partita (HT ~55 min, O15/O25 ~110 min dal kickoff)."
            )
        else:
            ready = ready.sort_values(["data", "ora"])
            tid = st.selectbox(
                "Partita da registrare",
                ready["trade_id"].tolist(),
                format_func=lambda x: (
                    f"{ready[ready['trade_id']==x]['partita'].iloc[0]} — "
                    f"{ready[ready['trade_id']==x]['ora'].iloc[0]} · "
                    f"{ready[ready['trade_id']==x]['strategia'].iloc[0]} "
                    f"({ready[ready['trade_id']==x]['stake_eur'].iloc[0]:.2f}€)"
                ),
                label_visibility="collapsed",
            )
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if st.button("✅ Win", use_container_width=True, key="jn_win"):
                    settle_trade(tid, True, bankroll_input)
                    st.rerun()
            with bc2:
                if st.button("❌ Lose", use_container_width=True, key="jn_lose"):
                    settle_trade(tid, False, bankroll_input)
                    st.rerun()
            with bc3:
                if st.button("⏭ No trade", use_container_width=True, key="jn_skip"):
                    mark_no_trade(tid, bankroll_input)
                    st.rerun()

        if not live.empty:
            with st.expander(f"⚽ In corso ({len(live)}) — non registrare ancora"):
                st.dataframe(
                    live[["ora", "partita", "strategia", "stake_eur"]],
                    use_container_width=True, hide_index=True,
                )
        if not future.empty:
            with st.expander(f"⏳ Non ancora iniziate ({len(future)})"):
                st.dataframe(
                    future[["data", "ora", "partita", "strategia", "stake_eur"]],
                    use_container_width=True, hide_index=True,
                )

        st.markdown("</div>", unsafe_allow_html=True)
