from core.sh_optimizer_common import format_sh_params as format_params, optimize_sh_system


def optimize_sh1(df, patterns=None, iterations=3000, seed=42, aggressive=False, max_dd_limit=-18.0):
    del aggressive
    return optimize_sh_system(df, "SH1", patterns, iterations, seed=seed, max_dd_limit=max_dd_limit)
