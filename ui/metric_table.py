"""Tabelle metriche stile dashboard scuro — sparkline, winrate ring, badge."""
from __future__ import annotations

import html
import math
from typing import Any

import pandas as pd
import streamlit as st

METRIC_TABLE_CSS = """
<style>
.cst-table-wrap { overflow-x: auto; margin-top: 0.25rem; max-height: 520px; overflow-y: auto; }
.cst-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 0.82rem;
}
.cst-table thead th {
    color: #8b949e;
    font-weight: 600;
    text-align: left;
    padding: 0.55rem 0.65rem;
    border-bottom: 1px solid #2a3039;
    white-space: nowrap;
    background: #0d1117;
    position: sticky;
    top: 0;
    z-index: 1;
}
.cst-table tbody tr:hover { background: rgba(255,255,255,0.03); }
.cst-table tbody td {
    padding: 0.7rem 0.65rem;
    border-bottom: 1px solid #21262d;
    vertical-align: middle;
    color: #e6edf3;
    background: transparent;
}
.cst-combo { display: flex; align-items: center; gap: 0.5rem; font-weight: 500; white-space: nowrap; }
.cst-combo-ico { font-size: 1rem; }
.cst-stakes { color: #9ca3af; font-size: 0.78rem; white-space: nowrap; }
.cst-npat {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 1.5rem; height: 1.5rem; border-radius: 6px;
    background: #1c2129; border: 1px solid #30363d;
    color: #c9d1d9; font-size: 0.78rem; font-weight: 600;
}
.cst-metric { display: flex; flex-direction: column; gap: 0.15rem; min-width: 4.5rem; }
.cst-mval { font-weight: 600; font-size: 0.86rem; line-height: 1.1; }
.cst-spark { display: block; opacity: 0.9; }
.cst-wr-ring {
    --pct: 50;
    width: 2.2rem; height: 2.2rem; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    background: conic-gradient(#3fb950 calc(var(--pct) * 1%), #2a3039 0);
    position: relative;
}
.cst-wr-ring::before {
    content: ""; position: absolute; inset: 4px; border-radius: 50%; background: #10141b;
}
.cst-wr-val {
    position: relative; z-index: 1; font-size: 0.58rem; font-weight: 700; color: #3fb950;
}
.cst-info { color: #6e7681; font-size: 0.72rem; margin-left: 0.15rem; }
.cst-muted { color: #9ca3af; font-size: 0.78rem; }
.cst-pos { color: #3fb950; font-weight: 600; }
.cst-neg { color: #f85149; font-weight: 600; }
.cst-pill {
    display: inline-block; padding: 0.15rem 0.45rem; border-radius: 6px;
    font-size: 0.72rem; font-weight: 600; background: #1c2129; border: 1px solid #30363d;
}
div[data-testid="stExpander"]:has(.cst-table) {
    background: linear-gradient(180deg, #151a22 0%, #10141b 100%) !important;
    border: 1px solid #2a3039 !important;
    border-radius: 14px !important;
    margin-bottom: 0.55rem !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.28) !important;
}
div[data-testid="stExpander"]:has(.cst-table) summary,
div[data-testid="stExpander"]:has(.cst-table) [data-testid="stMarkdownContainer"] p {
    font-weight: 600 !important;
    color: #e6edf3 !important;
}
</style>
"""

_ROW_ICONS = ("⭐", "〰️", "🎯", "⚡", "🚀", "💎", "🔥", "📈")

_METRIC_STYLE = {
    "profit": ("#3fb950", True, "{:,.1f}"),
    "max_dd": ("#f85149", False, "{:,.1f}"),
    "score": ("#58a6ff", True, "{:,.1f}"),
    "calmar": ("#f2cc60", True, "{:,.2f}"),
    "roi": ("#3fb950", True, "{:+.1f}%"),
    "roi_rob": ("#58a6ff", True, "{:+.1f}%"),
}


def inject_metric_table_css() -> None:
    st.markdown(METRIC_TABLE_CSS, unsafe_allow_html=True)


def _escape(text: object) -> str:
    return html.escape(str(text) if text is not None else "")


def _row_icon(idx: int) -> str:
    return _ROW_ICONS[idx % len(_ROW_ICONS)]


def _sparkline_svg(seed: str, color: str, *, upward: bool = True) -> str:
    h = sum(ord(c) for c in seed) % 997
    pts: list[str] = []
    for i in range(10):
        t = i / 9
        wave = math.sin(t * math.pi * 1.4 + h * 0.03) * 3
        trend = (1 - t) * 7 if upward else t * 7
        y = 13 - trend - wave
        pts.append(f"{i * 7:.1f},{y:.1f}")
    return (
        f'<svg class="cst-spark" viewBox="0 0 63 18" width="63" height="18">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{" ".join(pts)}"/>'
        f"</svg>"
    )


