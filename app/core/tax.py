"""
app/core/tax.py

German capital gains tax engine.

Rules hardcoded per German retail investor law:
  - FIFO lot disposal (enforced in lot.py, not here)
  - Abgeltungsteuer: 26.375% (25% + 5.5% Solidaritätszuschlag)
  - Sparerpauschbetrag: €1,000 annual tax-free allowance (default; configurable)
  - Loss pots: equity losses carry forward indefinitely, absorb gains before tax
  - Kirchensteuer: not calculated (user-specific, varies by German state)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.lot import FifoResult

ABGELTUNGSTEUER_RATE: float = 0.26375  # 25% + 5.5% solidarity surcharge
DEFAULT_SPARERPAUSCHBETRAG: float = 1_000.00


class TaxYear(BaseModel):
    """
    Running German tax state for one calendar year.

    Update incrementally as trades are realised:
      - Call apply_disposal() for each completed FIFO disposal.
      - Read tax_owed to see current liability.
    """

    year: int
    sparerpauschbetrag: float = Field(
        default=DEFAULT_SPARERPAUSCHBETRAG,
        gt=0,
        description="Annual tax-free allowance in EUR",
    )
    allowance_used: float = Field(default=0.0, ge=0)
    realised_gains: float = Field(default=0.0)    # gross gains before allowance/loss pot
    realised_losses: float = Field(default=0.0)   # gross losses (stored as positive number)
    loss_pot_carried_in: float = Field(default=0.0, ge=0)  # losses from prior years

    # ---------------------------------------------------------- derived

    @property
    def allowance_remaining(self) -> float:
        return max(0.0, self.sparerpauschbetrag - self.allowance_used)

    @property
    def net_gain(self) -> float:
        """Gains minus in-year losses — can be negative."""
        return self.realised_gains - self.realised_losses

    @property
    def taxable_gain(self) -> float:
        """
        Gain subject to Abgeltungsteuer.

        Formula: net_gain - loss_pot_carried_in - allowance_used, floored at 0.

        Each input is already cumulative state maintained elsewhere:
          - net_gain is realised_gains - realised_losses for the year
          - loss_pot_carried_in is set at year start, not mutated by disposals
          - allowance_used is incremented by apply_disposal as gains are realised

        Therefore each is subtracted exactly once.
        """
        return max(0.0, self.net_gain - self.loss_pot_carried_in - self.allowance_used)

    @property
    def tax_owed(self) -> float:
        """Abgeltungsteuer due on taxable_gain."""
        return round(self.taxable_gain * ABGELTUNGSTEUER_RATE, 2)

    @property
    def harvest_headroom(self) -> float:
        """
        Additional gain that can still be realised tax-free this year.

        Counts remaining Sparerpauschbetrag and any offsetting loss pot.
        Useful for November tax-gain harvesting decisions.
        """
        return self.allowance_remaining + self.loss_pot_remaining

    @property
    def loss_pot_remaining(self) -> float:
        """Unabsorbed loss pot after netting against this year's gains."""
        absorbed = max(0.0, min(self.loss_pot_carried_in, self.net_gain))
        return max(0.0, self.loss_pot_carried_in - absorbed)

    # ---------------------------------------------------------- mutations

    def apply_disposal(self, result: FifoResult) -> None:
        """
        Record a completed FIFO disposal into the running tax state.

        Gains and losses are tracked separately — German law does not
        allow netting within the same trade for Sparerpauschbetrag purposes.
        """
        if result.total_gain >= 0:
            self.realised_gains += result.total_gain
            # Consume allowance against gains only
            consumed = min(self.allowance_remaining, result.total_gain)
            self.allowance_used += consumed
        else:
            self.realised_losses += abs(result.total_gain)


class TaxEstimate(BaseModel):
    """
    Hypothetical tax impact of a proposed disposal — without mutating TaxYear.
    Used by the pre-trade checklist and FIFO simulator UI.
    """

    proposed_gain: float
    allowance_remaining_before: float
    loss_pot_before: float
    allowance_consumed: float
    loss_pot_consumed: float
    taxable_gain: float
    tax_owed: float
    allowance_remaining_after: float
    loss_pot_remaining_after: float


def recompute_tax_year_from_realised_gains_eur(
    year: int,
    realised_gains_eur: list[float],
    sparerpauschbetrag: float = DEFAULT_SPARERPAUSCHBETRAG,
    loss_pot_carried_in: float = 0.0,
) -> TaxYear:
    """
    Build a fresh TaxYear by replaying every realised gain/loss for the year.

    Args:
        year: Calendar year (e.g. 2026).
        realised_gains_eur: One signed EUR figure per disposal — positive = gain,
            negative = loss. Sells from prior years must be filtered out by
            the caller before calling this.
        sparerpauschbetrag: Annual allowance, default €1,000.
        loss_pot_carried_in: Unused losses from previous years.

    Returns:
        A fully populated TaxYear with allowance_used, realised_gains,
        realised_losses correctly aggregated.

    This is the canonical way to derive tax state — never mutate a TaxYear
    incrementally from UI code, always recompute via this function.
    """
    gains = sum(g for g in realised_gains_eur if g > 0)
    losses = sum(-g for g in realised_gains_eur if g < 0)

    # Allowance is consumed against gross gains (German law)
    allowance_used = min(sparerpauschbetrag, gains)

    return TaxYear(
        year=year,
        sparerpauschbetrag=sparerpauschbetrag,
        allowance_used=allowance_used,
        realised_gains=gains,
        realised_losses=losses,
        loss_pot_carried_in=loss_pot_carried_in,
    )


def estimate_disposal_tax(tax_year: TaxYear, proposed_gain: float) -> TaxEstimate:
    """
    Calculate the tax impact of a proposed gain without mutating tax_year.

    Args:
        tax_year:      Current running tax state for the year.
        proposed_gain: Gain (positive) or loss (negative) from the proposed trade.

    Returns:
        TaxEstimate showing exactly what tax would be owed and what is consumed.
    """
    allowance_before = tax_year.allowance_remaining
    loss_pot_before = tax_year.loss_pot_remaining

    if proposed_gain <= 0:
        # A loss adds to loss pot, no tax, allowance untouched
        return TaxEstimate(
            proposed_gain=proposed_gain,
            allowance_remaining_before=allowance_before,
            loss_pot_before=loss_pot_before,
            allowance_consumed=0.0,
            loss_pot_consumed=0.0,
            taxable_gain=0.0,
            tax_owed=0.0,
            allowance_remaining_after=allowance_before,
            loss_pot_remaining_after=loss_pot_before + abs(proposed_gain),
        )

    remaining = proposed_gain

    # 1. Absorb with loss pot first
    loss_pot_consumed = min(loss_pot_before, remaining)
    remaining -= loss_pot_consumed

    # 2. Absorb with Sparerpauschbetrag
    allowance_consumed = min(allowance_before, remaining)
    remaining -= allowance_consumed

    taxable = max(0.0, remaining)
    tax = round(taxable * ABGELTUNGSTEUER_RATE, 2)

    return TaxEstimate(
        proposed_gain=proposed_gain,
        allowance_remaining_before=allowance_before,
        loss_pot_before=loss_pot_before,
        allowance_consumed=allowance_consumed,
        loss_pot_consumed=loss_pot_consumed,
        taxable_gain=taxable,
        tax_owed=tax,
        allowance_remaining_after=allowance_before - allowance_consumed,
        loss_pot_remaining_after=loss_pot_before - loss_pot_consumed,
    )
