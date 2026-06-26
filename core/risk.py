from config import *

def apply_risk(system, stake, drawdown, profit_history):
    last10 = profit_history[-10:] if len(profit_history) >= 10 else []

    if system == "O25" and (drawdown < DD_BOOST or sum(last10) < 0):
        return 0

    if system == "O15" and drawdown < DD_BOOST:
        stake *= BOOST_O15

    if system == "HT" and drawdown < DD_BOOST:
        stake *= BOOST_HT

    if drawdown < DD_REDUCE:
        stake *= REDUCTION_FACTOR

    return stake
