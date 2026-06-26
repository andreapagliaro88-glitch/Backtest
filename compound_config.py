INITIAL_BANKROLL = 150.0

UNIT_TIER_PHASES = [
    ("FASE 1 — MICRO", [(150, 3), (200, 4), (250, 5)]),
    ("FASE 2 — BUILD", [(300, 6), (400, 8), (500, 10)]),
    ("FASE 3 — SCALE", [(600, 12), (800, 16), (1000, 20)]),
    ("FASE 4 — SERIO", [(1250, 25), (1500, 30), (2000, 40)]),
    ("FASE 5 — PRO", [(2500, 50)]),
]

UNITS_DIVISOR_BELOW_MIN = 50  # sotto 150€: 1U = bankroll / 50

# --- Controlled Compounding System (CCS) ---
CCS_UNIT_TIERS_ASC = [
    (150, 3),
    (200, 4),
    (250, 5),
    (300, 6),
    (400, 8),
    (500, 10),
    (600, 12),
    (800, 16),
    (1000, 20),
    (1250, 25),
    (1500, 30),
    (2000, 40),
    (2500, 50),
]

CCS_WITHDRAWAL_THRESHOLD = 6000.0
CCS_WITHDRAWAL_AMOUNT = 1000.0
CCS_DOWNGRADE_TRADES = 50

# Retrocompatibilità: scaglioni in ordine decrescente
UNIT_TIERS = list(reversed(CCS_UNIT_TIERS_ASC))

_UNIT_TO_PHASE = {unit: phase for phase, tiers in UNIT_TIER_PHASES for _, unit in tiers}


def phase_for_unit_eur(unit_eur):
    return _UNIT_TO_PHASE.get(round(unit_eur, 2), "")


DD_REDUCE_10 = -10
DD_REDUCE_15 = -15
DD_STOP_20 = -20

STAKE_REDUCE_10 = 0.75
STAKE_REDUCE_15 = 0.50
STOP_TRADES_20 = 10

PROFIT_ODDS = {"HT": 0.4, "O15": 0.35, "O25": 0.8, "SH0": 0.3, "SH1": 0.3, "SH2": 0.3}
