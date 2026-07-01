"""Trade giornaliero per singola strategia — stessa logica del tab principale."""
from __future__ import annotations

import os

import streamlit as st

from compound_config import INITIAL_BANKROLL
from core.strategy_daily_fixtures import (
    CFG_SYSTEMS,
    FIXTURE_HINTS,
    delete_fixture,
    file_for_pattern,
    fixtures_dir,
    forced_system_for_cfg,
    list_fixture_files,
    save_fixture_bytes,
    save_pattern_fixture,
)
from ui.daily_trades_tab import render_daily_trades_panel

DAILY_STRATEGY_CSS = """
<style>
.sd-pattern {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 0.65rem 0.85rem; margin-bottom: 0.5rem;
}
.sd-pattern-ok { border-color: #238636; }
.sd-pattern-miss { border-color: #30363d; }
.sd-pname { font-weight: 600; color: #e6edf3; font-size: 0.9rem; }
.sd-pfile { color: #8b949e; font-size: 0.78rem; margin-top: 0.15rem; }
</style>
"""

SUBTITLES: dict[str, str] = {
    "ht": "Upload Fixtures HT + CCS. Solo segnali Half Time.",
    "o15": "Upload Fixtures Over 1.5 + CCS.",
    "o25": "Upload Fixtures Over 2.5 + CCS.",
    "sh0": "Upload Fixtures 0 SH + CCS.",
    "sh1": "Upload Fixtures SH1 + CCS.",
    "sh2": "Upload Fixtures SH2 + CCS.",
    "combined": (
        "Strategia <b>combinata</b> HT/O15/O25 + CCS — stessa orchestrazione del tab principale."
    ),
    "manual": "Template manuale + CCS per trade manuali.",
}


def _pattern_groups(cfg_key: str, patterns: list[str]) -> list[tuple[str, list[str]]]:
    key = cfg_key.lower()
    if key != "combined":
        sys = CFG_SYSTEMS.get(key, (cfg_key.upper(),))[0] if key in CFG_SYSTEMS else cfg_key.upper()
        return [(sys, patterns)]

    groups: list[tuple[str, list[str]]] = []
    for sys in ("HT", "O15", "O25"):
        sub = [p.split(":", 1)[1] for p in patterns if p.startswith(f"{sys}:")]
        if sub:
            groups.append((sys, sub))
    if not groups and patterns:
        return [("Combined", patterns)]
    return groups


def _render_fixture_folder_expander(cfg_key: str, patterns: list[str]) -> None:
    """Gestione opzionale file Fixtures salvati per pattern."""
    folder = fixtures_dir(cfg_key)
    with st.expander("📁 Gestione file Fixtures in cartella", expanded=False):
        st.caption(f"Salva i file del giorno in `{folder}/` per riutilizzarli con il pulsante sopra.")
        bulk = st.file_uploader(
            "Carica più file insieme",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key=f"{cfg_key}_daily_bulk",
        )
        if bulk and st.button("💾 Salva file caricati", key=f"{cfg_key}_daily_bulk_save"):
            for up in bulk:
                save_fixture_bytes(cfg_key, up.name, up.getvalue())
            st.success(f"Salvati **{len(bulk)}** file.")
            st.rerun()

        if patterns:
            st.markdown("**File per pattern**")
            groups = _pattern_groups(cfg_key, patterns)
            for group_label, group_patterns in groups:
                if len(groups) > 1:
                    st.markdown(f"**{group_label}**")
                cols = st.columns(2)
                for i, pattern in enumerate(group_patterns):
                    with cols[i % 2]:
                        existing = file_for_pattern(cfg_key, pattern)
                        css = "sd-pattern sd-pattern-ok" if existing else "sd-pattern sd-pattern-miss"
                        fname = os.path.basename(existing) if existing else "Nessun file"
                        st.markdown(
                            f'<div class="{css}">'
                            f'<div class="sd-pname">{pattern}</div>'
                            f'<div class="sd-pfile">{fname}</div></div>',
                            unsafe_allow_html=True,
                        )
                        up = st.file_uploader(
                            f"Upload {pattern}",
                            type=["xlsx", "xls"],
                            key=f"{cfg_key}_daily_pat_{pattern}",
                            label_visibility="collapsed",
                        )
                        if up is not None and st.button("Salva", key=f"{cfg_key}_daily_save_{pattern}"):
                            save_pattern_fixture(cfg_key, pattern, up.getvalue(), up.name)
                            st.success(f"Salvato **{pattern}**")
                            st.rerun()

        files = list_fixture_files(cfg_key)
        if files:
            for row in files:
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.markdown(f"**{row['file']}** · {row['size_kb']} KB · {row['updated']}")
                with c2:
                    with open(row["path"], "rb") as f:
                        st.download_button(
                            "📥",
                            f.read(),
                            file_name=row["file"],
                            key=f"{cfg_key}_dl_{row['file']}",
                        )
                with c3:
                    if st.button("🗑", key=f"{cfg_key}_del_{row['file']}", help="Elimina"):
                        delete_fixture(cfg_key, row["file"])
                        st.rerun()


