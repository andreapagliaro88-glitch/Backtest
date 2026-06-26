"""Analisi quote 1X2 vs gol secondo tempo — Sweden Superettan."""
import os

import numpy as np
import pandas as pd

CSV_PATH = os.path.join("data", "footystats", "sweden-superettan.csv")
# Quota media stimata Over 0.5 2° tempo (mercato tipico)
DEFAULT_SH_ODD = 1.28
STAKE = 1.0
GOAL_COL = "sh_goal"
OUTPUT_DIR = "output/footystats"


def load_league(path=CSV_PATH):
    df = pd.read_csv(path, sep=";", low_memory=False)
    df["date"] = pd.to_datetime(df["date_GMT"], format="mixed", errors="coerce")
    df = df[df["status"] == "complete"].copy()

    for col in ("odds_ft_home_team_win", "odds_ft_draw", "odds_ft_away_team_win"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in (
        "home_team_goal_count_half_time",
        "away_team_goal_count_half_time",
        "home_team_goal_count",
        "away_team_goal_count",
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["sh_home"] = df["home_team_goal_count"] - df["home_team_goal_count_half_time"]
    df["sh_away"] = df["away_team_goal_count"] - df["away_team_goal_count_half_time"]
    df[GOAL_COL] = (df["sh_home"] + df["sh_away"]) >= 1

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
    df["spread_fav_dog"] = df["odd_dog"] - df["odd_fav"]

    return df.sort_values("date").reset_index(drop=True)


def profit_sim(wins, n, odd=DEFAULT_SH_ODD, stake=STAKE):
    if n == 0:
        return 0.0, 0.0, 0.0
    winrate = wins / n
    profit = wins * stake * (odd - 1) - (n - wins) * stake
    roi = profit / (n * stake) * 100
    return winrate, profit, roi


def scan_range(df, col, low, high, step=0.05, odd=DEFAULT_SH_ODD, min_n=30):
    rows = []
    edges = np.arange(low, high + step, step)
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        is_last = i == len(edges) - 2
        if is_last:
            mask = (df[col] >= a) & (df[col] <= b)
            label = f"{a:.2f}-{b:.2f}"
        else:
            mask = (df[col] >= a) & (df[col] < b)
            label = f"{a:.2f}-{b:.2f}"
        sub = df[mask]
        n = len(sub)
        if n < min_n:
            continue
        wins = sub[GOAL_COL].sum()
        wr, prof, roi = profit_sim(wins, n, odd)
        rows.append({
            "colonna": col,
            "range": label,
            "min": a,
            "max": b,
            "n": n,
            "winrate": wr,
            "profit_u": prof,
            "roi_pct": roi,
            "break_even_odd": 1 / wr if wr > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def exact_range(df, col, lo, hi, odd=DEFAULT_SH_ODD):
    sub = df[(df[col] >= lo) & (df[col] <= hi)]
    n = len(sub)
    wins = sub[GOAL_COL].sum()
    wr, prof, roi = profit_sim(wins, n, odd)
    return {"colonna": col, "range": f"{lo:.2f}-{hi:.2f}", "n": n, "winrate": wr, "roi_pct": roi}


def scan_2d(df, col_a, col_b, a_range, b_range, step=0.15, min_n=25, odd=DEFAULT_SH_ODD):
    rows = []
    a_edges = np.arange(a_range[0], a_range[1] + step, step)
    b_edges = np.arange(b_range[0], b_range[1] + step, step)
    for i in range(len(a_edges) - 1):
        for j in range(len(b_edges) - 1):
            a0, a1 = a_edges[i], a_edges[i + 1]
            b0, b1 = b_edges[j], b_edges[j + 1]
            is_last_a = i == len(a_edges) - 2
            is_last_b = j == len(b_edges) - 2
            ma = (df[col_a] >= a0) & (df[col_a] <= a1 if is_last_a else df[col_a] < a1)
            mb = (df[col_b] >= b0) & (df[col_b] <= b1 if is_last_b else df[col_b] < b1)
            sub = df[ma & mb]
            n = len(sub)
            if n < min_n:
                continue
            wins = sub[GOAL_COL].sum()
            wr, prof, roi = profit_sim(wins, n, odd)
            rows.append({
                "range_1": f"{a0:.2f}-{a1:.2f}",
                "range_x": f"{b0:.2f}-{b1:.2f}",
                "n": n,
                "winrate": wr,
                "roi_pct": roi,
            })
    return pd.DataFrame(rows)


def main():
    df = load_league()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    base_wr = df[GOAL_COL].mean()
    base_n = len(df)

    print(f"Partite analizzate: {base_n}")
    print(f"Gol 2° tempo (base): {base_wr*100:.1f}%")
    print(f"Quota 2T simulata: {DEFAULT_SH_ODD} (flat stake 1U)\n")

    cols_scan = {
        "odd_1": (1.2, 4.0),
        "odd_x": (2.5, 4.5),
        "odd_2": (1.2, 5.0),
        "odd_fav": (1.2, 2.8),
        "odd_dog": (3.0, 8.0),
        "spread_fav_dog": (1.0, 6.0),
    }

    all_scans = [scan_range(df, col, lo, hi) for col, (lo, hi) in cols_scan.items()]
    results = pd.concat([s for s in all_scans if not s.empty], ignore_index=True)
    results = results.sort_values("roi_pct", ascending=False)
    results.to_csv(f"{OUTPUT_DIR}/superettan_2h_1x2_scan.csv", index=False)

    robust = results[results["n"] >= 80].sort_values("roi_pct", ascending=False)
    worst = results[results["n"] >= 80].sort_values("roi_pct").head(5)
    grid = scan_2d(df, "odd_1", "odd_x", (1.3, 2.8), (2.8, 4.2), min_n=20)
    grid = grid.sort_values("roi_pct", ascending=False)
    grid.to_csv(f"{OUTPUT_DIR}/superettan_2h_grid_1x.csv", index=False)

    print("=== TOP 15 RANGE 1X2 (2° tempo) ===")
    for _, r in results.head(15).iterrows():
        print(
            f"  {r['colonna']:12} {r['range']:12} | n={int(r['n']):4} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}% | "
            f"BE odd {r['break_even_odd']:.3f}"
        )

    print("\n=== TOP 10 ROBUSTI (n >= 80) ===")
    for _, r in robust.head(10).iterrows():
        print(
            f"  {r['colonna']:12} {r['range']:12} | n={int(r['n']):4} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}%"
        )

    print("\n=== TOP 10 COMBO 1 + X ===")
    for _, r in grid.head(10).iterrows():
        print(
            f"  1: {r['range_1']:12} X: {r['range_x']:12} | n={int(r['n']):3} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}%"
        )

    print("\n=== DA EVITARE (n >= 80) ===")
    for _, r in worst.iterrows():
        print(
            f"  {r['colonna']:12} {r['range']:12} | n={int(r['n']):4} | "
            f"WR {r['winrate']*100:.1f}% | ROI {r['roi_pct']:+.1f}%"
        )

    with pd.ExcelWriter(f"{OUTPUT_DIR}/superettan_analisi_2h.xlsx", engine="openpyxl") as writer:
        pd.DataFrame([{
            "Campionato": "Sweden Superettan",
            "Partite": base_n,
            "Gol 2T %": round(base_wr * 100, 2),
            "Quota 2T simulata": DEFAULT_SH_ODD,
        }]).to_excel(writer, sheet_name="Info", index=False)
        results.head(50).to_excel(writer, sheet_name="Top range", index=False)
        robust.head(30).to_excel(writer, sheet_name="Range robusti", index=False)
        grid.head(30).to_excel(writer, sheet_name="Combo 1+X", index=False)
        results[results["roi_pct"] > 0].to_excel(writer, sheet_name="Profittevoli", index=False)

    print(f"\nSalvato: {OUTPUT_DIR}/superettan_analisi_2h.xlsx")


if __name__ == "__main__":
    main()
