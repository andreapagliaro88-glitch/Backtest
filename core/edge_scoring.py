"""Metriche avanzate e Edge Score composito per pattern discovery."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

MC_SIMULATIONS = 1000


def kelly_fraction(p: float, odd: float) -> float:
    if odd <= 1.01 or p <= 0:
        return 0.0
    k = (p * odd - 1) / (odd - 1)
    return float(max(0.0, min(1.0, k)))


def profit_factor(profits: np.ndarray) -> float:
    wins = profits[profits > 0].sum()
    losses = abs(profits[profits < 0].sum())
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def sharpe_ratio(profits: np.ndarray) -> float:
    if len(profits) < 2:
        return 0.0
    std = float(np.std(profits, ddof=1))
    if std <= 1e-9:
        return 0.0
    return float(np.mean(profits) / std * np.sqrt(len(profits)))


def expectancy_per_trade(profits: np.ndarray) -> float:
    return float(np.mean(profits)) if len(profits) else 0.0


def winning_streak_stats(wins: np.ndarray) -> dict[str, Any]:
    streaks: list[int] = []
    cur = 0
    for w in wins:
        if w:
            cur += 1
        elif cur:
            streaks.append(cur)
            cur = 0
    if cur:
        streaks.append(cur)
    if not streaks:
        return {"max": 0, "avg": 0.0}
    return {"max": int(max(streaks)), "avg": float(np.mean(streaks))}


def seasonal_stability(trades: pd.DataFrame) -> float:
    if trades.empty or "season" not in trades.columns:
        return 0.0
    by_s = trades.groupby("season")["profit_u"].sum()
    return float((by_s > 0).mean()) if len(by_s) else 0.0


def average_drawdown(profits: np.ndarray) -> float:
    if len(profits) == 0:
        return 0.0
    eq = np.cumsum(profits)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return float(dd[dd < 0].mean()) if (dd < 0).any() else 0.0


def explain_edge_statistically(pattern: dict[str, Any]) -> str:
    """Spiegazione in italiano del perché l'edge è statisticamente plausibile."""
    parts = [
        f"Il mercato **{pattern.get('market_label', '')}** nel segmento filtrato "
        f"vincente nel **{pattern.get('winrate', 0) * 100:.1f}%** dei casi "
        f"({int(pattern.get('n', 0))} partite).",
    ]
    wr = pattern.get("winrate", 0)
    odd = pattern.get("avg_odd", 2.0)
    be = 100 / odd if odd > 1 else 50
    parts.append(
        f"Win rate superiore al break-even implicito (**{be:.1f}%** a quota media **{odd:.2f}**)."
    )
    ci_lo = pattern.get("ci_low", 0) * 100
    ci_hi = pattern.get("ci_high", 0) * 100
    parts.append(f"Intervallo di confidenza 95%: **[{ci_lo:.1f}%, {ci_hi:.1f}%]**.")
    if pattern.get("oos_pass"):
        parts.append(
            f"Confermato out-of-sample: ROI **{pattern.get('oos_roi_pct', 0):.1f}%** "
            f"su {int(pattern.get('oos_n', 0))} partite successive."
        )
    ms = pattern.get("monthly_stability", 0) * 100
    parts.append(f"Stabilità mensile: **{ms:.0f}%** dei mesi in profitto.")
    desc = pattern.get("description", "")
    if desc:
        parts.append(f"Condizioni: {desc}.")
    if pattern.get("market", "").startswith("live_") or "Live" in pattern.get("market_label", ""):
        parts.append(
            "Edge live: lo stato partita al minuto di ingresso seleziona scenari "
            "con valore atteso residuo misurabile sul campionato."
        )
    elif any(k in desc for k in ("xg_", "pre_over", "ppg_", "pre_btts")):
        parts.append(
            "Il filtro pre-match isola partite con profilo offensivo/difensivo "
            "coerente con la frequenza storica dell'outcome."
        )
    elif "odd_" in desc:
        parts.append(
            "Il range di quote individuato dal grid search adattivo segnala "
            "un pricing inefficiency ricorrente del book su questo campionato."
        )
    parts.append(f"p-value **{pattern.get('p_value', 1):.4f}** (significatività statistica).")
    return " ".join(parts)


