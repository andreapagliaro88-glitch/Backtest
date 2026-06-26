def get_stake(system, signals):
    if system == 'HT':
        return 4.0 if signals >= 3 else 2.2 if signals == 2 else 0.7
    if system == 'O25':
        return 2.5 if signals >= 4 else 1.6 if signals == 3 else 0.8
    if system == 'O15':
        return 5.0 if signals >= 4 else 3.0 if signals == 3 else 1.5
    return 0
