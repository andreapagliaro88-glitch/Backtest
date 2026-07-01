"""Dashboard riutilizzabile: backtest + combinazioni pattern + ottimizza stake."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable

import pandas as pd
import streamlit as st

import ui.combo_size_table as _combo_size_table_module
import ui.headbar as _headbar_module
importlib.reload(_headbar_module)
importlib.reload(_combo_size_table_module)

from compound_config import INITIAL_BANKROLL
from core.ccs_runner import enrich_trades_with_eur, format_trades_eur_display, run_ccs_on_backtest_df
from core.pattern_combo_optimizer import (
    best_combos,
    combos_per_size,
    count_pattern_combos,
    list_available_patterns,
    optimize_pattern_combos,
    optimize_tier_pattern_combos,
    split_combos_by_n,
)
from core.strategy_state_store import hydrate_session, persist_from_session
from ui.combo_size_table import render_combo_size_overview
from ui.headbar import render_strategy_nav
from ui.metric_table import (
    COMBO_RESULT_COLUMNS,
    OPT_STAKE_COLUMNS,
    prepare_combo_view,
    render_metric_table,
    render_simple_table,
)
from ui.plot_theme import plot_bar, plot_line
from ui.strategy_daily_tab import render_strategy_daily_tab
from ui.tier_metodo import (
    active_tier_rules,
    apply_stake_rules,
    format_stakes_summary,
    render_stake_simulator_fragment,
    render_tier_optimizer_fragment,
    show_active_config_banner,
    show_tier_metodo_panel,
    show_tier_workflow_guide,
    stakes_fingerprint,
    supports_tier,
)

STRATEGY_CSS = """
<style>
    .strat-best {
        background: #0d1f14; border: 1px solid #238636; border-radius: 10px;
        padding: 0.75rem 1rem; margin-bottom: 0.5rem;
    }