def _winrate_ring(pct: float) -> str:
    pct = max(0.0, min(100.0, float(pct)))
    return (
        f'<span class="cst-wr-ring" style="--pct:{pct:.1f};">'
        f'<span class="cst-wr-val">{pct:.1f}%</span></span>'
    )


def _metric_cell(value: float, fmt: str, color: str, spark_seed: str, *, upward: bool) -> str:
    return (
        f'<div class="cst-metric">'
        f'<div class="cst-mval" style="color:{color};">{fmt.format(value)}</div>'
        f"{_sparkline_svg(spark_seed, color, upward=upward)}"
        f"</div>"
    )


def _winrate_pct(raw: object) -> float:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return 0.0
    if isinstance(raw, str):
        s = raw.strip().rstrip("%")
        try:
            return float(s)
        except ValueError:
            return 0.0
    v = float(raw)
    return v * 100 if v <= 1 else v


def _cell_html(
    row: pd.Series,
    col: dict[str, Any],
    *,
    row_idx: int,
    seed: str,
    stakes_label: str = "",
) -> str:
    key = col["key"]
    kind = col.get("kind", "text")
    val = row.get(key)

    if kind == "rank":
        return f'<span class="cst-muted">{_escape(val)}</span>'
    if kind == "combo_icon":
        icon = _row_icon(row_idx)
        return (
            f'<div class="cst-combo"><span class="cst-combo-ico">{icon}</span>'
            f"<span>{_escape(val)}</span></div>"
        )
    if kind == "stakes":
        text = val if val not in (None, "", "—") else stakes_label
        return f'<span class="cst-stakes">{_escape(text or "—")}</span>'
    if kind == "badge":
        return f'<span class="cst-npat">{_escape(val)}</span>'
    if kind == "pill":
        return f'<span class="cst-pill">{_escape(val)}</span>'
    if kind == "winrate":
        return _winrate_ring(_winrate_pct(val))
    if kind == "trades":
        try:
            return f"{int(val):,}"
        except (TypeError, ValueError):
            return _escape(val)
    if kind == "profit_signed":
        try:
            v = float(val)
            cls = "cst-pos" if v >= 0 else "cst-neg"
            return f'<span class="{cls}">{v:+,.2f}</span>'
        except (TypeError, ValueError):
            return _escape(val)
    if kind == "metric":
        metric = col.get("metric", key)
        color, upward, fmt = _METRIC_STYLE.get(metric, ("#e6edf3", True, "{:,.2f}"))
        try:
            return _metric_cell(float(val), fmt, color, seed + metric, upward=upward)
        except (TypeError, ValueError):
            return _escape(val)
    if kind == "text_muted":
        return f'<span class="cst-muted">{_escape(val)}</span>'
  # text
    return _escape(val)


