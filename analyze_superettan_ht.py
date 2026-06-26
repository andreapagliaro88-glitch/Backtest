"""Analisi quote 1X2 vs gol primo tempo — Sweden Superettan."""
import os
import pandas as pd
import numpy as np

CSV_PATH = os.path.join("data", "footystats", "sweden-superettan.csv")
# Quota media stimata Over 0.5 HT (mercato tipico); usata per simulare profitto
DEFAULT_HT_ODD = 1.38
STAKE = 1.0


def load_league(path=CSV_PATH):
    df = pd.read_csv(path, sep=";", low_memory=False)
    df["date"] = pd.to_datetime(df["date_GMT"], errors="coerce")
    df = df[df["status"] == "complete"].copy()

    for col in ("odds_ft_home_team_win", "odds_ft_draw", "odds_ft_away_team_win"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["ht_home"] = pd.to_numeric(df["home_team_goal_count_half_time"], errors="coerce").fillna(0)
    df["ht_away"] = pd.to_numeric(df["away_team_goal_count_half_time"], errors="coerce").fillna(0)
    df["fh_goal"] = (df["ht_home"] + df["ht_away"]) >= 1

    df = df[
        (df["odds_ft_home_team_win"] > 1.01)
        & (df["odds_ft_draw"] > 1.01)
        & (df["odds_ft_away_team_win"] > 1.01)
    ].copy()

    df["odd_1"] = df["odds_ft_home_team_win"]
    df["odd_x"] = df["odds_ft_draw"]
    df["odd_2"] = df["odds_ft_away_team_win"]
    df["odd_fav"] = df[["odd_1", "odd_x", "odd_2"]].min(axis=1)
    df["odd_dog"] = df[["odd_1", "odd_x", "odd_2"]].max(axis=1)
    df["odd_mid"] = df[["odd_1", "odd_x", "odd_2"]].apply(
        lambda r: sorted(r)[1], axis=1
    )
    df["spread_fav_dog"] = df["odd_dog"] - df["odd_fav"]

    return df.sort_values("date").reset_index(drop=True)


def profit_sim(wins, n, ht_odd=DEFAULT_HT_ODD, stake=STAKE):
    if n == 0:
        return 0.0, 0.0, 0.0
    winrate = wins / n
    profit = wins * stake * (ht_odd - 1) - (n - wins) * stake
    roi = profit / (n * stake) * 100
    return winrate, profit, roi


def scan_range(df, col, low, high, step=0.05, ht_odd=DEFAULT_HT_ODD, inclusive_high=True):
    rows = []
    edges = np.arange(low, high + step, step)
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        is_last = i == len(edges) - 2
        if is_last and inclusive_high:
            mask = (df[col] >= a) & (df[col] <= b)
            label = f"{a:.2f}-{b:.2f}"
        else:
            mask = (df[col] >= a) & (df[col] < b)
            label = f"{a:.2f}-{b:.2f}"
        sub = df[mask]
        n = len(sub)
        if n < 30:
            continue
        wins = sub["fh_goal"].sum()
        wr, prof, roi = profit_sim(wins, n, ht_odd)
        rows.append({
            "colonna": col,
            "range": label,
            "inclusivo": is_last and inclusive_high,
            "min": a,
            "max": b,
            "n": n,
            "winrate": wr,
            "profit_u": prof,
            "roi_pct": roi,
            "break_even_odd": 1 / wr if wr > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def exact_range(df, col, lo, hi, ht_odd=DEFAULT_HT_ODD):
    """Range inclusivo su entrambi i lati (come altre app)."""
    sub = df[(df[col] >= lo) & (df[col] <= hi)]
    n = len(sub)
    wins = sub["fh_goal"].sum()
    wr, prof, roi = profit_sim(wins, n, ht_odd)
    return {
        "colonna": col,
        "range": f"{lo:.2f}-{hi:.2f} (inclusivo)",
        "n": n,
        "winrate": wr,
        "profit_u": prof,
        "roi_pct": roi,
        "break_even_odd": 1 / wr if wr > 0 else np.nan,
    }


def scan_2d(df, col_a, col_b, a_range, b_range, step=0.1, min_n=25, ht_odd=DEFAULT_HT_ODD):
    rows = []
    a_edges = np.arange(a_range[0], a_range[1] + step, step)
    b_edges = np.arange(b_range[0], b_range[1] + step, step)
    for i in range(len(a_edges) - 1):
        for j in range(len(b_edges) - 1):
            a0, a1 = a_edges[i], a_edges[i + 1]
            b0, b1 = b_edges[j], b_edges[j + 1]
            mask = (
                (df[col_a] >= a0) & (df[col_a] < a1)
                & (df[col_b] >= b0) & (df[col_b] < b1)
            )
            sub = df[mask]
            n = len(sub)
            if n < min_n:
                continue
            wins = sub["fh_goal"].sum()
            wr, prof, roi = profit_sim(wins, n, ht_odd)
            rows.append({
                "range_1": f"{a0:.2f}-{a1:.2f}",
                "range_x": f"{b0:.2f}-{b1:.2f}",
                "n": n,
                "winrate": wr,
                "profit_u": prof,
                "roi_pct": roi,
            })
    return pd.DataFrame(rows)


def main():
    df = load_league()
    os.makedirs("output/footystats", exist_ok=True)

    base_wr = df["fh_goal"].mean()
    base_n = len(df)
    print(f"Partite analizzate: {base_n}")
    print(f"Gol 1° tempo (base): {base_wr*100:.1f}%")
    print(f"Quota HT simulata: {DEFAULT_HT_ODD} (flat stake 1U)\n")

    check = exact_range(df, "odd_1", 2.35, 2.40)
    print("=== VERIFICA RANGE ALTRO APP ===")
    print(
        f"  Quota 1 tra {check['range']}: n={check['n']} | "
        f"WR {check['winrate']*100:.1f}% | ROI {check['roi_pct']:+.1f}%"
    )
    print("  (filtro: odds_ft_home_team_win >= 2.35 AND <= 2.40)\n")

    cols_scan = {
        "odd_1": (1.2, 4.0),
        "odd_x": (2.5, 4.5),
        "odd_2": (1.2, 5.0),
        "odd_fav": (1.2, 2.5),
        "odd_dog": (3.0, 8.0),
        "spread_fav_dog": (1.0, 6.0),
    }

    all_scans = []
    for col, (lo, hi) in cols_scan.items():
        scan = scan_range(df, col, lo, hi, step=0.05)
        if not scan.empty:
            all_scans.append(scan)

    results = pd.concat(all_scans, ignore_index=True)
    results = results.sort_values("roi_pct", ascending=False)
    results.to_csv("output/footystats/superettan_1x2_scan.csv", index=False)

    top = results.head(15)
    print("=== TOP 15 RANGE 1X2 (per ROI simulato) ===")
    for _, r in top.iterrows():
        print(
            f"  {r['colonna']:12} {r['range']:12} | n={int(r['n']):4} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}% | "
            f"BE odd {r['break_even_odd']:.3f}"
        )

    grid = scan_2d(df, "odd_1", "odd_x", (1.3, 2.8), (2.8, 4.2), step=0.15, min_n=20)
    grid = grid.sort_values("roi_pct", ascending=False)
    grid.to_csv("output/footystats/superettan_1x2_grid_1x.csv", index=False)

    print("\n=== TOP 10 COMBO QUOTA 1 + QUOTA X ===")
    for _, r in grid.head(10).iterrows():
        print(
            f"  1: {r['range_1']:12} X: {r['range_x']:12} | n={int(r['n']):3} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}%"
        )

    profitable = results[results["roi_pct"] > 0].copy()
    robust = results[results["n"] >= 80].sort_values("roi_pct", ascending=False)
    profitable.to_csv("output/footystats/superettan_1x2_profitable.csv", index=False)
    robust.to_csv("output/footystats/superettan_1x2_robust.csv", index=False)

    print("\n=== TOP 10 RANGE ROBUSTI (n >= 80) ===")
    for _, r in robust.head(10).iterrows():
        print(
            f"  {r['colonna']:12} {r['range']:12} | n={int(r['n']):4} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}% | "
            f"BE odd {r['break_even_odd']:.3f}"
        )

    worst = results[results["n"] >= 80].sort_values("roi_pct").head(5)
    print("\n=== RANGE DA EVITARE (n >= 80, ROI peggiore) ===")
    for _, r in worst.iterrows():
        print(
            f"  {r['colonna']:12} {r['range']:12} | n={int(r['n']):4} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}%"
        )

    best = results.iloc[0] if not results.empty else None
    summary = {
        "partite": base_n,
        "fh_goal_rate": round(base_wr, 4),
        "ht_odd_assumed": DEFAULT_HT_ODD,
        "best_single_range": f"{best['colonna']} {best['range']}" if best is not None else "",
        "best_roi": round(best["roi_pct"], 2) if best is not None else 0,
        "best_winrate": round(best["winrate"], 4) if best is not None else 0,
        "best_n": int(best["n"]) if best is not None else 0,
        "profitable_ranges": len(profitable),
    }
    pd.DataFrame([summary]).to_csv("output/footystats/superettan_summary.csv", index=False)

    with pd.ExcelWriter("output/footystats/superettan_analisi_ht.xlsx", engine="openpyxl") as writer:
        pd.DataFrame([{
            "Campionato": "Sweden Superettan",
            "Partite": base_n,
            "Gol 1T %": round(base_wr * 100, 2),
            "Quota HT simulata": DEFAULT_HT_ODD,
            "Stake": STAKE,
        }]).to_excel(writer, sheet_name="Info", index=False)
        results.head(50).to_excel(writer, sheet_name="Top range singoli", index=False)
        robust.head(30).to_excel(writer, sheet_name="Range robusti", index=False)
        grid.head(30).to_excel(writer, sheet_name="Combo 1+X", index=False)
        profitable.to_excel(writer, sheet_name="Tutti profittevoli", index=False)

    print("\nSalvato: output/footystats/superettan_analisi_ht.xlsx")
    return df, results, grid, summary


if __name__ == "__main__":
    main()
