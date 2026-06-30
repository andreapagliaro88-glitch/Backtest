"""Simulazione Monte Carlo per Controlled Compounding System."""
from __future__ import annotations

import random
from typing import Any

import numpy as np

from core.controlled_compounding import ControlledCompounding


def run_ccs_monte_carlo(
    trades: list[dict[str, Any]],
    initial_bankroll: float = 150.0,
    n_simulations: int = 1000,
    seed: int | None = 42,
    ruin_bankroll: float = 0.0,
) -> dict[str, Any]:
    """
    Rimescola l'ordine dei trade mantenendo win/loss e odds invariati.
    trades: [{vinto, profit_odds, system?, date?}, ...]
    """
    if not trades:
        return {"n_simulations": 0, "message": "Nessun trade"}

    rng = random.Random(seed)
    finals: list[float] = []
    profits: list[float] = []
    max_dds: list[float] = []
    ruined = 0

    for _ in range(n_simulations):
        order = trades.copy()
        rng.shuffle(order)
        ccs = ControlledCompounding(initial_bankroll)
        hit_ruin = False

        for t in order:
            if t.get("skipped"):
                continue
            profit = ccs.settle_trade(
                vinto=bool(t["vinto"]),
                profit_odds=float(t["profit_odds"]),
                date=t.get("date"),
                system=t.get("system", ""),
                stake_u=float(t.get("stake_u") or 1.0),
            )
            if ccs.bankroll <= ruin_bankroll or not ccs.can_bet():
                if ccs.bankroll < ccs.current_unit_eur:
                    hit_ruin = True
                    break

        s = ccs.summary()
        finals.append(s["final_bankroll"] + s["total_withdrawn"])
        profits.append(s["total_profit_eur"])
        max_dds.append(s["max_dd_eur"])
        if hit_ruin:
            ruined += 1

    finals_arr = np.array(finals)
    profits_arr = np.array(profits)
    dds_arr = np.array(max_dds)

    return {
        "n_simulations": n_simulations,
        "n_trades": len(trades),
        "ruin_probability": round(ruined / n_simulations, 4),
        "final_bankroll_mean": round(float(finals_arr.mean()), 2),
        "final_bankroll_median": round(float(np.median(finals_arr)), 2),
        "final_bankroll_p5": round(float(np.percentile(finals_arr, 5)), 2),
        "final_bankroll_p95": round(float(np.percentile(finals_arr, 95)), 2),
        "profit_mean": round(float(profits_arr.mean()), 2),
        "profit_median": round(float(np.median(profits_arr)), 2),
        "profit_p5": round(float(np.percentile(profits_arr, 5)), 2),
        "profit_p95": round(float(np.percentile(profits_arr, 95)), 2),
        "max_dd_mean": round(float(dds_arr.mean()), 2),
        "max_dd_median": round(float(np.median(dds_arr)), 2),
        "max_dd_p5": round(float(np.percentile(dds_arr, 5)), 2),
        "max_dd_p95": round(float(np.percentile(dds_arr, 95)), 2),
        "distribution_final": finals_arr,
        "distribution_profit": profits_arr,
        "distribution_max_dd": dds_arr,
    }
