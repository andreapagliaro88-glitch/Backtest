"""Stile Plotly condiviso — tema scuro Streamlit."""
from __future__ import annotations

import re

import pandas as pd
import plotly.express as px
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
    fig.update_layout(**PLOT_LAYOUT, height=height, showlegend=showlegend)
    fig.update_xaxes(**PLOT_LAYOUT["xaxis"])
    fig.update_yaxes(**PLOT_LAYOUT["yaxis"])
    return fig


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

    plot_df = df.drop(columns=["rules"], errors="ignore")
    kwargs = dict(x=x, y=y, labels=labels or {})
    if color and color in plot_df.columns:
        kwargs["color"] = color
        kwargs["color_continuous_scale"] = "Turbo"
    if hover_data:
        kwargs["hover_data"] = [c for c in hover_data if c in plot_df.columns]

    fig = px.scatter(plot_df, **kwargs, opacity=0.9)
    fig.update_traces(
        marker=dict(
            size=10,
            line=dict(width=1, color="rgba(255,255,255,0.35)"),
        ),
    )
    if color and color in plot_df.columns:
        fig.update_layout(
            coloraxis_colorbar=dict(
                title=dict(text=color.capitalize(), font=dict(color="#8b949e")),
                tickfont=dict(color="#8b949e"),
                outlinecolor="#30363d",
                bgcolor="#161b22",
            ),
        )
    fig.update_layout(title=title)
    chart_key = _chart_key(key, "scatter", title, y, x)
    st.plotly_chart(
        style_figure(fig, height, showlegend=bool(color)),
        use_container_width=True,
        config=PLOTLY_CONFIG,
        key=chart_key,
    )


def _trade_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index(drop=True).copy()
    out["trade_n"] = range(1, len(out) + 1)
    return out


def _chart_key(key: str | None, kind: str, title: str, *parts: str) -> str:
    if key:
        return key
    slug = re.sub(r"[^\w]+", "_", f"{kind}_{title}_{'_'.join(parts)}".lower()).strip("_")
    return slug[:120] or kind


def plot_line(
    df: pd.DataFrame,
    y: str,
    title: str,
    x: str = "trade_n",
    height: int = 320,
    color: str = "#58a6ff",
    fill: bool = False,
    key: str | None = None,
):
    if df.empty or y not in df.columns:
        st.info(f"Nessun dato per «{title}».")
        return
    if x == "trade_n":
        df = _trade_index(df)
    if fill:
        fig = px.area(df, x=x, y=y)
        fig.update_traces(line_color=color, fillcolor=_hex_rgba(color))
    else:
        fig = px.line(df, x=x, y=y)
        fig.update_traces(line_color=color, line_width=2)
    fig.update_layout(title=title)
    chart_key = _chart_key(key, "line", title, y, x)
    st.plotly_chart(
        style_figure(fig, height),
        use_container_width=True,
        config=PLOTLY_CONFIG,
        key=chart_key,
    )


def plot_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    height: int = 280,
    color: str = "#58a6ff",
    key: str | None = None,
):
    if df.empty:
        st.info(f"Nessun dato per «{title}».")
        return
    fig = px.bar(df, x=x, y=y)
    fig.update_traces(marker_color=color)
    fig.update_layout(title=title)
    chart_key = _chart_key(key, "bar", title, y, x)
    st.plotly_chart(
        style_figure(fig, height),
        use_container_width=True,
        config=PLOTLY_CONFIG,
        key=chart_key,
    )


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
    fig = px.histogram(x=values, nbins=nbins, labels={"x": "Valore"})
    fig.update_traces(marker_color=color)
    fig.update_layout(title=title)
    chart_key = _chart_key(key, "hist", title)
    st.plotly_chart(
        style_figure(fig, height),
        use_container_width=True,
        config=PLOTLY_CONFIG,
        key=chart_key,
    )