</style>
"""


@dataclass
class StrategyConfig:
    key: str
    title: str
    data_hint: str
    system: str | None
    run_backtest: Callable
    optimize_stake: Callable
    format_params: Callable
    optimize_combos: Callable | None = None
    df_raw: pd.DataFrame | None = None
    df_grouped: pd.DataFrame | None = None
    stake_label: str = "Ottimizza stake"


def _ccs_metric_cards(ccs, initial_bankroll: float):
    s = ccs.summary()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bankroll finale", f"{s['final_bankroll']:,.2f} €")
    c2.metric("Profitto totale", f"{s['total_profit_eur']:,.2f} €")
    c3.metric("ROI", f"{s['roi_pct']:.2f}%")
    c4.metric("Max DD", f"{s['max_dd_eur']:,.2f} €")
    c5.metric("1U attuale", f"{s['current_unit_eur']:.2f} €")
    c6.metric("Prelievi", f"{s['n_withdrawals']} ({s['total_withdrawn']:,.0f} €)")
    c7, c8, c9 = st.columns(3)
    c7.metric("Bankroll iniziale", f"{initial_bankroll:,.2f} €")
    c8.metric("Trade CCS", s["trades"])
    c9.metric("Winrate", f"{s['winrate'] * 100:.1f}%")


def _ccs_equity_charts(df_ccs: pd.DataFrame, title: str, key_prefix: str = "ccs"):
    if df_ccs.empty:
        st.warning("Nessun trade CCS (bankroll insufficiente o nessun ingresso).")
        return

    col1, col2 = st.columns(2)
    with col1:
        plot_line(
            df_ccs, y="bankroll", title=f"Bankroll — {title}",
            color="#58a6ff", fill=True, key=f"{key_prefix}_bankroll",
        )
    with col2:
        y_eq = "equity_eur" if "equity_eur" in df_ccs.columns else "bankroll"
        plot_line(
            df_ccs, y=y_eq, title=f"Equity — {title}",
            color="#3fb950", fill=True, key=f"{key_prefix}_equity",
        )

    col3, col4 = st.columns(2)
    with col3:
        plot_line(
            df_ccs, y="dd_eur", title="Drawdown (€)", color="#f85149",
            fill_to_zero=True, key=f"{key_prefix}_dd_eur",
        )
    with col4:
        plot_line(
            df_ccs, y="dd_pct", title="Drawdown (%)", color="#d29922",
            fill_to_zero=True, key=f"{key_prefix}_dd_pct",
        )

    monthly = df_ccs.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly_profit = monthly.groupby(monthly["date"].dt.to_period("M"))["profit_eur"].sum().reset_index()
    monthly_profit["date"] = monthly_profit["date"].astype(str)
    plot_bar(
        monthly_profit, x="date", y="profit_eur",
        title=f"Profitto mensile (€) — {title}", color="#58a6ff",
        key=f"{key_prefix}_monthly",
    )


def _render_ccs_backtest(
    df_trades: pd.DataFrame,
    title: str,
    cfg_key: str,
    section: str = "bt",
    system: str | None = None,
):
    """Backtest con CCS: la strategia decide gli ingressi, CCS gestisce 1U in €."""
    tier_system = system or cfg_key.upper()
    prefix = f"{cfg_key}_{section}"
    bankroll = st.number_input(
        "Bankroll iniziale (€)",
        min_value=50.0,
        value=float(INITIAL_BANKROLL),
        step=50.0,
        key=f"{prefix}_bankroll_in",
    )
    st.caption(
        "Controlled Compounding: ingressi dalla strategia (stake U > 0) · "
        "stake in € = Stake (U) × 1U allo scaglione · prelievo a 6000€"
    )

    df_ccs, ccs = run_ccs_on_backtest_df(df_trades, bankroll)
    _ccs_metric_cards(ccs, bankroll)
    _ccs_equity_charts(df_ccs, title, key_prefix=f"{prefix}_plot")

    if ccs.withdrawals:
        with st.expander("Prelievi CCS"):
            wd = pd.DataFrame(ccs.withdrawals_dataframe_rows())
            cols = [{"key": c, "label": c, "kind": "text"} for c in wd.columns]
            render_simple_table(wd, cols)

    if ccs.tiers_reached:
        with st.expander("Scaglioni 1U raggiunti"):
            tr = pd.DataFrame(ccs.tiers_dataframe_rows())
            cols = [{"key": c, "label": c, "kind": "text"} for c in tr.columns]
            render_simple_table(tr, cols)

    df_display = enrich_trades_with_eur(df_trades, df_ccs)
    n_skip = int((df_display["ingresso"] == "SKIP").sum()) if not df_display.empty else 0
    expand_trades = supports_tier(tier_system)
    with st.expander("Dettaglio trade (tier U + CCS €)", expanded=expand_trades):
        if n_skip:
            st.caption(f"Ingressi: {len(df_ccs)} · Saltati dalla strategia: {n_skip}")
        if supports_tier(tier_system):
            st.caption(
                "**Stake (U)** = puntata Metodo tier. "
                "**Stake CCS (€)** = Stake (U) × **1U (€)** allo scaglione bankroll attuale."
            )
        if supports_tier(tier_system) and not df_display.empty and "patterns_str" in df_display.columns:
            skip_pat = df_display.loc[df_display["ingresso"] == "SKIP", "patterns_str"]
            if not skip_pat.empty:
                top_skip = skip_pat.value_counts().head(5)
                st.caption(
                    "Pattern più saltati: "
                    + " · ".join(f"{p} ({n})" for p, n in top_skip.items())
                )
        trades_view = format_trades_eur_display(df_display)
        trade_cols = [{"key": c, "label": c, "kind": "text"} for c in trades_view.columns]
        if "Profitto (€)" in trades_view.columns:
            for col in trade_cols:
                if col["key"] == "Profitto (€)":
                    col["kind"] = "profit_signed"
        render_simple_table(trades_view, trade_cols, seed_col=trades_view.columns[0])


def active_patterns_key(cfg_key: str) -> str:
    return f"{cfg_key}_active_patterns"


def active_combo_label_key(cfg_key: str) -> str:
    return f"{cfg_key}_active_combo_label"


def patterns_from_combo_row(row) -> tuple[str, ...] | None:
    raw = row.get("patterns")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    return tuple(raw) if not isinstance(raw, tuple) else raw


def patterns_dirty_key(cfg_key: str) -> str:
    return f"{cfg_key}_patterns_dirty"


def bt_patterns_key(cfg_key: str) -> str:
    return f"{cfg_key}_bt_patterns"


def bt_trades_key(cfg_key: str) -> str:
    return f"{cfg_key}_bt_trades"


def _run_strategy_backtest(cfg: StrategyConfig, df_raw: pd.DataFrame, patterns: list[str] | None):
    pat = tuple(patterns) if patterns else None
    tier_rules = active_tier_rules(cfg.key, cfg.system) if supports_tier(cfg.system) else None
    if cfg.key == "combined":
        return cfg.run_backtest(df_raw)
    if supports_tier(cfg.system):
        return cfg.run_backtest(df_raw, pat, tier_rules=tier_rules)
    if cfg.system and patterns is not None:
        return cfg.run_backtest(df_raw, pat)
    return cfg.run_backtest(df_raw)


def _sync_bt_patterns_widget(cfg_key: str, options: list[str]) -> None:
    """Aggiorna il multiselect backtest solo prima che il widget venga creato."""
    if not st.session_state.get(patterns_dirty_key(cfg_key)):
        return
    active = st.session_state.get(active_patterns_key(cfg_key))
    if active:
        st.session_state[bt_patterns_key(cfg_key)] = [p for p in active if p in options]
    st.session_state.pop(patterns_dirty_key(cfg_key), None)


def combo_summary_dirty_key(cfg_key: str) -> str:
    return f"{cfg_key}_combo_summary_dirty"


def _sync_combo_summary_pick(cfg_key: str, options: list[str]) -> None:
    """Allinea il selectbox alla combo attiva prima che il widget venga creato."""
    if not st.session_state.get(combo_summary_dirty_key(cfg_key)):
        return
    label = get_active_combo_label(cfg_key)
    pick_key = f"{cfg_key}_combo_summary_pick"
    if label and label in options:
        st.session_state[pick_key] = label
    elif options:
        st.session_state[pick_key] = options[0]
    st.session_state.pop(combo_summary_dirty_key(cfg_key), None)


def set_active_combo(cfg_key: str, patterns: tuple[str, ...] | None, combo_label: str = ""):
    if patterns:
        st.session_state[active_patterns_key(cfg_key)] = tuple(patterns)
        st.session_state[active_combo_label_key(cfg_key)] = combo_label
        st.session_state[patterns_dirty_key(cfg_key)] = True
        if combo_label:
            st.session_state[combo_summary_dirty_key(cfg_key)] = True
    else:
        st.session_state.pop(active_patterns_key(cfg_key), None)
        st.session_state.pop(active_combo_label_key(cfg_key), None)
    persist_from_session(cfg_key, st.session_state)


def _persist_combo_state(cfg_key: str):
    persist_from_session(cfg_key, st.session_state)


def get_active_combo_label(cfg_key: str) -> str | None:
    return st.session_state.get(active_combo_label_key(cfg_key))


def _combo_results_key(cfg_key: str) -> str:
    return f"{cfg_key}_combo_results"


def _needs_combo_recompute(cfg: StrategyConfig, patterns: list[str], *, force: bool = False) -> bool:
    """True solo se l'utente forza il ricalcolo (pulsante) o non ci sono ancora risultati."""
    combo_df = st.session_state.get(_combo_results_key(cfg.key))
    if combo_df is None or combo_df.empty:
        return bool(patterns)
    if not force:
        return False
    return True


