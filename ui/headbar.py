"""Headbar e navigazione a pill — barra scura con icone."""
from __future__ import annotations

import json

import streamlit as st

# (id, icon, testo)
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("daily", "📅", "Trade Giornaliero"),
    ("combined", "🧩", "Combined"),
    ("ht", "🕐", "HT"),
    ("o15", "📈", "Over 1.5"),
    ("o25", "📈", "Over 2.5"),
    ("sh0", "⚠️", "0 SH"),
    ("sh1", "📈", "1 SH"),
    ("sh2", "📈", "2 SH"),
    ("manual", "✏️", "Manuale"),
    ("compound", "🪙", "Compound €"),
    ("footystats", "📊", "Analisi Campionati"),
]

STRATEGY_SECTIONS_TIER: list[tuple[str, str]] = [
    ("bt", "📈 Backtest attuale"),
    ("tier", "🎯 Ottimizza tier"),
    ("stake_sim", "⚖️ Simula stake"),
    ("combo", "🧩 Combinazioni pattern"),
    ("opt", "⚙️ Ottimizza stake"),
    ("daily", "📅 Trade giornaliero"),
]

STRATEGY_SECTIONS_BASIC: list[tuple[str, str]] = [
    ("bt", "📈 Backtest attuale"),
    ("combo", "🧩 Combinazioni pattern"),
    ("opt", "⚙️ Ottimizza stake"),
    ("daily", "📅 Trade giornaliero"),
]

NAV_SESSION_KEY = "app_nav_page"
NAV_WIDGET_KEY = "app_main_nav"

NAV_LABEL_TO_KEY = {f"{icon} {label}": key for key, icon, label in NAV_ITEMS}
NAV_KEY_TO_LABEL = {key: f"{icon} {label}" for key, icon, label in NAV_ITEMS}


def nav_labels() -> list[str]:
    return list(NAV_LABEL_TO_KEY.keys())


def _pill_nav_css() -> str:
  """CSS globale per tutte le barre pill (anche tab strategia)."""
  return """
/* NAV_V3 */
.element-container[class*="st-key-app_main_nav"] .stButtonGroup,
.element-container[class*="st-key-"][class*="_strategy_nav"] .stButtonGroup {
    width: 100% !important;
    background: linear-gradient(180deg, #1c2028 0%, #111419 100%) !important;
    border: 1px solid #2f3540 !important;
    border-radius: 16px !important;
    padding: 8px 10px 14px !important;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
}
.element-container[class*="st-key-app_main_nav"] [data-testid="stWidgetLabel"],
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-testid="stWidgetLabel"] {
    display: none !important;
}
.element-container[class*="st-key-app_main_nav"] [data-baseweb="button-group"],
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-baseweb="button-group"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 6px !important;
    width: 100% !important;
    overflow-x: auto !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
.element-container[class*="st-key-app_main_nav"] [data-baseweb="button-group"] > button,
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-baseweb="button-group"] > button {
    position: relative !important;
    display: inline-flex !important;
    align-items: center !important;
    height: 2.5rem !important;
    padding: 0 14px !important;
    border-radius: 12px !important;
    border: 1px solid #2a3039 !important;
    background: rgba(0, 0, 0, 0.25) !important;
    color: #eef0f3 !important;
    font-size: 0.86rem !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
}
.element-container[class*="st-key-app_main_nav"] [data-baseweb="button-group"] > button p,
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-baseweb="button-group"] > button p {
    color: inherit !important;
    font-size: 0.86rem !important;
    margin: 0 !important;
}
.element-container[class*="st-key-app_main_nav"] [data-baseweb="button-group"] > button[kind="pills"]:hover,
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-baseweb="button-group"] > button[kind="pills"]:hover {
    background: rgba(255, 255, 255, 0.07) !important;
    border-color: #3d4450 !important;
}
.element-container[class*="st-key-app_main_nav"] [data-baseweb="button-group"] > button[kind="pillsActive"],
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-baseweb="button-group"] > button[kind="pillsActive"] {
    color: #ff5a5c !important;
    background: rgba(255, 90, 92, 0.14) !important;
    border-color: rgba(255, 90, 92, 0.6) !important;
}
.element-container[class*="st-key-app_main_nav"] [data-baseweb="button-group"] > button[kind="pillsActive"] p,
.element-container[class*="st-key-"][class*="_strategy_nav"] [data-baseweb="button-group"] > button[kind="pillsActive"] p {
    color: #ff5a5c !important;
}
.element-container.st-key-app_main_nav {
    position: sticky !important;
    top: 0 !important;
    z-index: 1000 !important;
    margin-bottom: 0.75rem !important;
}
.element-container[class*="st-key-"][class*="_strategy_nav"] {
    margin-bottom: 0.75rem !important;
}
"""


