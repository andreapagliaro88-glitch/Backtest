import pandas as pd

from core.pattern_loader import load_pattern_data


def load_data(base_path="data"):
    return load_pattern_data(base_path)
