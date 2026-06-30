"""Stile Plotly condiviso — tema scuro Streamlit."""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PLOT_LAYOUT = dict(
    paper_bgcolor="#161b22",
    plot_bgcolor="#0d1117",
    font=dict(color="#e6edf3", size=11),
    margin=dict(l=48, r=16, t=48, b=40),
    xaxis=dict(gridcolor="#30363d", zerolinecolor="#30363d", title_font=dict(color="#8b949e")),
    yaxis=dict(gridcolor="#30363d", zerolinecolor="#30363d", title_font=dict(color="#8b949e")),
    title=dict(font=dict(color="#f0f3f6", size=14)),
)

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


def _hex_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(88,166,255,{alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def style_figure(fig, height: int = 320, showlegend: bool = False):
    """Applica tema scuro senza template Plotly (evita reset colori tracce)."""
    fig.update_layout(
        paper_bgcolor=PLOT_LAYOUT["paper_bgcolor"],
        plot_bgcolor=PLOT_LAYOUT["plot_bgcolor"],
        font=PLOT_LAYOUT["font"],
        margin=PLOT_LAYOUT["margin"],
        title_font=dict(color="#f0f3f6", size=14),
        height=height,
        showlegend=showlegend,
    )
    fig.update_xaxes(
        gridcolor="#30363d",
        zerolinecolor="#30363d",
        title_font=dict(color="#8b949e"),
        tickfont=dict(color="#8b949e"),
    )
    fig.update_yaxes(
        gridcolor="#30363d",
        zerolinecolor="#30363d",
        title_font=dict(color="#8b949e"),
        tickfont=dict(color="#8b949e"),
    )
    return fig


def _chart_key(key: str | None, kind: str, title: str, *parts: str) -> str:
    if key:
        return key
    slug = re.sub(r"[^\w]+", "_", f"{kind}_{title}_{'_'.join(parts)}".lower()).strip("_")
    return slug[:120] or kind


def _trade_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index(drop=True).copy()
    out["trade_n"] = range(1, len(out) + 1)
    return out


def _prepare_xy(df: pd.DataFrame, x: str, y: str) -> pd.DataFrame | None:
    if df.empty or y not in df.columns:
        return None
    out = _trade_index(df) if x == "trade_n" and "trade_n" not in df.columns else df.reset_index(drop=True).copy()
    if x not in out.columns:
        return None
    out[y] = pd.to_numeric(out[y], errors="coerce")
    out[x] = out[x] if x == "trade_n" else out[x]
    out = out.dropna(subset=[y])
    if out.empty:
        return None
    return out


def _show_chart(fig, height: int, key: str | None, kind: str, title: str, *key_parts: str):
    chart_key = _chart_key(key, kind, title, *key_parts)
    st.plotly_chart(
        style_figure(fig, height),
        use_container_width=True,
        config=PLOTLY_CONFIG,
        key=chart_key,
    )


def plot_line(
    df: pd.DataFrame,
    y: str,
    title: str,
    x: str = "trade_n",
    height: int = 320,
    color: str = "#58a6ff",
    fill: bool = False,
    fill_to_zero: bool = False,
    key: str | None = None,
):
    plot_df = _prepare_xy(df, x, y)
    if plot_df is None:
        st.info(f"Nessun dato per «{title}».")
        return

    use_fill = fill or fill_to_zero
    fig = go.Figure(
        go.Scatter(
            x=plot_df[x],
            y=plot_df[y],
            mode="lines",
            line=dict(color=color, width=2),
            fill="tozeroy" if use_fill else None,
            fillcolor=_hex_rgba(color, 0.22) if use_fill else None,
        )
    )
    fig.update_layout(title=title)
    _show_chart(fig, height, key, "line", title, y, x)


def plot_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    height: int = 280,
    color: str = "#58a6ff",
    key: str | None = None,
):
    if df.empty or x not in df.columns or y not in df.columns:
        st.info(f"Nessun dato per «{title}».")
        return
    plot_df = df.copy()
    plot_df[y] = pd.to_numeric(plot_df[y], errors="coerce")
    plot_df = plot_df.dropna(subset=[y])
    if plot_df.empty:
        st.info(f"Nessun dato valido per «{title}».")
        return

    fig = go.Figure(go.Bar(x=plot_df[x], y=plot_df[y], marker_color=color))
    fig.update_layout(title=title)
    _show_chart(fig, height, key, "bar", title, y, x)


def plot_scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    color: str | None = None,
    height: int = 360,
    labels: dict | None = None,
    hover_data: list[str] | None = None,
    key: str | None = None,
):
    if df.empty or x not in df.columns or y not in df.columns:
        st.info(f"Nessun dato per «{title}».")
        return

    plot_df = df.drop(columns=["rules"], errors="ignore").copy()
    for col in (x, y, color):
        if col and col in plot_df.columns:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x, y])
    if plot_df.empty:
        st.info(f"Nessun dato valido per «{title}».")
        return

    marker_kwargs: dict = dict(
        size=9,
        line=dict(width=0.8, color="rgba(255,255,255,0.45)"),
    )
    if color and color in plot_df.columns:
        fig = go.Figure(
            go.Scatter(
                x=plot_df[x],
                y=plot_df[y],
                mode="markers",
                marker=dict(
                    size=9,
                    color=plot_df[color],
                    colorscale="Turbo",
                    showscale=True,
                    colorbar=dict(
                        title=dict(text=color, font=dict(color="#8b949e")),
                        tickfont=dict(color="#8b949e"),
                        outlinecolor="#30363d",
                        bgcolor="#161b22",
                    ),
                    line=dict(width=0.8, color="rgba(255,255,255,0.45)"),
                ),
                text=plot_df[hover_data[0]] if hover_data and hover_data[0] in plot_df.columns else None,
                hovertemplate=f"{x}=%{{x}}<br>{y}=%{{y}}<extra></extra>",
            )
        )
    else:
        marker_kwargs["color"] = "#58a6ff"
        fig = go.Figure(go.Scatter(
            x=plot_df[x], y=plot_df[y], mode="markers", marker=marker_kwargs,
        ))

    if labels:
        fig.update_xaxes(title_text=labels.get(x, x))
        fig.update_yaxes(title_text=labels.get(y, y))
    fig.update_layout(title=title)
    _show_chart(fig, height, key, "scatter", title, y, x)


def plot_histogram(
    values,
    title: str,
    height: int = 320,
    nbins: int = 40,
    color: str = "#58a6ff",
    key: str | None = None,
):
    if values is None or len(values) == 0:
        st.info(f"Nessun dato per «{title}».")
        return
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if arr.empty:
        st.info(f"Nessun dato valido per «{title}».")
        return

    fig = go.Figure(go.Histogram(x=arr, nbinsx=nbins, marker_color=color))
    fig.update_layout(title=title, xaxis_title="Valore")
    _show_chart(fig, height, key, "hist", title)
