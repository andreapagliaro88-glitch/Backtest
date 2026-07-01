"""Pianificazione trade giornaliero allineata a combo pattern + stake tier."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import uuid

from core.controlled_compounding import ControlledCompounding
from core.fixture_parser import pattern_from_fixture_filename
from core.tier_backtest import TierState, process_tier_trade
from core.tier_config import default_tier_risk, profit_odds_for
from core.tier_engine import TierRules, classify_tier, stake_u_for_tier, tier_label


@dataclass
class StrategyDailyPlanConfig:
    system: str
    rules: TierRules
    active_patterns: tuple[str, ...]


def patterns_from_fonti(fonti: str, system: str) -> list[str]:
  names = [s.strip() for s in str(fonti or "").split(",") if s.strip()]
  out: list[str] = []
  seen: set[str] = set()
  for name in names:
    pat = pattern_from_fixture_filename(name, system)
    if pat and pat not in seen:
      seen.add(pat)
      out.append(pat)
  return out


def active_patterns_on_match(
    patterns: list[str] | None,
    fonti: str,
    system: str,
    active_patterns: tuple[str, ...],
) -> list[str]:
    combo = set(active_patterns)
    if patterns:
        return [p for p in patterns if p in combo]
    return [p for p in patterns_from_fonti(fonti, system) if p in combo]


def replay_tier_state(
    journal_rows: list[dict],
    system: str,
    rules: TierRules,
    active_patterns: tuple[str, ...] | None = None,
) -> TierState:
    """Ricostruisce shock/streak tier dai trade regolati."""
    state = TierState()
    risk = default_tier_risk(system)
    profit_odds = profit_odds_for(system)
    combo = set(active_patterns or ())

    for row in journal_rows:
        if str(row.get("strategia")) != system:
            continue
        if row.get("esito") not in ("VINTO", "PERSO"):
            continue
        pats = list(row.get("patterns") or [])
        if not pats:
            pats = pats_from_note(row)
        if not pats:
            pats = patterns_from_fonti(row.get("fonti", ""), system)
        if combo:
            pats = [p for p in pats if p in combo]
        if not pats:
            segnali = int(row.get("segnali") or 0)
            if segnali > 0:
                pats = [f"engine_{i}" for i in range(segnali)]
        fake = SimpleNamespace(
            patterns=pats,
            vinto=row.get("esito") == "VINTO",
        )
        process_tier_trade(fake, state, rules=rules, risk=risk, profit_odds=profit_odds)
    return state


def pats_from_note(row: dict) -> list[str]:
    note = str(row.get("note") or "")
    prefix = "Pattern: "
    if prefix not in note:
        return []
    chunk = note.split("|", 1)[0].replace(prefix, "").strip()
    if not chunk:
        return []
    return [p.strip() for p in chunk.split("+") if p.strip()]


def plan_tier_daily_match(
    row0,
    match_id,
    patterns: list[str],
    cfg: StrategyDailyPlanConfig,
    tier_state: TierState,
    ccs: ControlledCompounding,
    *,
    fonti: str = "",
) -> dict:
    """Pianifica un trade tier con stake T1–T4 della pagina strategia."""
    active = [p for p in patterns if p in cfg.active_patterns]
    if not active:
        active = active_patterns_on_match(None, fonti, cfg.system, cfg.active_patterns)

    risk = default_tier_risk(cfg.system)
    profit_odds = profit_odds_for(cfg.system)

    if not active:
        return _skip_tier_row(row0, match_id, cfg.system, "Nessun pattern della combo attiva", fonti=fonti)

    tier = classify_tier(active, cfg.rules)
    if tier is None:
        return _skip_tier_row(
            row0, match_id, cfg.system,
            f"Pattern non classificati ({' + '.join(active)})",
            fonti=fonti,
            patterns=active,
        )

    if tier == 4 and tier_state.tier4_blocked > 0:
        return _skip_tier_row(
            row0, match_id, cfg.system, "T4 bloccato (streak)",
            fonti=fonti, patterns=active, tier=tier,
        )

    stake_u = stake_u_for_tier(tier, cfg.rules)
    if tier_state.t23_reduced and tier in (2, 3):
        stake_u *= risk.reduce_t23_factor
    if tier_state.shock_mode > 0:
        stake_u *= risk.shock_factor

    stake_u = round(stake_u, 2)
    if stake_u <= 0:
        return _skip_tier_row(row0, match_id, cfg.system, "Stake 0", fonti=fonti, patterns=active, tier=tier)

    unit_eur = ccs.stake_eur()
    if not ccs.can_bet(stake_u):
        return _skip_tier_row(
            row0, match_id, cfg.system, "Bankroll insufficiente",
            fonti=fonti, patterns=active, tier=tier,
        )

    stake_eur = round(stake_u * unit_eur, 2)
    patterns_str = " + ".join(active)
    return {
        "trade_id": str(uuid.uuid4())[:8],
        "data": row0["data"],
        "ora": row0.get("ora", ""),
        "campionato": row0.get("campionato", ""),
        "partita": row0.get("partita", ""),
        "match_id": match_id,
        "strategia": cfg.system,
        "segnali": len(active),
        "signals_ht": 0,
        "signals_o15": 0,
        "signals_o25": 0,
        "signals_sh0": len(active) if cfg.system in ("SH0", "SH1", "SH2") else 0,
        "stake_u": stake_u,
        "valore_1u": round(unit_eur, 2),
        "stake_eur": stake_eur,
        "fase": tier_label(tier),
        "modalita_rischio": "Tier",
        "esito": "DA GIOCARE",
        "profit_u": None,
        "profit_eur": None,
        "bankroll_eur": round(ccs.bankroll, 2),
        "equity_u": round(tier_state.equity, 2),
        "dd_u": round(tier_state.equity - tier_state.peak, 2),
        "fonti": fonti,
        "note": f"Pattern: {patterns_str} | {tier_label(tier)}",
        "patterns": active,
        "tier": tier,
    }


def apply_tier_settlement(
    trade: dict,
    vinto: bool,
    ccs: ControlledCompounding,
    tier_state: TierState,
    cfg: StrategyDailyPlanConfig,
) -> dict:
    """Registra esito tier e aggiorna stato streak/shock."""
    stake_u = float(trade.get("stake_u") or 0)
    odds = profit_odds_for(cfg.system)
    profit_eur = ccs.settle_trade(
        vinto=vinto,
        profit_odds=odds,
        date=trade.get("data"),
        system=cfg.system,
        stake_u=stake_u,
    )
    profit_u = round(stake_u * odds, 2) if vinto else round(-stake_u, 2)

    patterns = trade.get("patterns") or pats_from_note(trade) or patterns_from_fonti(
        trade.get("fonti", ""), cfg.system,
    )
    fake = SimpleNamespace(patterns=list(patterns), vinto=vinto)
    risk = default_tier_risk(cfg.system)
    process_tier_trade(
        fake, tier_state, rules=cfg.rules, risk=risk, profit_odds=odds,
    )

    trade["esito"] = "VINTO" if vinto else "PERSO"
    trade["profit_u"] = profit_u
    trade["profit_eur"] = profit_eur
    trade["bankroll_eur"] = round(ccs.bankroll, 2)
    trade["equity_u"] = round(tier_state.equity, 2)
    trade["dd_u"] = round(tier_state.equity - tier_state.peak, 2)
    return trade


def _skip_tier_row(row0, match_id, system, reason, *, fonti="", patterns=None, tier=None):
    patterns = patterns or []
    patterns_str = " + ".join(patterns) if patterns else "—"
    return {
        "trade_id": str(uuid.uuid4())[:8],
        "data": row0["data"],
        "ora": row0.get("ora", ""),
        "campionato": row0.get("campionato", ""),
        "partita": row0.get("partita", ""),
        "match_id": match_id,
        "strategia": "—",
        "segnali": 0,
        "signals_ht": 0,
        "signals_o15": 0,
        "signals_o25": 0,
        "signals_sh0": 0,
        "stake_u": 0,
        "valore_1u": 0,
        "stake_eur": 0,
        "fase": tier_label(tier) if tier else "",
        "modalita_rischio": "",
        "esito": "SALTATO",
        "profit_u": 0,
        "profit_eur": 0,
        "bankroll_eur": None,
        "equity_u": None,
        "dd_u": None,
        "fonti": fonti,
        "note": f"{reason} ({patterns_str})",
        "patterns": patterns,
        "tier": tier,
    }