def _build_tier_plan(cfg_key: str, system: str | None):
    from core.strategy_daily_plan import StrategyDailyPlanConfig
    from core.tier_engine import rules_for_pattern_combo
    from ui.strategy_dashboard import active_patterns_key
    from ui.tier_metodo import active_tier_rules, supports_tier

    if not system or not supports_tier(system):
        return None
    active_pats = tuple(st.session_state.get(active_patterns_key(cfg_key)) or ())
    if not active_pats:
        return None
    base_rules = active_tier_rules(cfg_key, system)
    combo_rules = rules_for_pattern_combo(active_pats, base_rules)
    return StrategyDailyPlanConfig(
        system=system,
        rules=combo_rules,
        active_patterns=active_pats,
    )


def render_strategy_daily_tab(
    cfg_key: str,
    strategy_title: str,
    patterns: list[str],
    *,
    system: str | None = None,
    initial_bankroll: float = INITIAL_BANKROLL,
) -> None:
    st.markdown(DAILY_STRATEGY_CSS, unsafe_allow_html=True)

    key = cfg_key.lower()
    allowed = CFG_SYSTEMS.get(key, ())
    forced = forced_system_for_cfg(key)
    if key == "combined":
        journal_filter: str | tuple[str, ...] | None = ("HT", "O15", "O25")
    elif forced:
        journal_filter = forced
    else:
        journal_filter = None

    subtitle = SUBTITLES.get(key, f"Trade giornaliero per {strategy_title} + CCS.")
    hint = FIXTURE_HINTS.get(key)
    tier_plan = _build_tier_plan(cfg_key, system or forced)

    from ui.tier_metodo import format_stakes_summary, supports_tier as _supports_tier
    if system and _supports_tier(system):
        from ui.strategy_dashboard import active_patterns_key, get_active_combo_label

        active_pats = tuple(st.session_state.get(active_patterns_key(cfg_key)) or ())
        combo_label = get_active_combo_label(cfg_key)
        if tier_plan:
            st.success(
                f"**Combo attiva:** {combo_label or ' + '.join(active_pats)} · "
                f"**Stake:** {format_stakes_summary(cfg_key, system, tier_plan.rules)} · "
                f"**Pattern usati:** {len(active_pats)}"
            )
        else:
            st.warning(
                "Nessuna combinazione pattern selezionata. "
                "Vai su **Combinazioni pattern**, scegli una combo e clicca **Usa nel riepilogo**."
            )

    render_daily_trades_panel(
        scope=cfg_key,
        title=f"Trade giornaliero — {strategy_title}",
        subtitle=subtitle,
        initial_bankroll=initial_bankroll,
        allowed_systems=allowed or None,
        forced_system=forced,
        journal_strategia_filter=journal_filter,
        fixture_hint=hint,
        cfg_key=cfg_key,
        tier_plan=tier_plan,
    )

    _render_fixture_folder_expander(cfg_key, patterns)