def build_metric_table_html(
    df: pd.DataFrame,
    columns: list[dict[str, Any]],
    *,
    seed_col: str = "combo",
    stakes_label: str = "",
    table_class: str = "cst-table",
) -> str:
    if df is None or df.empty:
        return ""

    headers = "".join(
        f"<th>{_escape(col['label'])}"
        + ('<span class="cst-info">ⓘ</span>' if col.get("info") else "")
        + "</th>"
        for col in columns
    )
    rows: list[str] = []
    for i, (_, row) in enumerate(df.iterrows()):
        seed = str(row.get(seed_col, i))
        cells = "".join(
            f"<td>{_cell_html(row, col, row_idx=i, seed=seed, stakes_label=stakes_label)}</td>"
            for col in columns
        )
        rows.append(f"<tr>{cells}</tr>")

    return (
        f'<div class="cst-table-wrap"><table class="{table_class}">'
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_metric_table(
    df: pd.DataFrame,
    columns: list[dict[str, Any]],
    *,
    seed_col: str = "combo",
    stakes_label: str = "",
) -> None:
    if df is None or df.empty:
        return
    inject_metric_table_css()
    st.markdown(
        build_metric_table_html(df, columns, seed_col=seed_col, stakes_label=stakes_label),
        unsafe_allow_html=True,
    )


def render_simple_table(
    df: pd.DataFrame,
    columns: list[dict[str, Any]] | None = None,
    *,
    seed_col: str | None = None,
) -> None:
    """Tabella scura senza sparkline — per trade, journal, CCS, ecc."""
    if df is None or df.empty:
        return
    if columns is None:
        columns = [{"key": c, "label": c, "kind": "text"} for c in df.columns]
    inject_metric_table_css()
    st.markdown(
        build_metric_table_html(
            df,
            columns,
            seed_col=seed_col or (df.columns[0] if len(df.columns) else "x"),
        ),
        unsafe_allow_html=True,
    )


# --- Preset colonne ---

COMBO_RESULT_COLUMNS: list[dict[str, Any]] = [
    {"key": "combo", "label": "Combinazione", "kind": "combo_icon"},
    {"key": "stakes_used", "label": "Stake T1/T2/T3/T4", "kind": "stakes"},
    {"key": "n_patterns", "label": "N° pattern", "kind": "badge"},
    {"key": "profit", "label": "Profit (U)", "kind": "metric", "metric": "profit", "info": True},
    {"key": "max_dd", "label": "Max DD (U)", "kind": "metric", "metric": "max_dd", "info": True},
    {"key": "score", "label": "Score", "kind": "metric", "metric": "score", "info": True},
    {"key": "calmar", "label": "Calmar", "kind": "metric", "metric": "calmar", "info": True},
    {"key": "trades", "label": "Trade", "kind": "trades"},
    {"key": "winrate", "label": "Winrate %", "kind": "winrate"},
]

STAKE_SIM_COLUMNS: list[dict[str, Any]] = [
    {"key": "#", "label": "Rank", "kind": "rank"},
    {"key": "n_patterns", "label": "N° pattern", "kind": "badge"},
    {"key": "combo", "label": "Combinazione", "kind": "combo_icon"},
    {"key": "stakes", "label": "Stake T1/T2/T3/T4", "kind": "stakes"},
    {"key": "profit", "label": "Profit (U)", "kind": "metric", "metric": "profit", "info": True},
    {"key": "max_dd", "label": "Max DD (U)", "kind": "metric", "metric": "max_dd", "info": True},
    {"key": "score", "label": "Score", "kind": "metric", "metric": "score", "info": True},
    {"key": "calmar", "label": "Calmar", "kind": "metric", "metric": "calmar", "info": True},
    {"key": "trades", "label": "Trade", "kind": "trades"},
    {"key": "winrate_pct", "label": "Winrate %", "kind": "winrate"},
]

OPT_STAKE_COLUMNS: list[dict[str, Any]] = [
    {"key": "#", "label": "Rank", "kind": "rank"},
    {"key": "profit", "label": "Profit (U)", "kind": "metric", "metric": "profit", "info": True},
    {"key": "max_dd", "label": "Max DD (U)", "kind": "metric", "metric": "max_dd", "info": True},
    {"key": "score", "label": "Score", "kind": "metric", "metric": "score", "info": True},
    {"key": "calmar", "label": "Calmar", "kind": "metric", "metric": "calmar", "info": True},
    {"key": "trades", "label": "Trade", "kind": "trades"},
    {"key": "winrate_pct", "label": "Winrate %", "kind": "winrate"},
    {"key": "params_str", "label": "Parametri", "kind": "text_muted"},
]

TIER_OPT_COLUMNS: list[dict[str, Any]] = [
    {"key": "pattern", "label": "Pattern", "kind": "combo_icon"},
    {"key": "suggested_tier", "label": "Tier suggerito", "kind": "pill"},
    {"key": "trades", "label": "Trade", "kind": "trades"},
    {"key": "profit", "label": "Profit (U)", "kind": "metric", "metric": "profit", "info": True},
    {"key": "max_dd", "label": "Max DD (U)", "kind": "metric", "metric": "max_dd", "info": True},
    {"key": "score", "label": "Score", "kind": "metric", "metric": "score", "info": True},
    {"key": "winrate_pct", "label": "Winrate %", "kind": "winrate"},
    {"key": "motivo", "label": "Motivo", "kind": "text_muted"},
]

STRATEGY_SUMMARY_COLUMNS: list[dict[str, Any]] = [
    {"key": "Strategia", "label": "Strategia", "kind": "pill"},
    {"key": "Profit (U)", "label": "Profit (U)", "kind": "metric", "metric": "profit", "info": True},
    {"key": "Max DD (U)", "label": "Max DD (U)", "kind": "metric", "metric": "max_dd", "info": True},
    {"key": "Trade", "label": "Trade", "kind": "trades"},
    {"key": "Winrate", "label": "Winrate %", "kind": "winrate"},
    {"key": "Pattern", "label": "Pattern", "kind": "text_muted"},
]

TIER_SUMMARY_COLUMNS: list[dict[str, Any]] = [
    {"key": "Tier", "label": "Tier", "kind": "pill"},
    {"key": "Trade", "label": "Trade", "kind": "trades"},
    {"key": "Profit (U)", "label": "Profit (U)", "kind": "metric", "metric": "profit", "info": True},
    {"key": "Max DD (U)", "label": "Max DD (U)", "kind": "metric", "metric": "max_dd", "info": True},
    {"key": "Winrate", "label": "Winrate %", "kind": "winrate"},
    {"key": "Stake medio (U)", "label": "Stake medio (U)", "kind": "text"},
]


def prepare_combo_view(combo_df: pd.DataFrame, *, stakes_label: str = "") -> pd.DataFrame:
    view = combo_df.copy()
    if "winrate" in view.columns:
        wr = view["winrate"]
        view["winrate"] = wr.apply(lambda x: _winrate_pct(x))
    if stakes_label:
        view["stakes_used"] = stakes_label
    return view
