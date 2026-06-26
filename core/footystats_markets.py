"""Mercati analizzabili sui CSV FootyStats."""

MARKETS = {
    "over05_ht": {
        "label": "Over 0.5 HT (gol 1° tempo)",
        "target_col": "fh_goal",
        "odds_col": None,
        "default_odd": 1.38,
    },
    "over05_2h": {
        "label": "Over 0.5 2T (gol 2° tempo)",
        "target_col": "sh_goal",
        "odds_col": None,
        "default_odd": 1.28,
    },
    "over15_2h": {
        "label": "Over 1.5 2T (2+ gol 2° tempo)",
        "target_col": "sh_2plus",
        "odds_col": None,
        "default_odd": 2.10,
    },
    "over15": {
        "label": "Over 1.5 FT",
        "target_col": "ft_2plus",
        "odds_col": "odds_ft_over15",
        "default_odd": 1.30,
    },
    "over25": {
        "label": "Over 2.5 FT",
        "target_col": "ft_3plus",
        "odds_col": "odds_ft_over25",
        "default_odd": 1.85,
    },
    "over35": {
        "label": "Over 3.5 FT",
        "target_col": "ft_4plus",
        "odds_col": "odds_ft_over35",
        "default_odd": 2.80,
    },
    "btts": {
        "label": "BTTS Sì",
        "target_col": "btts",
        "odds_col": "odds_btts_yes",
        "default_odd": 1.75,
    },
    "home_win": {
        "label": "Vittoria 1",
        "target_col": "home_win",
        "odds_col": "odds_ft_home_team_win",
        "default_odd": None,
    },
    "draw": {
        "label": "Pareggio X",
        "target_col": "draw",
        "odds_col": "odds_ft_draw",
        "default_odd": None,
    },
    "away_win": {
        "label": "Vittoria 2",
        "target_col": "away_win",
        "odds_col": "odds_ft_away_team_win",
        "default_odd": None,
    },
}

SCAN_COLS = {
    "odd_1": (1.2, 4.0),
    "odd_x": (2.5, 4.5),
    "odd_2": (1.2, 5.0),
    "odd_fav": (1.2, 2.8),
    "odd_dog": (3.0, 8.0),
    "spread_fav_dog": (1.0, 6.0),
}

MIN_SAMPLE = 30
MIN_ROBUST = 80
