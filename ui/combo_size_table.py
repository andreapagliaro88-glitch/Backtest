"""Tabella combinazioni per dimensione — stile dashboard scuro."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pandas as pd
import streamlit as st

from core.pattern_combo_optimizer import combos_per_size, count_pattern_combos, split_combos_by_n
from ui.metric_table import (
    COMBO_RESULT_COLUMNS,
    build_metric_table_html,
    inject_metric_table_css,
    prepare_combo_view,
)

COMBO_SIZE_CSS = """
<style>
.cst-wrap { margin: 0.25rem 0 1rem 0; }
.cst-head-row {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 1rem; margin-bottom: 0.5rem;
}
.cst-head-row h4 { margin: 0; color: #f0f3f6; font-size: 1.15rem; font-weight: 700; }
.cst-sub { color: #8b949e; font-size: 0.82rem; margin-top: 0.2rem; }
.cst-updated { color: #6e7681; font-size: 0.78rem; white-space: nowrap; padding-top: 0.35rem; }
.cst-best-tag { color: #3fb950; font-size: 0.78rem; font-weight: 600; }
</style>
"""


def _group_table_html(sub: pd.DataFrame, stakes_label: str, *, start_icon_idx: int = 0) -> str:
    view = prepare_combo_view(sub, stakes_label=stakes_label)
    return build_metric_table_html(
        view,
        COMBO_RESULT_COLUMNS,
        seed_col="combo",
        stakes_label=stakes_label,
    )


def render_combo_size_overview(
    combo_df: pd.DataFrame,
    patterns: list[str],
    *,
    cfg_key: str,
    stakes_label: str = "",
    active_combo_label: str | None = None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    if combo_df is None or combo_df.empty or not patterns:
        return

    inject_metric_table_css()
    st.markdown(COMBO_SIZE_CSS, unsafe_allow_html=True)

    n = len(patterns)
    groups = split_combos_by_n(combo_df, n)
    expected = combos_per_size(n)
    total_expected = count_pattern_combos(n)
    best_row = combo_df.sort_values(["score", "profit"], ascending=False).iloc[0]
    best_size = int(best_row.get("n_patterns", n))
    parts = [f"{size} → {len(groups.get(size, []))}/{expected[size]}" for size in range(n, 0, -1)]
    updated = datetime.now().strftime("%H:%M")

    if active_combo_label:
        st.caption(
            f"Combinazioni salvate: **{len(combo_df)}** risultati · "
            f"combo attiva **{active_combo_label}** (persiste dopo refresh)"
        )

    h1, h2, h3 = st.columns([5, 1, 1])
    with h1:
        st.markdown("#### Tutte le combinazioni per dimensione")
        st.caption(
            f"**{len(combo_df):,}** risultati su **{total_expected:,}** combinazioni possibili "
            f"({' · '.join(parts)})"
        )
    with h2:
        st.markdown(f'<p class="cst-updated">Aggiornato Oggi, {updated}</p>', unsafe_allow_html=True)
    with h3:
        if on_refresh is not None and st.button(
            "🔄",
            key=f"{cfg_key}_combo_dim_refresh",
            help="Ricalcola combinazioni",
        ):
            on_refresh()
            st.rerun()

    for size in range(n, 0, -1):
        sub = groups.get(size)
        count = 0 if sub is None else len(sub)
        badge = "🟣" if size == 1 else ("🟢" if size == n else "🔵")
        title = f"{badge} {size} pattern — {count}/{expected[size]} combinazioni"
        if size == best_size:
            title += " · Migliore combinazione"

        with st.expander(title, expanded=(size == n)):
            if sub is None or sub.empty:
                st.caption("Nessun risultato.")
            else:
                st.markdown(_group_table_html(sub, stakes_label), unsafe_allow_html=True)