def losing_streak_stats(wins: np.ndarray) -> dict[str, Any]:
    streaks: list[int] = []
    cur = 0
    for w in wins:
        if not w:
            cur += 1
        elif cur:
            streaks.append(cur)
            cur = 0
    if cur:
        streaks.append(cur)
    if not streaks:
        return {"max": 0, "distribution": {}, "avg": 0.0}

    dist: dict[int, int] = {}
    for s in streaks:
        dist[s] = dist.get(s, 0) + 1
    return {
        "max": int(max(streaks)),
        "distribution": dist,
        "avg": float(np.mean(streaks)),
    }


def monte_carlo_analysis(profits: np.ndarray, n_sim: int = MC_SIMULATIONS) -> dict[str, float]:
    if len(profits) == 0:
        return {
            "mc_median_roi": 0.0,
            "mc_p5_roi": 0.0,
            "mc_p95_roi": 0.0,
            "mc_prob_profit": 0.0,
        }
    rng = np.random.default_rng(42)
    n = len(profits)
    final_rois = np.empty(n_sim)
    for i in range(n_sim):
        sample = profits[rng.integers(0, n, size=n)]
        final_rois[i] = 100.0 * sample.sum() / n
    return {
        "mc_median_roi": float(np.median(final_rois)),
        "mc_p5_roi": float(np.percentile(final_rois, 5)),
        "mc_p95_roi": float(np.percentile(final_rois, 95)),
        "mc_prob_profit": float((final_rois > 0).mean()),
    }


def _roi_pct(profits: np.ndarray) -> float:
    if len(profits) == 0:
        return 0.0
    return float(100.0 * profits.sum() / len(profits))