def _combo_is_outdated(cfg: StrategyConfig) -> bool:
    """Stake/tier cambiati rispetto all'ultimo calcolo combinazioni."""
    if st.session_state.get(f"{cfg.key}_combo_stale"):
        return True
    if supports_tier(cfg.system):
        rules = active_tier_rules(cfg.key, cfg.system)
        fp = st.session_state.get(f"{cfg.key}_combo_stakes_fp")
        if fp and fp != stakes_fingerprint(cfg.key, cfg.system, rules):
            return True
    return False


def _cached_combo_results(cfg_key: str) -> pd.DataFrame:
    df = st.session_state.get(_combo_results_key(cfg_key))
    return df if df is not None else pd.DataFrame()


def _compute_pattern_combos(
    cfg: StrategyConfig,
    patterns: list[str],
    df_raw: pd.DataFrame,
    *,
    progress_callback=None,
) -> pd.DataFrame:
    if supports_tier(cfg.system):
        tier_rules = active_tier_rules(cfg.key, cfg.system)
        sys_df = df_raw[df_raw["system"] == cfg.system].copy() if "system" in df_raw.columns else df_raw
        combo_df = optimize_tier_pattern_combos(
            sys_df,
            cfg.system,
            tier_rules,
            patterns=patterns,
            progress_callback=progress_callback,
        )
        st.session_state[f"{cfg.key}_combo_stakes_fp"] = stakes_fingerprint(cfg.key, cfg.system, tier_rules)
        st.session_state[f"{cfg.key}_combo_stakes_label"] = format_stakes_summary(cfg.key, cfg.system, tier_rules)
        st.session_state[f"{cfg.key}_combo_stale"] = False
    elif cfg.optimize_combos:
        combo_df = cfg.optimize_combos(df_raw)
    else:
        combo_df = optimize_pattern_combos(
            df_raw,
            lambda d, p: cfg.run_backtest(d, p),
            patterns=patterns,
            system=cfg.system,
        )
    return combo_df


