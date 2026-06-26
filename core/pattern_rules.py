"""Regole filtro per pattern discovery."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict

import pandas as pd


@dataclass
class Rule:
    feature: str
    op: str  # between | gt | lt
    lo: float | None = None
    hi: float | None = None
    val: float | None = None
    eq_val: bool | int | float | None = None

    def describe(self) -> str:
        if self.op == "between":
            return f"{self.feature} in [{self.lo:.3g}, {self.hi:.3g}]"
        if self.op == "gt":
            return f"{self.feature} > {self.val:.3g}"
        if self.op == "eq":
            return f"{self.feature} == {self.val}"
        return f"{self.feature} < {self.val:.3g}"

    def mask(self, df: pd.DataFrame) -> pd.Series:
        s = df[self.feature]
        if self.op == "between":
            return (s >= self.lo) & (s <= self.hi)
        if self.op == "gt":
            return s > self.val
        if self.op == "eq":
            return s.astype(bool) if s.dtype == bool else (s == self.val)
        return s < self.val

    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)
