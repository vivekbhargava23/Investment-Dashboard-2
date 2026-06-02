"""Auto-resolve ISIN → ticker + tax kind using yfinance Search."""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Literal

from app.domain.money import Currency
from app.domain.tax.classification import InstrumentKind
from app.ports.company_data import CompanyDataProvider
from app.ports.ticker_resolver import TickerMatch, TickerResolver

_DE_SUFFIXES = {".DE", ".F", ".MU", ".BE", ".DU", ".HM", ".HA", ".SG", ".NW"}

_QUOTE_TYPE_TO_KIND: dict[str, InstrumentKind] = {
    "EQUITY": InstrumentKind.AKTIE,
    "ETF": InstrumentKind.AKTIENFONDS,
    "MUTUALFUND": InstrumentKind.MISCHFONDS,
}


@dataclass(frozen=True)
class AutoResolveResult:
    isin: str
    ticker: str | None
    name: str | None
    instrument_kind: InstrumentKind | None
    confidence: Literal["high", "medium", "low"]
    reason: str


def autoresolve_isin(
    isin: str,
    description_hint: str,
    *,
    resolver: TickerResolver,
    company_provider: CompanyDataProvider,
) -> AutoResolveResult:
    """Resolve an ISIN to a ticker and InstrumentKind.

    Uses resolver.resolve(isin) (yfinance Search accepts ISINs as queries).
    Fetches quoteType cheaply via company_provider.get_quote_type().
    """
    try:
        matches = resolver.resolve(isin, limit=5)
    except Exception as exc:
        return AutoResolveResult(
            isin=isin,
            ticker=None,
            name=None,
            instrument_kind=None,
            confidence="low",
            reason=f"Resolver error: {exc}",
        )

    if not matches:
        return AutoResolveResult(
            isin=isin,
            ticker=None,
            name=None,
            instrument_kind=None,
            confidence="low",
            reason="yfinance Search returned no matches for ISIN",
        )

    if len(matches) == 1:
        chosen = matches[0]
        confidence: Literal["high", "medium", "low"] = "high"
        reason = f"yfinance Search single match: {chosen.symbol}"
    else:
        chosen, confidence, reason = _pick_best(matches, description_hint)

    kind, kind_reason = _resolve_kind(chosen.symbol, company_provider)

    return AutoResolveResult(
        isin=isin,
        ticker=chosen.symbol,
        name=chosen.name or description_hint or None,
        instrument_kind=kind,
        confidence=confidence if kind is not None else "low",
        reason=f"{reason}; {kind_reason}",
    )


def _pick_best(
    matches: list[TickerMatch],
    description_hint: str,
) -> tuple[TickerMatch, Literal["high", "medium", "low"], str]:
    """Score candidates and return (best_match, confidence, reason)."""
    scored: list[tuple[float, TickerMatch]] = []
    desc_lower = description_hint.lower()

    for m in matches:
        score = 0.0

        # Prefer EUR-denominated (Scalable is a German broker; EUR listings are typical)
        if m.currency == Currency.EUR:
            score += 2.0

        # Prefer German exchange suffixes
        sym_upper = m.symbol.upper()
        for suffix in _DE_SUFFIXES:
            if sym_upper.endswith(suffix):
                score += 1.5
                break

        # Name similarity to CSV description
        name_lower = (m.name or "").lower()
        if name_lower and desc_lower:
            sim = difflib.SequenceMatcher(None, name_lower, desc_lower).ratio()
            score += sim * 2.0

        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    gap = best_score - second_score
    if gap >= 1.5:
        confidence: Literal["high", "medium", "low"] = "medium"
        reason = f"yfinance Search top match (score gap {gap:.1f}): {best.symbol}"
    else:
        confidence = "low"
        reason = f"yfinance Search ambiguous (score gap {gap:.1f}): {best.symbol}"

    return best, confidence, reason


def _resolve_kind(
    ticker: str,
    company_provider: CompanyDataProvider,
) -> tuple[InstrumentKind | None, str]:
    """Return (InstrumentKind, reason_string) by fetching quoteType cheaply."""
    try:
        qt = company_provider.get_quote_type(ticker)
    except Exception as exc:
        return None, f"get_quote_type error: {exc}"

    if qt is None:
        return None, "quoteType unavailable"

    kind = _QUOTE_TYPE_TO_KIND.get(qt)
    if kind is None:
        return None, f"quoteType={qt!r} not mappable to InstrumentKind"

    return kind, f"quoteType={qt!r} → {kind.value}"