def _ensure_pattern_combos(
    cfg: StrategyConfig,
    patterns: list[str],
    df_raw: pd.DataFrame,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Calcola combinazioni solo su richiesta esplicita (evita blocchi al caricamento tab)."""
    combo_key = _combo_results_key(cfg.key)
    if not patterns or cfg.key == "combined":
        return _cached_combo_results(cfg.key)

    if not _needs_combo_recompute(cfg, patterns, force=force):
        return _cached_combo_results(cfg.key)

    n_combos = count_pattern_combos(len(patterns))
    progress = st.progress(0.0, text="Calcolo combinazioni…") if n_combos > 64 else None

    def _on_progress(p: float):
        if progress is not None:
            progress.progress(p, text=f"Calcolo combinazioni… {int(p * 100)}%")

    try:
        combo_df = _compute_pattern_combos(
            cfg,
            patterns,
            df_raw,
            progress_callback=_on_progress if progress else None,
        )
        st.session_state[combo_key] = combo_df
        if combo_df is not None and not combo_df.empty:
            if not st.session_state.get(active_patterns_key(cfg.key)):
                best = combo_df.sort_values("score", ascending=False).iloc[0]
                pats = patterns_from_combo_row(best)
                set_active_combo(cfg.key, pats, str(best.get("combo", "")))
        _persist_combo_state(cfg.key)
    except Exception as exc:
        st.error(f"Errore nel calcolo combinazioni: {exc}")
    finally:
        if progress is not None:
            progress.empty()

    return _cached_combo_results(cfg.key)


def _stakes_label_for_combo(cfg: StrategyConfig) -> str:
    if supports_tier(cfg.system):
        return st.session_state.get(f"{cfg.key}_combo_stakes_label") or format_stakes_summary(cfg.key, cfg.system)
    return ""


def _render_combo_size_overview(
    combo_df: pd.DataFrame,
    patterns: list[str],
    cfg: StrategyConfig,
    df_raw: pd.DataFrame | None = None,
):
    """Mostra tutte le combinazioni raggruppate per dimensione (UI dashboard)."""
    render_combo_size_overview(
        combo_df,
        patterns,
        cfg_key=cfg.key,
        stakes_label=_stakes_label_for_combo(cfg),
        active_combo_label=get_active_combo_label(cfg.key),
        on_refresh=(
            (lambda: _ensure_pattern_combos(cfg, patterns, df_raw, force=True))
            if df_raw is not None
            else None
        ),
    )


def _metric_threshold_kwargs(
    min_profit: float,
    min_max_dd: float,
    min_trades: int | float,
    min_winrate: float,
    min_calmar: float,
) -> dict:
    return {
        "min_profit": None if min_profit <= -900 else min_profit,
        "min_max_dd": None if min_max_dd <= -900 else min_max_dd,
        "min_trades": int(min_trades) if min_trades > 0 else None,
        "min_winrate_pct": float(min_winrate) if min_winrate > 0 else None,
        "min_calmar": float(min_calmar) if min_calmar > 0 else None,
    }


def _apply_metric_filters(
    df: pd.DataFrame,
    *,
    search_col: str | None = None,
    search: str = "",
    min_profit: float | None = None,
    min_max_dd: float | None = None,
    min_trades: int | None = None,
    min_winrate_pct: float | None = None,
    min_calmar: float | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    view = df.copy()
    if search and search.strip() and search_col and search_col in view.columns:
        q = search.strip().lower()
        view = view[view[search_col].astype(str).str.lower().str.contains(q, regex=False)]

    if min_profit is not None:
        view = view[view["profit"] >= min_profit]
    if min_max_dd is not None:
        view = view[view["max_dd"] >= min_max_dd]
    if min_trades is not None and min_trades > 0:
        view = view[view["trades"] >= min_trades]
    if min_winrate_pct is not None and min_winrate_pct > 0:
        view = view[view["winrate"] * 100 >= min_winrate_pct]
    if min_calmar is not None and min_calmar > 0:
        view = view[view["calmar"] >= min_calmar]

    return view


def _apply_combo_filters(
    combo_df: pd.DataFrame,
    *,
    size_filter: str,
    search: str = "",
    include_patterns: list[str] | None = None,
    min_profit: float | None = None,
    min_max_dd: float | None = None,
    min_trades: int | None = None,
    min_winrate_pct: float | None = None,
    min_calmar: float | None = None,
) -> pd.DataFrame:
    """Applica filtri alla tabella combinazioni."""
    if combo_df.empty:
        return combo_df

    view = combo_df.copy()

    if size_filter and size_filter != "Tutte le dimensioni" and size_filter.endswith("pattern"):
        try:
            size = int(size_filter.split()[0])
            view = view[view["n_patterns"] == size]
        except ValueError:
            pass

    if search and search.strip():
        q = search.strip().lower()
        view = view[view["combo"].astype(str).str.lower().str.contains(q, regex=False)]

    if include_patterns:
        must = set(include_patterns)

        def _has_patterns(row) -> bool:
            raw = row.get("patterns")
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                return False
            pats = set(raw) if isinstance(raw, (list, tuple, set)) else {raw}
            return must.issubset(pats)

        view = view[view.apply(_has_patterns, axis=1)]

    return _apply_metric_filters(
        view,
        min_profit=min_profit,
        min_max_dd=min_max_dd,
        min_trades=min_trades,
        min_winrate_pct=min_winrate_pct,
        min_calmar=min_calmar,
    )


def _apply_opt_filters(
    results_df: pd.DataFrame,
    *,
    search: str = "",
    min_profit: float | None = None,
    min_max_dd: float | None = None,
    min_trades: int | None = None,
    min_winrate_pct: float | None = None,
    min_calmar: float | None = None,
) -> pd.DataFrame:
    """Applica filtri alla tabella ottimizzazione stake."""
    return _apply_metric_filters(
        results_df,
        search_col="params_str",
        search=search,
        min_profit=min_profit,
        min_max_dd=min_max_dd,
        min_trades=min_trades,
        min_winrate_pct=min_winrate_pct,
        min_calmar=min_calmar,
    )


def _combo_size_filter_options(n_patterns: int) -> list[str]:
    return ["Tutte le dimensioni"] + [f"{k} pattern" for k in range(n_patterns, 0, -1)]


def _render_combo_tab(cfg: StrategyConfig, patterns: list[str], df_raw: pd.DataFrame):
    st.markdown("### Tutte le combinazioni di pattern")

    if supports_tier(cfg.system):
        rules = active_tier_rules(cfg.key, cfg.system)
        show_active_config_banner(cfg.key, cfg.system, always=True)
        st.caption(
            "**Passo 3/3** — Con tier e stake già impostati (passi 1–2), "
            "trova **quali pattern includere**. Profit/DD usano gli stake attive."
        )
        if _combo_is_outdated(cfg):
            st.warning(
                "⚠️ Tier o stake cambiati dall'ultimo calcolo. "
                "Clicca **Ricalcola combinazioni** per aggiornare tutti i subset."
            )

    if not patterns:
        st.error(
            "Nessun pattern rilevato nei file Excel. "
            "Verifica che i file siano in `data/ht/`, `data/over15/` o `data/over25/` "
            "e clicca **Aggiorna dati** in alto."
        )
        return

    n_combos = count_pattern_combos(len(patterns)) if patterns else 0
    if n_combos:
        per_size = combos_per_size(len(patterns))
        breakdown = " + ".join(f"{k}×{v}" for k, v in sorted(per_size.items(), reverse=True))
        st.caption(
            f"**{n_combos:,}** combinazioni totali ({breakdown}). "
            "Score = Profit + 0.6 × Max DD."
            + (" · calcolo ottimizzato tier" if supports_tier(cfg.system) else "")
        )

    combo_key = _combo_results_key(cfg.key)
    has_cached = not _cached_combo_results(cfg.key).empty
    btn_label = "🔄 Ricalcola combinazioni" if has_cached else "🔍 Calcola tutte le combinazioni"

    if st.button(btn_label, type="primary", key=f"{cfg.key}_run_combos"):
        n_combos = count_pattern_combos(len(patterns)) if patterns else 0
        progress = st.progress(0.0, text="Calcolo combinazioni…") if n_combos > 64 else None

        def _on_progress(p: float):
            if progress is not None:
                progress.progress(p, text=f"Calcolo combinazioni… {int(p * 100)}%")

        with st.spinner("Calcolo in corso..."):
            try:
                combo_df = _ensure_pattern_combos(cfg, patterns, df_raw, force=True)
                if combo_df is not None and not combo_df.empty:
                    best = combo_df.sort_values("score", ascending=False).iloc[0]
                    pats = patterns_from_combo_row(best)
                    set_active_combo(cfg.key, pats, str(best.get("combo", "")))
                    st.success(
                        f"✅ **{len(combo_df)}** combinazioni calcolate. "
                        f"Migliore per score: **{best['combo']}**"
                    )
                else:
                    st.warning("Nessuna combinazione ha prodotto risultati.")
            except Exception as exc:
                st.error(f"Errore nel calcolo combinazioni: {exc}")
            finally:
                if progress is not None:
                    progress.empty()

    combo_df = _cached_combo_results(cfg.key)
    if combo_df.empty:
        st.info(
            "Clicca **Calcola tutte le combinazioni** per testare ogni subset di pattern "
            "(da tutti i file fino ai singoli)."
        )
        return

    if supports_tier(cfg.system):
        stakes_label = st.session_state.get(f"{cfg.key}_combo_stakes_label") or format_stakes_summary(cfg.key, cfg.system)
        st.markdown(f"**Stake usati nel calcolo:** `{stakes_label}`")

    bests = best_combos(combo_df)
    cols = st.columns(4)
    for col, (label, bkey) in zip(cols, [
        ("Miglior score", "score"),
        ("Max profitto", "profit"),
        ("Min drawdown", "min_dd"),
        ("Miglior Calmar", "calmar"),
    ]):
        row = bests[bkey]
        with col:
            st.markdown(f"**{label}**")
            st.markdown(
                f'<div class="strat-best"><b>{row["combo"]}</b><br>'
                f'Profit {row["profit"]:.1f} U · DD {row["max_dd"]:.1f} U · '
                f'{int(row["trades"])} trade</div>',
                unsafe_allow_html=True,
            )

    sort_by = st.selectbox(
        "Ordina per",
        ["score", "profit", "max_dd", "calmar", "winrate", "trades", "n_patterns"],
        key=f"{cfg.key}_combo_sort",
    )
    n_pat = len(patterns)

    st.markdown("#### 🔎 Filtri combinazioni")
    f1, f2, f3, f4 = st.columns(4)
    size_filter = f1.selectbox(
        "N° pattern",
        _combo_size_filter_options(n_pat),
        key=f"{cfg.key}_combo_size_filter",
    )
    search = f2.text_input(
        "Cerca nel nome",
        placeholder="es. Carry + Drive",
        key=f"{cfg.key}_combo_search",
    )
    include_patterns = f3.multiselect(
        "Deve includere",
        options=patterns,
        default=[],
        key=f"{cfg.key}_combo_include_pat",
        help="Mostra solo combinazioni che contengono tutti i pattern selezionati.",
    )
    min_trades = f4.number_input(
        "Trade min.",
        min_value=0,
        value=0,
        step=10,
        key=f"{cfg.key}_combo_min_trades",
    )

    g1, g2, g3, g4 = st.columns(4)
    min_profit = g1.number_input(
        "Profit min. (U)",
        value=-999.0,
        step=5.0,
        key=f"{cfg.key}_combo_min_profit",
    )
    min_max_dd = g2.number_input(
        "DD min. (U)",
        value=-999.0,
        step=1.0,
        key=f"{cfg.key}_combo_min_dd",
        help="Es. -15 → esclude DD peggiori di -15 U.",
    )
    min_winrate = g3.number_input(
        "Winrate min. (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=1.0,
        key=f"{cfg.key}_combo_min_wr",
    )
    min_calmar = g4.number_input(
        "Calmar min.",
        min_value=0.0,
        value=0.0,
        step=0.5,
        key=f"{cfg.key}_combo_min_calmar",
    )

    ascending = sort_by == "max_dd"
    view = combo_df.sort_values(
        ["n_patterns", sort_by, "profit"],
        ascending=[False, ascending, False],
    ).copy()
    view = _apply_combo_filters(
        view,
        size_filter=size_filter,
        search=search,
        include_patterns=include_patterns or None,
        **_metric_threshold_kwargs(min_profit, min_max_dd, min_trades, min_winrate, min_calmar),
    )
    stakes_label = _stakes_label_for_combo(cfg)
    st.caption(f"**{len(view):,}** combinazioni mostrate su **{len(combo_df):,}** totali")

    if view.empty:
        st.warning("Nessuna combinazione con i filtri selezionati. Allarga i filtri o resetta i valori.")
        return

    combo_view = prepare_combo_view(view, stakes_label=stakes_label)
    render_metric_table(combo_view, COMBO_RESULT_COLUMNS, stakes_label=stakes_label)

    st.download_button(
        "📥 Scarica CSV combinazioni",
        combo_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{cfg.key}_combo_optimization.csv",
        mime="text/csv",
        key=f"{cfg.key}_dl_combo",
    )

    col_a, col_b = st.columns([3, 1])
    combo_options = view["combo"].tolist()
    _sync_combo_summary_pick(cfg.key, combo_options)
    with col_a:
        active_label = get_active_combo_label(cfg.key)
        default_index = (
            combo_options.index(active_label)
            if active_label in combo_options else 0
        )
        sel_combo = st.selectbox(
            "Combinazione per riepilogo",
            combo_options,
            index=default_index,
            key=f"{cfg.key}_combo_summary_pick",
        )
    with col_b:
        st.write("")
        st.write("")
        if st.button("Applica al riepilogo", type="primary", key=f"{cfg.key}_apply_summary"):
            row = combo_df[combo_df["combo"] == sel_combo].iloc[0]
            set_active_combo(cfg.key, patterns_from_combo_row(row), sel_combo)
            st.success(f"Riepilogo aggiornato: **{sel_combo}**")

    active_label = get_active_combo_label(cfg.key)
    if active_label:
        st.info(f"**Riepilogo in alto:** {active_label}")

    pat_row = combo_df[combo_df["combo"] == sel_combo].iloc[0]

    if cfg.key == "combined":
        detail_trades = cfg.run_backtest(
            df_raw,
            pat_row.get("ht_patterns") or None,
            pat_row.get("o15_patterns") or None,
            pat_row.get("o25_patterns") or None,
        )
    else:
        raw_pats = pat_row.get("patterns")
        if raw_pats is None or (isinstance(raw_pats, float) and pd.isna(raw_pats)):
            pat_tuple = None
        elif isinstance(raw_pats, tuple):
            pat_tuple = raw_pats
        else:
            pat_tuple = tuple(raw_pats)
        if supports_tier(cfg.system):
            detail_trades = cfg.run_backtest(df_raw, pat_tuple, tier_rules=active_tier_rules(cfg.key, cfg.system))
        else:
            detail_trades = cfg.run_backtest(df_raw, pat_tuple)
    _render_ccs_backtest(detail_trades, sel_combo, cfg.key, section="combo", system=cfg.system)


@st.fragment
def _render_combo_tab_fragment(cfg: StrategyConfig, patterns: list[str], df_raw: pd.DataFrame):
    """Fragment: click su Calcola combinazioni non resetta la tab attiva."""
    try:
        _render_combo_tab(cfg, patterns, df_raw)
    except Exception as exc:
        st.error(f"Errore tab combinazioni: {exc}")


def _render_opt_pick_comparison(
    baseline: dict,
    picked: pd.Series,
    rank: int,
    format_params: Callable,
):
    """Confronto metriche tra baseline e configurazione selezionata."""
    st.markdown(f"### Confronto — baseline vs selezionato **#{rank}**")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Profit (U)",
        f"{picked['profit']:.2f}",
        f"{picked['profit'] - baseline['profit']:+.2f}",
    )
    m2.metric(
        "Max DD (U)",
        f"{picked['max_dd']:.2f}",
        f"{picked['max_dd'] - baseline['max_dd']:+.2f}",
        delta_color="inverse",
    )
    m3.metric(
        "Score",
        f"{picked['score']:.2f}",
        f"{picked['score'] - baseline['score']:+.2f}",
    )
    m4.metric(
        "Calmar",
        f"{picked['calmar']:.2f}",
        f"{picked['calmar'] - baseline.get('calmar', 0):+.2f}",
    )

    m5, m6 = st.columns(2)
    m5.metric("Trade", int(picked["trades"]))
    m6.metric("Winrate", f"{picked['winrate'] * 100:.1f}%")
    wr_delta = (picked["winrate"] - baseline.get("winrate", 0)) * 100
    m6.caption(f"Δ winrate: {wr_delta:+.1f} pp")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Baseline (attuale)**")
        st.write(
            f"Profit **{baseline['profit']:.2f} U** · DD **{baseline['max_dd']:.2f} U** · "
            f"Score **{baseline['score']:.2f}**"
        )
        params = baseline.get("params", baseline)
        st.caption(format_params(params))
    with c2:
        st.markdown(f"**Selezionato (#{rank})**")
        st.write(
            f"Profit **{picked['profit']:.2f} U** · DD **{picked['max_dd']:.2f} U** · "
            f"Score **{picked['score']:.2f}** · Calmar **{picked['calmar']:.2f}**"
        )
        params = picked.get("params", picked)
        st.caption(format_params(params))


def _render_stake_tab(cfg: StrategyConfig, patterns: list[str], df_raw: pd.DataFrame):
    st.markdown("### Ottimizzazione parametri")
    opt_patterns = st.multiselect(
        "Pattern attivi",
        options=patterns,
        default=patterns,
        key=f"{cfg.key}_opt_patterns",
    ) if patterns else []
    iterations = st.slider("Iterazioni", 500, 5000, 2000, 500, key=f"{cfg.key}_opt_iter")
    aggressive = False
    max_dd = -999.0
    dd_weight = 0.6
    use_tier = bool(cfg.system and supports_tier(cfg.system))

    if use_tier:
        c1, c2 = st.columns(2)
        dd_weight = c1.slider(
            "Penalità DD nello score", 0.2, 1.2, 0.6, 0.05,
            key=f"{cfg.key}_opt_dd_weight",
        )
        max_dd = c2.number_input(
            "Filtro DD minimo (U)", value=-999.0, step=1.0, key=f"{cfg.key}_opt_dd",
        )
        st.caption(
            f"Stake attuali: **{format_stakes_summary(cfg.key, cfg.system)}** · "
            "ottimizzazione su backtest **tier** (T1/T2/T3/T4)."
        )
    elif cfg.key in ("sh0", "sh1", "sh2"):
        dd_default = -18.0
        max_dd = st.number_input("Filtro DD minimo", value=dd_default, step=1.0, key=f"{cfg.key}_opt_dd")
    elif cfg.key == "o15":
        aggressive = st.checkbox("Modalità aggressiva", key=f"{cfg.key}_opt_agg")
        max_dd = st.number_input("Filtro DD minimo", value=-999.0, step=1.0, key=f"{cfg.key}_opt_dd")

    if st.button(f"⚙️ {cfg.stake_label}", type="primary", key=f"{cfg.key}_run_opt"):
        with st.spinner(f"Test {iterations} configurazioni..."):
            pat = tuple(opt_patterns) if opt_patterns else None
            dd_limit = None if max_dd <= -900 else max_dd
            if use_tier:
                from core.tier_stake_optimizer import format_stake_combo, optimize_tier_stakes

                rules = active_tier_rules(cfg.key, cfg.system)
                baseline, results = optimize_tier_stakes(
                    df_raw, cfg.system, rules,
                    patterns=pat,
                    dd_weight=dd_weight,
                    max_dd_limit=dd_limit,
                    include_random=True,
                    random_iterations=iterations,
                )
                st.session_state[f"{cfg.key}_opt_format"] = "tier"
            elif cfg.key == "combined":
                baseline, results = cfg.optimize_stake(cfg.df_grouped, df_raw, iterations=iterations)
                st.session_state[f"{cfg.key}_opt_format"] = "legacy"
            elif cfg.key == "o15":
                baseline, results = cfg.optimize_stake(
                    df_raw, patterns=pat, iterations=iterations,
                    aggressive=aggressive, max_dd_limit=dd_limit,
                )
                st.session_state[f"{cfg.key}_opt_format"] = "legacy"
            elif cfg.key in ("sh0", "sh1", "sh2"):
                baseline, results = cfg.optimize_stake(
                    df_raw, patterns=pat, iterations=iterations, max_dd_limit=dd_limit,
                )
                st.session_state[f"{cfg.key}_opt_format"] = "legacy"
            else:
                baseline, results = cfg.optimize_stake(df_raw, patterns=pat, iterations=iterations)
                st.session_state[f"{cfg.key}_opt_format"] = "legacy"
            st.session_state[f"{cfg.key}_opt_baseline"] = baseline
            st.session_state[f"{cfg.key}_opt_results"] = results
            if results is not None and not results.empty:
                best = results.iloc[0]
                st.success(
                    f"✅ **{len(results)}** configurazioni testate. "
                    f"Migliore per score: profit **{best['profit']:.1f}U** · DD **{best['max_dd']:.1f}U**"
                )
            elif results is not None and results.empty:
                st.warning("Nessun risultato con i filtri impostati.")

    baseline = st.session_state.get(f"{cfg.key}_opt_baseline")
    results = st.session_state.get(f"{cfg.key}_opt_results")
    opt_format = st.session_state.get(f"{cfg.key}_opt_format", "legacy")
    if use_tier:
        from core.tier_stake_optimizer import format_stake_combo
        format_fn = format_stake_combo
    else:
        format_fn = cfg.format_params

    if baseline and results is not None and not results.empty:
        show = results.copy()
        show["winrate_pct"] = (show["winrate"] * 100).round(1)
        if opt_format == "tier":
            show["params_str"] = show.apply(format_stake_combo, axis=1)
        else:
            show["params_str"] = show["params"].apply(cfg.format_params)

        sort_by = st.selectbox(
            "Ordina per",
            ["score", "profit", "max_dd", "calmar", "winrate", "trades"],
            key=f"{cfg.key}_opt_sort",
        )

        st.markdown("#### 🔎 Filtri risultati")
        f1, f2, f3, f4 = st.columns(4)
        search = f1.text_input(
            "Cerca nei parametri",
            placeholder="es. T1=3.0",
            key=f"{cfg.key}_opt_search",
        )
        min_trades = f2.number_input(
            "Trade min.",
            min_value=0,
            value=0,
            step=10,
            key=f"{cfg.key}_opt_min_trades",
        )
        min_profit = f3.number_input(
            "Profit min. (U)",
            value=-999.0,
            step=5.0,
            key=f"{cfg.key}_opt_min_profit",
        )
        min_max_dd = f4.number_input(
            "DD min. (U)",
            value=-999.0,
            step=1.0,
            key=f"{cfg.key}_opt_min_dd",
            help="Es. -15 → esclude DD peggiori di -15 U.",
        )

        g1, g2 = st.columns(2)
        min_winrate = g1.number_input(
            "Winrate min. (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            key=f"{cfg.key}_opt_min_wr",
        )
        min_calmar = g2.number_input(
            "Calmar min.",
            min_value=0.0,
            value=0.0,
            step=0.5,
            key=f"{cfg.key}_opt_min_calmar",
        )

        ascending = sort_by == "max_dd"
        view = _apply_opt_filters(
            show,
            search=search,
            **_metric_threshold_kwargs(min_profit, min_max_dd, min_trades, min_winrate, min_calmar),
        )
        view = view.sort_values(
            [sort_by, "profit"],
            ascending=[ascending, False],
        ).reset_index(drop=True)
        view["#"] = range(1, len(view) + 1)

        table_cols = ["#", "profit", "max_dd", "score", "calmar", "trades", "winrate_pct", "params_str"]
        st.caption(f"**{len(view):,}** configurazioni mostrate su **{len(show):,}** totali")

        if view.empty:
            st.warning("Nessun risultato con i filtri selezionati. Allarga i filtri o resetta i valori.")
            return

        render_metric_table(view[table_cols], OPT_STAKE_COLUMNS, seed_col="params_str")

        default_rank = int(st.session_state.get(f"{cfg.key}_opt_pick_rank", 1))
        default_rank = max(1, min(default_rank, len(view)))
        sel_rank = st.number_input(
            "Seleziona risultato (#)",
            min_value=1,
            max_value=len(view),
            value=default_rank,
            step=1,
            key=f"{cfg.key}_opt_pick_rank",
            help="Numero Rank dalla tabella sopra.",
        )
        picked = view.iloc[int(sel_rank) - 1]
        _render_opt_pick_comparison(baseline, picked, int(sel_rank), format_fn)

        if use_tier and st.button(
            "✅ Applica stake selezionate",
            type="primary",
            key=f"{cfg.key}_apply_opt_stakes",
        ):
            apply_stake_rules(cfg.key, cfg.system, picked.to_dict())
            st.success(
                f"Stake applicate: **{format_stake_combo(picked)}**. "
                "Opzionale: ricalcola **Combinazioni pattern**."
            )

        st.download_button(
            "📥 Scarica CSV ottimizzazione",
            results.to_csv(index=False).encode("utf-8"),
            file_name=f"{cfg.key}_optimization.csv",
            mime="text/csv",
            key=f"{cfg.key}_dl_opt",
        )
    elif results is not None and results.empty:
        st.warning("Nessun risultato con i filtri impostati.")
    else:
        st.info(f"Clicca **{cfg.stake_label}** per avviare la ricerca.")


@st.fragment
def _render_stake_tab_fragment(cfg: StrategyConfig, patterns: list[str], df_raw: pd.DataFrame):
    """Fragment: click su Ottimizza stake non resetta la tab attiva."""
    try:
        _render_stake_tab(cfg, patterns, df_raw)
    except Exception as exc:
        st.error(f"Errore ottimizzazione stake: {exc}")


def show_strategy_tab(cfg: StrategyConfig):
    hydrate_session(cfg.key, st.session_state)

    st.markdown(STRATEGY_CSS, unsafe_allow_html=True)
    st.markdown(f"### {cfg.title}")
    st.caption(cfg.data_hint)

    df_raw = cfg.df_raw if cfg.df_raw is not None else pd.DataFrame()
    if df_raw.empty and cfg.key != "combined":
        st.warning(f"Nessun dato per {cfg.title}. Carica file Excel in `data/`.")
        return
    if cfg.key == "combined" and df_raw.empty:
        st.warning("Nessun dato Combined. Carica file in `data/ht`, `data/over15`, `data/over25`.")
        return

    if cfg.system:
        patterns = list_available_patterns(df_raw, cfg.system)
        sub = df_raw[df_raw["system"] == cfg.system]
        st.caption(
            f"{len(sub):,} righe · {sub['match_id'].nunique():,} partite · "
            f"Pattern: {', '.join(patterns) if patterns else '—'}"
        )
    else:
        patterns = []
        for sys in ("HT", "O15", "O25"):
            p = list_available_patterns(df_raw, sys)
            if p:
                patterns.extend([f"{sys}:{x}" for x in p])
        st.caption(f"Dati combinati HT + O15 + O25 · {len(df_raw):,} righe totali")

    if supports_tier(cfg.system):
        show_tier_workflow_guide(cfg.key, cfg.system)

    section = render_strategy_nav(cfg.key, with_tier=bool(cfg.system and supports_tier(cfg.system)))

    pat_list_for_combos: list[str] = []
    if cfg.system:
        pat_list_for_combos = list_available_patterns(df_raw, cfg.system)
    elif cfg.key != "combined":
        pat_list_for_combos = patterns

    combo_df_cached = _cached_combo_results(cfg.key)

    if section == "bt":
        if _combo_is_outdated(cfg):
            st.warning(
                "⚠️ Tier o stake cambiati dopo l'ultimo calcolo combinazioni. "
                "I numeri sotto possono essere datati — vai su **Combinazioni pattern** e ricalcola."
            )
        if pat_list_for_combos and not combo_df_cached.empty:
            _render_combo_size_overview(combo_df_cached, pat_list_for_combos, cfg, df_raw)
        elif pat_list_for_combos:
            st.caption(
                "Apri **Combinazioni pattern** e clicca **Calcola tutte le combinazioni** "
                "per vedere ogni subset (N, N-1, …, 1 file)."
            )

        sel_patterns: list[str] | None = None
        if cfg.system and patterns:
            pat_options = list_available_patterns(df_raw, cfg.system)
            _sync_bt_patterns_widget(cfg.key, pat_options)
            bt_key = bt_patterns_key(cfg.key)
            if bt_key not in st.session_state:
                active = st.session_state.get(active_patterns_key(cfg.key))
                fallback = [p for p in (active or pat_options) if p in pat_options] or pat_options
                st.session_state[bt_key] = fallback
            sel = st.multiselect(
                "Pattern attivi (vuoto = tutti)",
                options=pat_options,
                key=bt_key,
            )
            sel_patterns = list(sel) if sel else None

        c_run, c_apply = st.columns([1, 1])
        with c_run:
            run_bt = st.button(
                "▶️ Esegui backtest",
                type="primary",
                key=f"{cfg.key}_run_bt",
            )
        with c_apply:
            if cfg.system and patterns:
                if st.button("Usa pattern nel riepilogo", key=f"{cfg.key}_bt_apply_summary"):
                    set_active_combo(
                        cfg.key,
                        tuple(sel_patterns) if sel_patterns else None,
                        " + ".join(sel) if sel else "Tutti i pattern",
                    )
                    st.success("Pattern applicati al riepilogo in alto.")

        if run_bt:
            with st.spinner("Backtest in corso..."):
                st.session_state[bt_trades_key(cfg.key)] = _run_strategy_backtest(
                    cfg, df_raw, sel_patterns,
                )

        df_trades = st.session_state.get(bt_trades_key(cfg.key))
        if df_trades is None:
            st.info(
                "**Backtest non ancora eseguito.**\n\n"
                "1. Scegli i pattern (opzionale)\n"
                "2. Clicca **▶️ Esegui backtest**\n"
                "3. Per tutte le combo pattern → tab **🧩 Combinazioni pattern**"
            )
        else:
            if supports_tier(cfg.system):
                show_tier_metodo_panel(
                    cfg.key, cfg.system, cfg.title.split("—")[0].strip(), df_trades, df_raw,
                )
            _render_ccs_backtest(df_trades, cfg.title, cfg.key, section="bt", system=cfg.system)

    elif section == "combo":
        pat_list = list_available_patterns(df_raw, cfg.system) if cfg.system else patterns
        _render_combo_tab_fragment(cfg, pat_list, df_raw)

    elif section == "opt":
        pat_list = list_available_patterns(df_raw, cfg.system) if cfg.system else []
        _render_stake_tab_fragment(cfg, pat_list, df_raw)

    elif section == "tier":
        render_tier_optimizer_fragment(cfg.key, cfg.system, cfg.title.split("—")[0].strip(), df_raw)

    elif section == "stake_sim":
        render_stake_simulator_fragment(cfg.key, cfg.system, cfg.title.split("—")[0].strip(), df_raw)

    elif section == "daily":
        daily_patterns: list[str] = []
        if cfg.system:
            daily_patterns = list_available_patterns(df_raw, cfg.system)
        elif cfg.key == "combined":
            for sys in ("HT", "O15", "O25"):
                for p in list_available_patterns(df_raw, sys):
                    daily_patterns.append(f"{sys}:{p}")
        else:
            daily_patterns = patterns
        render_strategy_daily_tab(
            cfg.key,
            cfg.title.split("—")[0].strip(),
            daily_patterns,
            system=cfg.system,
            initial_bankroll=INITIAL_BANKROLL,
        )
