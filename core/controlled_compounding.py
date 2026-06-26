"""Controlled Compounding System (CCS) — gestione bankroll a scaglioni."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from compound_config import (
    CCS_DOWNGRADE_TRADES,
    CCS_UNIT_TIERS_ASC,
    CCS_WITHDRAWAL_AMOUNT,
    CCS_WITHDRAWAL_THRESHOLD,
)


@dataclass
class WithdrawalRecord:
    date: Any
    amount: float
    bankroll_before: float
    bankroll_after: float
    trade_index: int


@dataclass
class TierReachedRecord:
    threshold_eur: float
    unit_eur: float
    date: Any
    trade_index: int
    bankroll_eur: float


@dataclass
class TradeRecord:
    trade_index: int
    date: Any
    system: str
    vinto: bool
    stake_eur: float
    unit_eur: float
    profit_eur: float
    bankroll_eur: float
    equity_eur: float
    peak_eur: float
    dd_eur: float
    dd_pct: float
    tier_threshold: float
    withdrawn: float = 0.0


class ControlledCompounding:
    """
    Crescita composta controllata: 1U a scaglioni fissi, stake max 1U,
    upgrade solo fuori drawdown, downgrade dopo 50 trade sotto scaglione,
  prelievi automatici oltre 6000€.
    """

    def __init__(self, initial_bankroll: float = 150.0):
        self.initial_bankroll = float(initial_bankroll)
        self.bankroll = float(initial_bankroll)
        self.peak = float(initial_bankroll)
        self._tier_idx = self._tier_index_for_bankroll(self.bankroll)
        self._trades_below_tier = 0
        self.total_withdrawn = 0.0
        self.withdrawals: list[WithdrawalRecord] = []
        self.tiers_reached: list[TierReachedRecord] = []
        self.trades: list[TradeRecord] = []
        self._trade_count = 0

        th, unit = CCS_UNIT_TIERS_ASC[self._tier_idx]
        self.tiers_reached.append(TierReachedRecord(
            threshold_eur=th, unit_eur=unit, date=None, trade_index=0, bankroll_eur=self.bankroll,
        ))

    @staticmethod
    def _tier_index_for_bankroll(bankroll: float) -> int:
        idx = 0
        for i, (threshold, _) in enumerate(CCS_UNIT_TIERS_ASC):
            if bankroll >= threshold:
                idx = i
        return idx

    @property
    def current_unit_eur(self) -> float:
        """Valore 1U corrente (bloccato allo scaglione attivo)."""
        return CCS_UNIT_TIERS_ASC[self._tier_idx][1]

    @property
    def current_tier_threshold(self) -> float:
        return CCS_UNIT_TIERS_ASC[self._tier_idx][0]

    @property
    def in_drawdown(self) -> bool:
        return self.bankroll < self.peak

    @property
    def drawdown_eur(self) -> float:
        return self.bankroll - self.peak

    @property
    def drawdown_pct(self) -> float:
        if self.peak <= 0:
            return 0.0
        return (self.bankroll - self.peak) / self.peak * 100.0

    @property
    def roi_pct(self) -> float:
        if self.initial_bankroll <= 0:
            return 0.0
        total_equity = self.bankroll + self.total_withdrawn
        return (total_equity - self.initial_bankroll) / self.initial_bankroll * 100.0

    def stake_eur(self) -> float:
        """Stake massima: sempre 1U corrente."""
        return self.current_unit_eur

    def can_bet(self) -> bool:
        return self.bankroll >= self.current_unit_eur

    def settle_trade(
        self,
        vinto: bool,
        profit_odds: float,
        date: Any = None,
        system: str = "",
    ) -> float:
        """
        Registra un trade: stake = 1U, profitto in €.
        Ritorna profit_eur (0 se non si può puntare).
        """
        stake = self.stake_eur()
        if not self.can_bet():
            self._log_trade(date, system, vinto, 0.0, stake, 0.0, 0.0)
            return 0.0

        profit = round(stake * profit_odds, 2) if vinto else round(-stake, 2)

        self.bankroll = round(self.bankroll + profit, 2)
        self.peak = max(self.peak, self.bankroll)

        self._try_upgrade_tier(date)
        self._update_downgrade_counter()
        withdrawn = self._apply_withdrawals(date)
        self._log_trade(date, system, vinto, stake, stake, profit, withdrawn)
        return profit

    def _apply_withdrawals(self, date: Any) -> float:
        total = 0.0
        while self.bankroll >= CCS_WITHDRAWAL_THRESHOLD:
            before = self.bankroll
            self.bankroll = round(self.bankroll - CCS_WITHDRAWAL_AMOUNT, 2)
            self.total_withdrawn += CCS_WITHDRAWAL_AMOUNT
            total += CCS_WITHDRAWAL_AMOUNT
            self.withdrawals.append(WithdrawalRecord(
                date=date,
                amount=CCS_WITHDRAWAL_AMOUNT,
                bankroll_before=before,
                bankroll_after=self.bankroll,
                trade_index=self._trade_count,
            ))
            self.peak = self.bankroll
        return total

    def _try_upgrade_tier(self, date: Any) -> None:
        if self.in_drawdown:
            return
        if self._tier_idx >= len(CCS_UNIT_TIERS_ASC) - 1:
            return
        next_threshold, next_unit = CCS_UNIT_TIERS_ASC[self._tier_idx + 1]
        if self.bankroll >= next_threshold:
            self._tier_idx += 1
            self._trades_below_tier = 0
            if not any(t.unit_eur == next_unit for t in self.tiers_reached):
                self.tiers_reached.append(TierReachedRecord(
                    threshold_eur=next_threshold,
                    unit_eur=next_unit,
                    date=date,
                    trade_index=self._trade_count,
                    bankroll_eur=self.bankroll,
                ))

    def _update_downgrade_counter(self) -> None:
        if self._tier_idx == 0:
            self._trades_below_tier = 0
            return
        threshold = CCS_UNIT_TIERS_ASC[self._tier_idx][0]
        if self.bankroll < threshold:
            self._trades_below_tier += 1
            if self._trades_below_tier >= CCS_DOWNGRADE_TRADES:
                self._tier_idx -= 1
                self._trades_below_tier = 0
        else:
            self._trades_below_tier = 0

    def _log_trade(
        self,
        date: Any,
        system: str,
        vinto: bool,
        stake_eur: float,
        unit_eur: float,
        profit_eur: float,
        withdrawn: float,
    ) -> None:
        self.trades.append(TradeRecord(
            trade_index=self._trade_count,
            date=date,
            system=system,
            vinto=vinto,
            stake_eur=stake_eur,
            unit_eur=unit_eur,
            profit_eur=profit_eur,
            bankroll_eur=self.bankroll,
            equity_eur=round(self.bankroll + self.total_withdrawn, 2),
            peak_eur=self.peak,
            dd_eur=self.drawdown_eur,
            dd_pct=self.drawdown_pct,
            tier_threshold=self.current_tier_threshold,
            withdrawn=withdrawn,
        ))
        self._trade_count += 1

    def summary(self) -> dict[str, Any]:
        active = [t for t in self.trades if t.stake_eur > 0]
        max_dd_eur = min((t.dd_eur for t in self.trades), default=0.0)
        max_dd_pct = min((t.dd_pct for t in self.trades), default=0.0)
        total_profit = self.bankroll + self.total_withdrawn - self.initial_bankroll

        return {
            "initial_bankroll": self.initial_bankroll,
            "final_bankroll": self.bankroll,
            "total_profit_eur": round(total_profit, 2),
            "roi_pct": round(self.roi_pct, 2),
            "total_withdrawn": round(self.total_withdrawn, 2),
            "n_withdrawals": len(self.withdrawals),
            "max_dd_eur": round(max_dd_eur, 2),
            "max_dd_pct": round(max_dd_pct, 2),
            "current_unit_eur": self.current_unit_eur,
            "current_tier_threshold": self.current_tier_threshold,
            "trades": len(active),
            "winrate": round(sum(1 for t in active if t.profit_eur > 0) / len(active), 4) if active else 0.0,
        }

    def tiers_dataframe_rows(self) -> list[dict]:
        return [
            {
                "Scaglione (€)": r.threshold_eur,
                "1U (€)": r.unit_eur,
                "Data raggiungimento": r.date,
                "Trade #": r.trade_index,
                "Bankroll (€)": r.bankroll_eur,
            }
            for r in self.tiers_reached
        ]

    def withdrawals_dataframe_rows(self) -> list[dict]:
        return [
            {
                "Data": w.date,
                "Importo (€)": w.amount,
                "Bankroll prima": w.bankroll_before,
                "Bankroll dopo": w.bankroll_after,
                "Trade #": w.trade_index,
            }
            for w in self.withdrawals
        ]

    def clone_fresh(self) -> ControlledCompounding:
        return ControlledCompounding(self.initial_bankroll)
