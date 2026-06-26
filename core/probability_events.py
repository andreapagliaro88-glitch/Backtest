"""Registro eventi per Probability Pattern Engine."""
from __future__ import annotations

EVENT_DEFS: dict[str, dict] = {
    # Goal FT
    "evt_over1_ft": {"y": "y_over05", "label": "Almeno 1 gol FT", "group": "Goal"},
    "evt_over2_ft": {"y": "y_over15", "label": "Almeno 2 gol FT", "group": "Goal"},
    "evt_over3_ft": {"y": "y_over25", "label": "Almeno 3 gol FT", "group": "Goal"},
    "evt_over4_ft": {"y": "y_over35", "label": "Almeno 4 gol FT", "group": "Goal"},
    "evt_over5_ft": {"y": "y_over45", "label": "Almeno 5 gol FT", "group": "Goal"},
    # Primo tempo
    "evt_over1_ht": {"y": "y_over05_ht", "label": "Almeno 1 gol HT", "group": "Primo Tempo"},
    "evt_over2_ht": {"y": "y_over15_ht", "label": "Almeno 2 gol HT", "group": "Primo Tempo"},
    "evt_no_goal_ht": {"y": "y_no_goal_ht", "label": "Nessun gol HT", "group": "Primo Tempo"},
    "evt_home_scores_ht": {"y": "y_home_scores_ht", "label": "Home segna HT", "group": "Primo Tempo"},
    "evt_away_scores_ht": {"y": "y_away_scores_ht", "label": "Away segna HT", "group": "Primo Tempo"},
    # Secondo tempo
    "evt_over1_2h": {"y": "y_over05_2h", "label": "Almeno 1 gol 2T", "group": "Secondo Tempo"},
    "evt_over2_2h": {"y": "y_over15_2h", "label": "Almeno 2 gol 2T", "group": "Secondo Tempo"},
    "evt_over3_2h": {"y": "y_over25_2h", "label": "Almeno 3 gol 2T", "group": "Secondo Tempo"},
    "evt_no_goal_2h": {"y": "y_no_goal_2h", "label": "Nessun gol 2T", "group": "Secondo Tempo"},
    "evt_btts_2h": {"y": "y_btts_2h", "label": "Entrambe segnano 2T", "group": "Secondo Tempo"},
    # Timing primo gol
    "evt_fg_before_10": {"y": "y_fg_before_10", "label": "Primo gol entro 10'", "group": "Timing"},
    "evt_fg_before_15": {"y": "y_fg_before_15", "label": "Primo gol entro 15'", "group": "Timing"},
    "evt_fg_before_20": {"y": "y_fg_before_20", "label": "Primo gol entro 20'", "group": "Timing"},
    "evt_fg_before_30": {"y": "y_fg_before_30", "label": "Primo gol entro 30'", "group": "Timing"},
    "evt_fg_after_45": {"y": "y_fg_after_45", "label": "Primo gol dopo 45'", "group": "Timing"},
    "evt_fg_after_60": {"y": "y_fg_after_60", "label": "Primo gol dopo 60'", "group": "Timing"},
    "evt_fg_after_70": {"y": "y_fg_after_70", "label": "Primo gol dopo 70'", "group": "Timing"},
    "evt_fg_after_75": {"y": "y_fg_after_75", "label": "Primo gol dopo 75'", "group": "Timing"},
    "evt_fg_after_80": {"y": "y_fg_after_80", "label": "Primo gol dopo 80'", "group": "Timing"},
    "evt_fg_after_85": {"y": "y_fg_after_85", "label": "Primo gol dopo 85'", "group": "Timing"},
    "evt_goal_after_60": {"y": "y_goal_after_60", "label": "Gol dopo 60'", "group": "Timing"},
    "evt_goal_after_70": {"y": "y_goal_after_70", "label": "Gol dopo 70'", "group": "Timing"},
    "evt_goal_after_75": {"y": "y_goal_after_75", "label": "Gol dopo 75'", "group": "Timing"},
    "evt_goal_after_80": {"y": "y_goal_after_80", "label": "Gol dopo 80'", "group": "Timing"},
    "evt_goal_after_85": {"y": "y_goal_after_85", "label": "Gol dopo 85'", "group": "Timing"},
    # Ultimi minuti
    "evt_goal_last_30": {"y": "y_goal_last_30", "label": "Gol negli ultimi 30'", "group": "Ultimi minuti"},
    "evt_goal_last_20": {"y": "y_goal_last_20", "label": "Gol negli ultimi 20'", "group": "Ultimi minuti"},
    "evt_goal_last_15": {"y": "y_goal_last_15", "label": "Gol negli ultimi 15'", "group": "Ultimi minuti"},
    "evt_goal_last_10": {"y": "y_goal_last_10", "label": "Gol negli ultimi 10'", "group": "Ultimi minuti"},
    "evt_goal_last_5": {"y": "y_goal_last_5", "label": "Gol negli ultimi 5'", "group": "Ultimi minuti"},
    # Casa
    "evt_home_first_goal": {"y": "y_first_goal_home", "label": "Casa segna per prima", "group": "Squadra Casa"},
    "evt_home_scores_ft": {"y": "y_home_scores_ft", "label": "Casa segna almeno 1 gol", "group": "Squadra Casa"},
    "evt_home_scores_2h": {"y": "y_home_scores_2h", "label": "Casa segna nel 2T", "group": "Squadra Casa"},
    "evt_home_scores_last_15": {"y": "y_home_scores_last_15", "label": "Casa segna ultimi 15'", "group": "Squadra Casa"},
    "evt_comeback_home": {"y": "y_comeback_home", "label": "Casa rimonta e vince", "group": "Squadra Casa"},
    "evt_double_lead_home": {"y": "y_double_lead_home", "label": "Casa doppio vantaggio", "group": "Squadra Casa"},
    "evt_last_goal_home": {"y": "y_last_goal_home", "label": "Casa segna per ultima", "group": "Squadra Casa"},
    # Ospite
    "evt_away_first_goal": {"y": "y_first_goal_away", "label": "Ospite segna per prima", "group": "Squadra Ospite"},
    "evt_away_scores_ft": {"y": "y_away_scores_ft", "label": "Ospite segna almeno 1 gol", "group": "Squadra Ospite"},
    "evt_away_scores_2h": {"y": "y_away_scores_2h", "label": "Ospite segna nel 2T", "group": "Squadra Ospite"},
    "evt_away_scores_last_15": {"y": "y_away_scores_last_15", "label": "Ospite segna ultimi 15'", "group": "Squadra Ospite"},
    "evt_comeback_away": {"y": "y_comeback_away", "label": "Ospite rimonta e vince", "group": "Squadra Ospite"},
    "evt_double_lead_away": {"y": "y_double_lead_away", "label": "Ospite doppio vantaggio", "group": "Squadra Ospite"},
    "evt_last_goal_away": {"y": "y_last_goal_away", "label": "Ospite segna per ultima", "group": "Squadra Ospite"},
    # BTTS
    "evt_btts": {"y": "y_btts", "label": "BTTS", "group": "BTTS"},
    "evt_btts_no": {"y": "y_btts_no", "label": "BTTS No", "group": "BTTS"},
    "evt_btts_after_60": {"y": "y_btts_after_60", "label": "BTTS dopo 60'", "group": "BTTS"},
    # Sequenza
    "evt_draw_after_deficit": {"y": "y_draw_after_deficit", "label": "Pareggio dopo svantaggio", "group": "Sequenza gol"},
    "evt_consecutive_same_team": {"y": "y_consecutive_same_team", "label": "Gol consecutivi stessa squadra", "group": "Sequenza gol"},
}


def event_ycols() -> dict[str, str]:
    return {eid: cfg["y"] for eid, cfg in EVENT_DEFS.items()}


def events_for_discovery(df_columns) -> list[str]:
    cols = set(df_columns)
    return [eid for eid, cfg in EVENT_DEFS.items() if cfg["y"] in cols]
