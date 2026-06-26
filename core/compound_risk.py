from compound_config import (
    DD_REDUCE_10,
    DD_REDUCE_15,
    DD_STOP_20,
    STAKE_REDUCE_10,
    STAKE_REDUCE_15,
    STOP_TRADES_20,
)


class CompoundRiskState:
    def __init__(self):
        self.stop_remaining = 0


def apply_compound_risk(stake_eur, drawdown_pct, state):
    if state.stop_remaining > 0:
        state.stop_remaining -= 1
        return 0.0, True, "stop"

    if drawdown_pct < DD_STOP_20:
        state.stop_remaining = STOP_TRADES_20
        return 0.0, True, "stop_triggered"

    if drawdown_pct < DD_REDUCE_15:
        return stake_eur * STAKE_REDUCE_15, False, "reduce_50"

    if drawdown_pct < DD_REDUCE_10:
        return stake_eur * STAKE_REDUCE_10, False, "reduce_25"

    return stake_eur, False, "normal"
