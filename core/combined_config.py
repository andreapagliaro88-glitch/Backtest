from dataclasses import dataclass, field


@dataclass
class CombinedParams:
    priority_dd_threshold: float = -12.0
    priority_normal: tuple = ("HT", "SH0", "O15", "O25")
    priority_crisis: tuple = ("O25", "SH0", "O15", "HT")
    skip_o25_below_dd: float | None = -15.0
    skip_o15_below_dd: float | None = -18.0
    skip_sh0_below_dd: float | None = -18.0
    full_stop_dd: float | None = -15.0
    full_stop_trades: int = 5

    def priority_for(self, drawdown_u: float) -> tuple:
        if drawdown_u < self.priority_dd_threshold:
            return self.priority_crisis
        return self.priority_normal

    def allowed_systems(self, drawdown_u: float) -> set | None:
        blocked = set()
        if self.skip_o25_below_dd is not None and drawdown_u < self.skip_o25_below_dd:
            blocked.add("O25")
        if self.skip_o15_below_dd is not None and drawdown_u < self.skip_o15_below_dd:
            blocked.add("O15")
        if self.skip_sh0_below_dd is not None and drawdown_u < self.skip_sh0_below_dd:
            blocked.add("SH0")
        return blocked
