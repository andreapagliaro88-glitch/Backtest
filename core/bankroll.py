from compound_config import UNIT_TIERS, UNITS_DIVISOR_BELOW_MIN


def unit_eur_for_bankroll(bankroll):
    for threshold, unit_eur in UNIT_TIERS:
        if bankroll >= threshold:
            return unit_eur
    return bankroll / UNITS_DIVISOR_BELOW_MIN


class Bankroll:
    def __init__(self, initial):
        self.initial = initial
        self.bankroll = initial
        self.peak = initial

    @property
    def unit_size(self):
        return unit_eur_for_bankroll(self.bankroll)

    @property
    def drawdown_eur(self):
        return self.bankroll - self.peak

    @property
    def drawdown_pct(self):
        if self.peak == 0:
            return 0.0
        return (self.bankroll - self.peak) / self.peak * 100

    @property
    def roi_pct(self):
        if self.initial == 0:
            return 0.0
        return (self.bankroll - self.initial) / self.initial * 100

    def apply_profit(self, profit_eur):
        self.bankroll += profit_eur
        self.peak = max(self.peak, self.bankroll)