def _apply_nav_bar_js(widget_keys: list[str]) -> None:
    """Forza stili via JS (Streamlit emotion spesso sovrascrive il CSS)."""
    keys = json.dumps(widget_keys)
    st.html(
        f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const keys = {keys};
            function paint() {{
                keys.forEach((k) => {{
                    const root = doc.querySelector('.st-key-' + k);
                    if (!root) return;
                    const wrap = root.querySelector('[data-testid="stButtonGroup"]');
                    if (!wrap) return;
                    wrap.style.setProperty('background', 'linear-gradient(180deg, #1c2028 0%, #111419 100%)', 'important');
                    wrap.style.setProperty('border', '1px solid #2f3540', 'important');
                    wrap.style.setProperty('border-radius', '16px', 'important');
                    wrap.style.setProperty('padding', '8px 10px 14px', 'important');
                    wrap.style.setProperty('box-shadow', '0 12px 32px rgba(0,0,0,0.45)', 'important');
                    const group = wrap.querySelector('[data-baseweb="button-group"]');
                    if (group) {{
                        group.style.setProperty('display', 'flex', 'important');
                        group.style.setProperty('flex-wrap', 'nowrap', 'important');
                        group.style.setProperty('gap', '6px', 'important');
                        group.style.setProperty('overflow-x', 'auto', 'important');
                    }}
                    wrap.querySelectorAll('[data-baseweb="button-group"] > button').forEach((btn) => {{
                        btn.style.setProperty('border-radius', '12px', 'important');
                        btn.style.setProperty('border', '1px solid #2a3039', 'important');
                        btn.style.setProperty('background', 'rgba(0,0,0,0.25)', 'important');
                        btn.style.setProperty('color', '#eef0f3', 'important');
                        btn.style.setProperty('height', '2.5rem', 'important');
                        btn.style.setProperty('padding', '0 14px', 'important');
                        const active = btn.getAttribute('kind') === 'pillsActive';
                        if (active) {{
                            btn.style.setProperty('color', '#ff5a5c', 'important');
                            btn.style.setProperty('background', 'rgba(255,90,92,0.14)', 'important');
                            btn.style.setProperty('border-color', 'rgba(255,90,92,0.6)', 'important');
                            btn.style.boxShadow = '0 0 12px rgba(255,77,79,0.35)';
                        }} else {{
                            btn.style.boxShadow = 'none';
                        }}
                        const p = btn.querySelector('p');
                        if (p) p.style.setProperty('color', active ? '#ff5a5c' : '#eef0f3', 'important');
                    }});
                }});
            }}
            paint();
            setTimeout(paint, 120);
            setTimeout(paint, 400);
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def inject_headbar_styles() -> None:
    st.markdown(
        f"<style>{_pill_nav_css()}</style>",
        unsafe_allow_html=True,
    )


def _render_pill_nav(
    widget_key: str,
    sections: list[tuple[str, str]],
    session_key: str,
) -> str:
    labels = [label for _, label in sections]
    id_by_label = {label: sid for sid, label in sections}
    saved = st.session_state.get(session_key, sections[0][0])
    default_label = next((label for sid, label in sections if sid == saved), labels[0])

    selected = st.pills(
        "Nav",
        options=labels,
        default=default_label,
        key=widget_key,
        label_visibility="collapsed",
        width="stretch",
    )
    if not selected:
        selected = default_label

    section_id = id_by_label.get(selected, sections[0][0])
    st.session_state[session_key] = section_id
    _apply_nav_bar_js([widget_key])
    return section_id


def render_main_nav() -> str:
    inject_headbar_styles()
    labels = nav_labels()
    saved_key = st.session_state.get(NAV_SESSION_KEY, NAV_ITEMS[0][0])
    default_label = NAV_KEY_TO_LABEL.get(saved_key, labels[0])

    selected = st.pills(
        "Navigazione",
        options=labels,
        default=default_label,
        key=NAV_WIDGET_KEY,
        label_visibility="collapsed",
        width="stretch",
    )
    if not selected:
        selected = default_label

    page_key = NAV_LABEL_TO_KEY.get(selected, NAV_ITEMS[0][0])
    st.session_state[NAV_SESSION_KEY] = page_key
    _apply_nav_bar_js([NAV_WIDGET_KEY])
    return page_key


def strategy_nav_key(cfg_key: str) -> str:
    return f"{cfg_key}_strategy_nav"


def strategy_section_session_key(cfg_key: str) -> str:
    return f"{cfg_key}_strategy_section"


def render_strategy_nav(cfg_key: str, *, with_tier: bool) -> str:
    inject_headbar_styles()
    sections = STRATEGY_SECTIONS_TIER if with_tier else STRATEGY_SECTIONS_BASIC
    return _render_pill_nav(
        strategy_nav_key(cfg_key),
        sections,
        strategy_section_session_key(cfg_key),
    )


def render_topbar() -> None:
    inject_headbar_styles()
