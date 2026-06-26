"""Mappatura pattern → mercati compatibili (senza quote)."""
from __future__ import annotations

EVENT_TRADING_MAP: dict[str, list[str]] = {
    "evt_over1_ft": ["Over 0.5 FT", "Lay 0-0", "Next Goal", "Asian Goal Line O0.5"],
    "evt_over2_ft": ["Over 1.5 FT", "Over 0.5 FT", "Next Goal", "Lay Under 1.5"],
    "evt_over3_ft": ["Over 2.5 FT", "Over 1.5 FT", "Correct Score alto", "Lay Under 2.5"],
    "evt_over4_ft": ["Over 3.5 FT", "Over 2.5 FT", "Correct Score 3+", "Lay Under 3.5"],
    "evt_over5_ft": ["Over 4.5 FT", "Correct Score 4+", "Lay Under 4.5"],
    "evt_over1_ht": ["Over 0.5 HT", "Primo gol HT", "Lay 0-0 HT"],
    "evt_over2_ht": ["Over 1.5 HT", "Over 0.5 HT", "Lay Under 1.5 HT"],
    "evt_no_goal_ht": ["Under 0.5 HT", "Lay Over 0.5 HT", "0-0 HT"],
    "evt_home_scores_ht": ["Home segna HT", "Home Over 0.5 team goals HT", "1-0 HT"],
    "evt_away_scores_ht": ["Away segna HT", "Away Over 0.5 team goals HT", "0-1 HT"],
    "evt_over1_2h": ["Over 0.5 2T", "Gol 2T", "Lay 0-0 2T"],
    "evt_over2_2h": ["Over 1.5 2T", "Over 0.5 2T", "Lay Under 1.5 2T"],
    "evt_over3_2h": ["Over 2.5 2T", "Over 1.5 2T"],
    "evt_no_goal_2h": ["Under 0.5 2T", "Lay Over 0.5 2T", "0-0 2T"],
    "evt_btts_2h": ["BTTS 2T", "Entrambe segnano 2T"],
    "evt_fg_before_10": ["Primo gol entro 10'", "Fast Start", "Over 0.5 entro 10'"],
    "evt_fg_before_15": ["Primo gol entro 15'", "Early Goal"],
    "evt_fg_before_20": ["Primo gol entro 20'"],
    "evt_fg_before_30": ["Primo gol entro 30'", "Over 0.5 entro 30'"],
    "evt_fg_after_45": ["Primo gol 2T", "Late Start", "Under 0.5 HT + Over FT"],
    "evt_fg_after_60": ["Primo gol dopo 60'", "Late Goal"],
    "evt_fg_after_70": ["Primo gol dopo 70'"],
    "evt_fg_after_75": ["Primo gol dopo 75'"],
    "evt_fg_after_80": ["Primo gol dopo 80'"],
    "evt_fg_after_85": ["Primo gol dopo 85'"],
    "evt_goal_after_60": ["Gol dopo 60'", "Over 0.5 live 60'", "Next Goal live"],
    "evt_goal_after_70": ["Gol dopo 70'", "Next Goal live 70'"],
    "evt_goal_after_75": ["Gol dopo 75'"],
    "evt_goal_after_80": ["Gol dopo 80'"],
    "evt_goal_after_85": ["Gol dopo 85'", "Ultimi minuti"],
    "evt_goal_last_30": ["Gol ultimi 30'", "Late Goals", "Over live 60-90"],
    "evt_goal_last_20": ["Gol ultimi 20'"],
    "evt_goal_last_15": ["Gol ultimi 15'", "Final Push"],
    "evt_goal_last_10": ["Gol ultimi 10'"],
    "evt_goal_last_5": ["Gol ultimi 5'", "Injury Time Goals"],
    "evt_home_first_goal": ["Home Next Goal", "Primo gol Casa", "1X"],
    "evt_home_scores_ft": ["Home Over 0.5 team goals", "Home to Score", "1"],
    "evt_home_scores_2h": ["Home segna 2T", "Home 2T Goal"],
    "evt_home_scores_last_15": ["Home segna ultimi 15'", "Home Late Goal"],
    "evt_comeback_home": ["Home Win", "Home rimonta", "1 live da svantaggio"],
    "evt_double_lead_home": ["Home -1 Handicap", "Home Win to Nil dopo 2-0"],
    "evt_last_goal_home": ["Home Last Goal", "Ultimo marcatore Casa"],
    "evt_away_first_goal": ["Away Next Goal", "Primo gol Ospite", "X2"],
    "evt_away_scores_ft": ["Away Over 0.5 team goals", "Away to Score", "2"],
    "evt_away_scores_2h": ["Away segna 2T", "Away 2T Goal"],
    "evt_away_scores_last_15": ["Away segna ultimi 15'", "Away Late Goal"],
    "evt_comeback_away": ["Away Win", "Away rimonta", "2 live da svantaggio"],
    "evt_double_lead_away": ["Away -1 Handicap", "Away Win to Nil dopo 0-2"],
    "evt_last_goal_away": ["Away Last Goal", "Ultimo marcatore Ospite"],
    "evt_btts": ["BTTS", "Both Teams to Score", "Lay BTTS No"],
    "evt_btts_no": ["BTTS No", "Clean Sheet", "Lay BTTS"],
    "evt_btts_after_60": ["BTTS live dopo 60'", "Entrambe segnano post-60"],
    "evt_draw_after_deficit": ["Draw", "X", "Pareggio live da svantaggio"],
    "evt_consecutive_same_team": ["Stessa squadra segna di nuovo", "Next Goal stessa squadra"],
}


def suggest_markets(event_id: str, probability: float, lift: float) -> list[str]:
    base = list(EVENT_TRADING_MAP.get(event_id, ["Mercato compatibile da valutare"]))
    extra: list[str] = []
    if probability >= 0.70:
        extra.append("Lay contro esito opposto (alta probabilità)")
    if lift >= 1.4:
        extra.append("Value pre-match se quota implicita < probabilità osservata")
    if event_id.startswith("evt_no_goal") or event_id == "evt_btts_no":
        extra.append("Lay Over / Lay BTTS")
    return list(dict.fromkeys(base + extra))
