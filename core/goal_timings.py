"""Parsing minuti gol FootyStats e derivazione mercati temporali."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

_MINUTE_RE = re.compile(r"(\d+)")


def parse_goal_timings(raw: Any) -> list[int]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    s = str(raw).strip()
    if not s or s.upper() == "N/A":
        return []
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part or part == "-1":
            continue
        m = _MINUTE_RE.search(part)
        if m:
            minute = int(m.group(1))
            if 0 <= minute <= 120:
                out.append(minute)
    return sorted(out)


def goals_by_period(home_raw: Any, away_raw: Any) -> dict[str, Any]:
    home_m = parse_goal_timings(home_raw)
    away_m = parse_goal_timings(away_raw)
    all_goals = sorted([(m, "H") for m in home_m] + [(m, "A") for m in away_m], key=lambda x: x[0])

    fh_h = sum(1 for m in home_m if m <= 45)
    fh_a = sum(1 for m in away_m if m <= 45)
    sh_h = len(home_m) - fh_h
    sh_a = len(away_m) - fh_a
    total = len(home_m) + len(away_m)

    first_team = None
    first_min = None
    if all_goals:
        first_min, first_team = all_goals[0]

    def after(minute: int) -> int:
        return sum(1 for m, _ in all_goals if m > minute)

    def before(minute: int) -> int:
        return sum(1 for m, _ in all_goals if m <= minute)

    def in_sh() -> int:
        return sum(1 for m, _ in all_goals if m > 45)

    def goals_after(minute: int) -> tuple[int, int, int]:
        gh = sum(1 for m in home_m if m > minute)
        ga = sum(1 for m in away_m if m > minute)
        return gh + ga, gh, ga

    def goals_in_last(mins: int) -> tuple[int, int, int]:
        thr = 90 - mins
        gh = sum(1 for m in home_m if m > thr)
        ga = sum(1 for m in away_m if m > thr)
        return gh + ga, gh, ga

    h_final, a_final = len(home_m), len(away_m)
    score_trace: list[tuple[int, int]] = []
    hh, aa = 0, 0
    home_was_behind = away_was_behind = False
    home_had_2lead = away_had_2lead = False
    consec_same = False
    for i, (_, t) in enumerate(all_goals):
        if t == "H":
            hh += 1
        else:
            aa += 1
        score_trace.append((hh, aa))
        if hh < aa:
            home_was_behind = True
        if aa < hh:
            away_was_behind = True
        if hh - aa >= 2:
            home_had_2lead = True
        if aa - hh >= 2:
            away_had_2lead = True
        if i > 0 and all_goals[i][1] == all_goals[i - 1][1]:
            consec_same = True

    last_team = all_goals[-1][1] if all_goals else None
    _, gh60, ga60 = goals_after(60)
    gl30, gh30, ga30 = goals_in_last(30)
    gl20, gh20, ga20 = goals_in_last(20)
    gl15, gh15, ga15 = goals_in_last(15)
    gl10, gh10, ga10 = goals_in_last(10)
    gl5, gh5, ga5 = goals_in_last(5)

    return {
        "home_m": home_m,
        "away_m": away_m,
        "all_goals": all_goals,
        "fh_h": fh_h,
        "fh_a": fh_a,
        "sh_h": sh_h,
        "sh_a": sh_a,
        "total_goals": total,
        "first_min": first_min,
        "first_team": first_team,
        "after_60": after(60),
        "after_65": after(65),
        "after_70": after(70),
        "after_75": after(75),
        "after_80": after(80),
        "after_85": after(85),
        "sh_goals": in_sh(),
        "last_min": all_goals[-1][0] if all_goals else None,
        "last_team": last_team,
        "goals_after_45": after(45),
        "gh60": gh60,
        "ga60": ga60,
        "btts_after_60": gh60 >= 1 and ga60 >= 1,
        "goals_last_30": gl30,
        "goals_last_20": gl20,
        "goals_last_15": gl15,
        "goals_last_10": gl10,
        "goals_last_5": gl5,
        "home_last_15": gh15,
        "away_last_15": ga15,
        "home_scores_ht": fh_h >= 1,
        "away_scores_ht": fh_a >= 1,
        "home_scores_2h": sh_h >= 1,
        "away_scores_2h": sh_a >= 1,
        "btts_2h": sh_h >= 1 and sh_a >= 1,
        "comeback_home": home_was_behind and h_final > a_final,
        "comeback_away": away_was_behind and a_final > h_final,
        "double_lead_home": home_had_2lead,
        "double_lead_away": away_had_2lead,
        "draw_after_deficit": h_final == a_final and (home_was_behind or away_was_behind),
        "consecutive_same_team": consec_same,
        "last_goal_home": last_team == "H",
        "last_goal_away": last_team == "A",
    }


def score_at_minute(home_raw: Any, away_raw: Any, minute: int) -> tuple[int, int]:
    home_m = parse_goal_timings(home_raw)
    away_m = parse_goal_timings(away_raw)
    h = sum(1 for m in home_m if m <= minute)
    a = sum(1 for m in away_m if m <= minute)
    return h, a


def attach_timing_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge colonne y_* da minuti gol e stati live."""
    if df.empty:
        return df

    h_col = "home_team_goal_timings" if "home_team_goal_timings" in df.columns else None
    a_col = "away_team_goal_timings" if "away_team_goal_timings" in df.columns else None
    if not h_col:
        return df

    parsed = [
        goals_by_period(row.get(h_col), row.get(a_col))
        for _, row in df.iterrows()
    ]
    pinfo = pd.DataFrame(parsed, index=df.index)

    h = pd.to_numeric(df.get("home_team_goal_count"), errors="coerce").fillna(0)
    a = pd.to_numeric(df.get("away_team_goal_count"), errors="coerce").fillna(0)
    hht = pd.to_numeric(df.get("home_team_goal_count_half_time"), errors="coerce").fillna(pinfo["fh_h"])
    aht = pd.to_numeric(df.get("away_team_goal_count_half_time"), errors="coerce").fillna(pinfo["fh_a"])
    sh_h, sh_a = h - hht, a - aht
    tg = h + a

    sh_total = pinfo["sh_goals"].where(pinfo["sh_goals"] > 0, sh_h + sh_a)
    fht = hht + aht
    fm = pinfo["first_min"]
    home_m_lists = pinfo["home_m"].tolist()
    away_m_lists = pinfo["away_m"].tolist()

    new: dict[str, pd.Series] = {
        "y_over05": tg >= 1,
        "y_over15": tg >= 2,
        "y_over25": tg >= 3,
        "y_over35": tg >= 4,
        "y_over45": tg >= 5,
        "y_under15": tg <= 1,
        "y_under25": tg <= 2,
        "y_under35": tg <= 3,
        "y_btts": (h >= 1) & (a >= 1),
        "y_home_win": h > a,
        "y_away_win": h < a,
        "y_draw": h == a,
        "y_dc_1x": h >= a,
        "y_dc_x2": h <= a,
        "y_dc_12": h != a,
        "y_hc_home_m1": h > a,
        "y_over05_ht": fht >= 1,
        "y_over15_ht": fht >= 2,
        "y_btts_ht": (hht >= 1) & (aht >= 1),
        "y_draw_ht": hht == aht,
        "y_home_ht": hht > aht,
        "y_away_ht": hht < aht,
        "y_over05_2h": sh_total >= 1,
        "y_over15_2h": sh_total >= 2,
        "y_no_goal_2h": sh_total == 0,
        "y_goal_after_60": pinfo["after_60"] >= 1,
        "y_goal_after_65": pinfo["after_65"] >= 1,
        "y_goal_after_70": pinfo["after_70"] >= 1,
        "y_goal_after_75": pinfo["after_75"] >= 1,
        "y_goal_after_80": pinfo["after_80"] >= 1,
        "y_goal_after_85": pinfo["after_85"] >= 1,
        "y_first_goal_home": pinfo["first_team"] == "H",
        "y_first_goal_away": pinfo["first_team"] == "A",
        "y_fg_before_10": fm.notna() & (fm <= 10),
        "y_fg_before_15": fm.notna() & (fm <= 15),
        "y_fg_before_20": fm.notna() & (fm <= 20),
        "y_fg_before_30": fm.notna() & (fm <= 30),
        "y_fg_after_60": fm.notna() & (fm > 60),
        "y_fg_after_70": fm.notna() & (fm > 70),
        "y_fg_after_80": fm.notna() & (fm > 80),
        "y_fg_after_45": fm.notna() & (fm > 45),
        "y_fg_after_75": fm.notna() & (fm > 75),
        "y_fg_after_85": fm.notna() & (fm > 85),
        "y_no_goal_ht": fht == 0,
        "y_home_scores_ht": pinfo["home_scores_ht"],
        "y_away_scores_ht": pinfo["away_scores_ht"],
        "y_home_scores_ft": h >= 1,
        "y_away_scores_ft": a >= 1,
        "y_home_scores_2h": pinfo["home_scores_2h"],
        "y_away_scores_2h": pinfo["away_scores_2h"],
        "y_over25_2h": sh_total >= 3,
        "y_btts_2h": pinfo["btts_2h"],
        "y_btts_after_60": pinfo["btts_after_60"],
        "y_goal_last_30": pinfo["goals_last_30"] >= 1,
        "y_goal_last_20": pinfo["goals_last_20"] >= 1,
        "y_goal_last_15": pinfo["goals_last_15"] >= 1,
        "y_goal_last_10": pinfo["goals_last_10"] >= 1,
        "y_goal_last_5": pinfo["goals_last_5"] >= 1,
        "y_home_scores_last_15": pinfo["home_last_15"] >= 1,
        "y_away_scores_last_15": pinfo["away_last_15"] >= 1,
        "y_comeback_home": pinfo["comeback_home"],
        "y_comeback_away": pinfo["comeback_away"],
        "y_double_lead_home": pinfo["double_lead_home"],
        "y_double_lead_away": pinfo["double_lead_away"],
        "y_draw_after_deficit": pinfo["draw_after_deficit"],
        "y_consecutive_same_team": pinfo["consecutive_same_team"],
        "y_last_goal_home": pinfo["last_goal_home"],
        "y_last_goal_away": pinfo["last_goal_away"],
        "first_goal_min": fm,
        "goals_after_60": pinfo["after_60"],
        "goals_2h": sh_total,
        "live_h_ht": hht,
        "live_a_ht": aht,
        "live_00_ht": (hht == 0) & (aht == 0),
    }
    new["y_btts_no"] = ~new["y_btts"]

    for minute in (45, 60, 65, 70, 75, 80):
        live_h = [sum(1 for m in hm if m <= minute) for hm in home_m_lists]
        live_a = [sum(1 for m in am if m <= minute) for am in away_m_lists]
        lh = pd.Series(live_h, index=df.index, dtype="int8")
        la = pd.Series(live_a, index=df.index, dtype="int8")
        new[f"live_h_{minute}"] = lh
        new[f"live_a_{minute}"] = la
        new[f"live_total_{minute}"] = lh + la
        new[f"live_00_{minute}"] = (lh == 0) & (la == 0)
        new[f"live_10_{minute}"] = (lh == 1) & (la == 0)
        new[f"live_01_{minute}"] = (lh == 0) & (la == 1)
        new[f"live_11_{minute}"] = (lh == 1) & (la == 1)

    return pd.concat([df, pd.DataFrame(new, index=df.index)], axis=1)