def roi_by_season(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty or "season" not in trades.columns:
        return {}
    out = {}
    for season, grp in trades.groupby("season"):
        out[str(season)] = round(_roi_pct(grp["profit_u"].values), 2)
    return out


def roi_home_away(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {"casa": 0.0, "trasferta": 0.0}
    casa = trades[trades["is_home_fav"]]
    trasferta = trades[~trades["is_home_fav"]]
    return {
        "casa": round(_roi_pct(casa["profit_u"].values), 2) if len(casa) else 0.0,
        "trasferta": round(_roi_pct(trasferta["profit_u"].values), 2) if len(trasferta) else 0.0,
    }


def monthly_heatmap(trades: pd.DataFrame) -> dict[str, dict[str, float]]:
    if trades.empty:
        return {}
    tmp = trades.copy()
    tmp["year"] = tmp["date"].dt.year.astype(str)
    tmp["mon"] = tmp["date"].dt.month
    out: dict[str, dict[str, float]] = {}
    for year, grp in tmp.groupby("year"):
        by_m = grp.groupby("mon")["profit_u"].sum()
        out[year] = {str(int(m)): round(float(v), 2) for m, v in by_m.items()}
    return out


def equity_curve(trades: pd.DataFrame) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    eq = trades["profit_u"].cumsum()
    return [
        {"date": d.strftime("%Y-%m-%d"), "equity": round(float(e), 3)}
        for d, e in zip(trades["date"], eq)
    ]


def profitable_months_count(trades: pd.DataFrame) -> int:
    if trades.empty or "month" not in trades.columns:
        return 0
    by_m = trades.groupby("month")["profit_u"].sum()
    return int((by_m > 0).sum())


def robustness_score(
    n: int,
    p_value: float,
    monthly_stability: float,
    oos_pass: bool,
    oos_roi_pct: float,
    roi_pct: float,
    ci_low: float,
    avg_odd: float,
) -> float:
    score = 0.0
    if oos_pass:
        score += 25.0
    score += min(monthly_stability, 1.0) * 25.0
    score += min(n / 200.0, 1.0) * 20.0
    if p_value <= 0.05:
        score += (1.0 - p_value / 0.05) * 15.0
    gap = abs(roi_pct - oos_roi_pct)
    score += max(0.0, 15.0 - gap * 0.6)
    breakeven = 1.0 / avg_odd if avg_odd > 1.01 else 0.5
    if ci_low > breakeven:
        score += 10.0
    elif ci_low > breakeven - 0.05:
        score += 5.0
    return float(min(100.0, max(0.0, score)))


def _norm(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return float(min(100.0, max(0.0, 100.0 * value / cap)))


def composite_edge_score(
    robustness: float,
    roi_pct: float,
    profit_u: float,
    oos_roi_pct: float,
    p_value: float,
    max_dd_u: float,
) -> float:
    norm_roi = _norm(max(roi_pct, 0), 30.0)
    norm_profit = _norm(max(profit_u, 0), 50.0)
    norm_oos = _norm(max(oos_roi_pct, 0), 25.0)
    norm_p = min(100.0, max(0.0, (1.0 - p_value / 0.05) * 100.0))
    dd_score = min(100.0, max(0.0, 100.0 + max_dd_u * 5.0))

    return float(
        0.30 * robustness
        + 0.20 * norm_roi
        + 0.20 * norm_profit
        + 0.15 * norm_oos
        + 0.10 * norm_p
        + 0.05 * dd_score
    )


def analyze_trade_series(trades: pd.DataFrame, pattern: dict[str, Any]) -> dict[str, Any]:
    profits = trades["profit_u"].values.astype(float)
    wins = trades["win"].values.astype(bool)

    streak = losing_streak_stats(wins)
    mc = monte_carlo_analysis(profits)
    pf = profit_factor(profits)
    sharpe = sharpe_ratio(profits)
    exp = expectancy_per_trade(profits)
    kelly = kelly_fraction(float(wins.mean()), float(pattern.get("avg_odd", 2.0)))

    win_streak = winning_streak_stats(wins)
    robust = robustness_score(
        n=int(pattern["n"]),
        p_value=float(pattern["p_value"]),
        monthly_stability=float(pattern["monthly_stability"]),
        oos_pass=bool(pattern["oos_pass"]),
        oos_roi_pct=float(pattern["oos_roi_pct"]),
        roi_pct=float(pattern["roi_pct"]),
        ci_low=float(pattern["ci_low"]),
        avg_odd=float(pattern.get("avg_odd", 2.0)),
    )
    edge = composite_edge_score(
        robustness=robust,
        roi_pct=float(pattern["roi_pct"]),
        profit_u=float(pattern["profit_u"]),
        oos_roi_pct=float(pattern["oos_roi_pct"]),
        p_value=float(pattern["p_value"]),
        max_dd_u=float(pattern["max_dd_u"]),
    )

    return {
        "robustness_score": round(robust, 1),
        "edge_score": round(edge, 1),
        "sharpe_ratio": round(sharpe, 3),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else 99.9,
        "expectancy_u": round(exp, 4),
        "kelly_pct": round(kelly * 100, 2),
        "profitable_months": profitable_months_count(trades),
        "total_months": int(trades["month"].nunique()) if "month" in trades.columns else 0,
        "max_losing_streak": streak["max"],
        "avg_losing_streak": round(streak["avg"], 2),
        "max_winning_streak": win_streak["max"],
        "avg_drawdown_u": round(average_drawdown(profits), 3),
        "seasonal_stability": round(seasonal_stability(trades) * 100, 1),
        "yield_pct": round(float(pattern.get("roi_pct", 0)), 2),
        "edge_explanation": explain_edge_statistically(pattern),
        "losing_streak_dist": streak["distribution"],
        "mc_median_roi": round(mc["mc_median_roi"], 2),
        "mc_p5_roi": round(mc["mc_p5_roi"], 2),
        "mc_p95_roi": round(mc["mc_p95_roi"], 2),
        "mc_prob_profit": round(mc["mc_prob_profit"] * 100, 1),
        "roi_by_season": roi_by_season(trades),
        "roi_home_away": roi_home_away(trades),
        "monthly_heatmap": monthly_heatmap(trades),
        "equity_curve": equity_curve(trades),
    }


def serialize_analytics(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("losing_streak_dist", "roi_by_season", "roi_home_away", "monthly_heatmap", "equity_curve", "odds_examples"):
        if key in out and not isinstance(out[key], str):
            out[key] = json.dumps(out[key], ensure_ascii=False)
    return out
