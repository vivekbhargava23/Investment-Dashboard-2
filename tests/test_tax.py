"""
tests/test_tax.py

German tax engine tests with independently verified expected values.
All EUR figures calculated by hand before writing assertions.
"""

import pytest
from datetime import date

from app.core.lot import OpenLot, dispose_fifo
from app.core.tax import (
    TaxYear,
    TaxEstimate,
    estimate_disposal_tax,
    recompute_tax_year_from_realised_gains_eur,
    ABGELTUNGSTEUER_RATE,
    DEFAULT_SPARERPAUSCHBETRAG,
)


# ── TaxYear: initial state ────────────────────────────────────────────────────

class TestTaxYearDefaults:
    def test_default_allowance(self):
        ty = TaxYear(year=2026)
        assert ty.sparerpauschbetrag == pytest.approx(DEFAULT_SPARERPAUSCHBETRAG)

    def test_allowance_fully_remaining_at_start(self):
        ty = TaxYear(year=2026)
        assert ty.allowance_remaining == pytest.approx(1_000.0)

    def test_no_tax_owed_at_start(self):
        ty = TaxYear(year=2026)
        assert ty.tax_owed == pytest.approx(0.0)

    def test_harvest_headroom_equals_allowance_at_start(self):
        ty = TaxYear(year=2026)
        assert ty.harvest_headroom == pytest.approx(1_000.0)


# ── estimate_disposal_tax: gain within allowance ──────────────────────────────

class TestEstimateGainWithinAllowance:
    def test_gain_fully_within_allowance(self):
        ty = TaxYear(year=2026)
        est = estimate_disposal_tax(ty, proposed_gain=600.0)

        assert est.taxable_gain == pytest.approx(0.0)
        assert est.tax_owed == pytest.approx(0.0)
        assert est.allowance_consumed == pytest.approx(600.0)
        assert est.allowance_remaining_after == pytest.approx(400.0)
        assert est.loss_pot_consumed == pytest.approx(0.0)

    def test_gain_exactly_equals_allowance(self):
        ty = TaxYear(year=2026)
        est = estimate_disposal_tax(ty, proposed_gain=1_000.0)

        assert est.taxable_gain == pytest.approx(0.0)
        assert est.tax_owed == pytest.approx(0.0)
        assert est.allowance_remaining_after == pytest.approx(0.0)


# ── estimate_disposal_tax: gain exceeds allowance ────────────────────────────

class TestEstimateGainExceedsAllowance:
    def test_gain_of_1400_taxable_portion_400(self):
        # 1400 - 1000 allowance = 400 taxable → 400 × 0.26375 = 105.50
        ty = TaxYear(year=2026)
        est = estimate_disposal_tax(ty, proposed_gain=1_400.0)

        assert est.allowance_consumed == pytest.approx(1_000.0)
        assert est.taxable_gain == pytest.approx(400.0)
        assert est.tax_owed == pytest.approx(round(400.0 * ABGELTUNGSTEUER_RATE, 2))
        assert est.allowance_remaining_after == pytest.approx(0.0)

    def test_partial_allowance_remaining(self):
        # 400 allowance already used; 700 remaining; gain of 1000 → taxable 300
        ty = TaxYear(year=2026, allowance_used=300.0)
        est = estimate_disposal_tax(ty, proposed_gain=1_000.0)

        assert est.allowance_consumed == pytest.approx(700.0)
        assert est.taxable_gain == pytest.approx(300.0)
        assert est.tax_owed == pytest.approx(round(300.0 * ABGELTUNGSTEUER_RATE, 2))

    def test_no_allowance_remaining_full_gain_taxable(self):
        ty = TaxYear(year=2026, allowance_used=1_000.0)
        est = estimate_disposal_tax(ty, proposed_gain=500.0)

        assert est.allowance_consumed == pytest.approx(0.0)
        assert est.taxable_gain == pytest.approx(500.0)
        assert est.tax_owed == pytest.approx(round(500.0 * ABGELTUNGSTEUER_RATE, 2))


# ── estimate_disposal_tax: loss pot absorption ────────────────────────────────

class TestEstimateLossPotAbsorption:
    def test_loss_pot_absorbs_gain_fully(self):
        # loss pot 800, gain 600 → pot absorbs all, allowance untouched
        ty = TaxYear(year=2026, loss_pot_carried_in=800.0)
        est = estimate_disposal_tax(ty, proposed_gain=600.0)

        assert est.loss_pot_consumed == pytest.approx(600.0)
        assert est.allowance_consumed == pytest.approx(0.0)
        assert est.taxable_gain == pytest.approx(0.0)
        assert est.tax_owed == pytest.approx(0.0)
        assert est.loss_pot_remaining_after == pytest.approx(200.0)

    def test_loss_pot_partially_absorbs_then_allowance_covers_rest(self):
        # loss pot 500, gain 800 → pot 500 + allowance 300 → taxable 0
        ty = TaxYear(year=2026, loss_pot_carried_in=500.0)
        est = estimate_disposal_tax(ty, proposed_gain=800.0)

        assert est.loss_pot_consumed == pytest.approx(500.0)
        assert est.allowance_consumed == pytest.approx(300.0)
        assert est.taxable_gain == pytest.approx(0.0)
        assert est.tax_owed == pytest.approx(0.0)

    def test_loss_pot_and_allowance_insufficient(self):
        # loss pot 200, allowance 1000, gain 1500 → taxable 300
        ty = TaxYear(year=2026, loss_pot_carried_in=200.0)
        est = estimate_disposal_tax(ty, proposed_gain=1_500.0)

        assert est.loss_pot_consumed == pytest.approx(200.0)
        assert est.allowance_consumed == pytest.approx(1_000.0)
        assert est.taxable_gain == pytest.approx(300.0)
        assert est.tax_owed == pytest.approx(round(300.0 * ABGELTUNGSTEUER_RATE, 2))


# ── estimate_disposal_tax: proposed loss ─────────────────────────────────────

class TestEstimateProposedLoss:
    def test_loss_produces_no_tax(self):
        ty = TaxYear(year=2026)
        est = estimate_disposal_tax(ty, proposed_gain=-400.0)

        assert est.tax_owed == pytest.approx(0.0)
        assert est.taxable_gain == pytest.approx(0.0)
        assert est.allowance_consumed == pytest.approx(0.0)

    def test_loss_increases_loss_pot(self):
        ty = TaxYear(year=2026, loss_pot_carried_in=200.0)
        est = estimate_disposal_tax(ty, proposed_gain=-300.0)

        assert est.loss_pot_remaining_after == pytest.approx(500.0)

    def test_allowance_unchanged_on_loss(self):
        ty = TaxYear(year=2026)
        est = estimate_disposal_tax(ty, proposed_gain=-500.0)

        assert est.allowance_remaining_after == pytest.approx(1_000.0)


# ── TaxYear.apply_disposal: mutation tests ────────────────────────────────────

class TestApplyDisposal:
    def _nvda_disposal(self, purchase_price: float, sell_price: float, shares: float) -> object:
        lot = OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1),
                  purchase_price=purchase_price, shares=shares)
        return dispose_fifo([lot], shares_to_sell=shares, sell_price=sell_price)

    def test_gain_updates_realised_gains_and_allowance(self):
        ty = TaxYear(year=2026)
        result = self._nvda_disposal(purchase_price=120.0, sell_price=150.0, shares=5.0)
        # gain = 5 × (150 - 120) = 150
        ty.apply_disposal(result)

        assert ty.realised_gains == pytest.approx(150.0)
        assert ty.allowance_used == pytest.approx(150.0)
        assert ty.tax_owed == pytest.approx(0.0)

    def test_loss_updates_realised_losses_not_allowance(self):
        ty = TaxYear(year=2026)
        result = self._nvda_disposal(purchase_price=150.0, sell_price=120.0, shares=5.0)
        # loss = 5 × (120 - 150) = -150
        ty.apply_disposal(result)

        assert ty.realised_losses == pytest.approx(150.0)
        assert ty.allowance_used == pytest.approx(0.0)

    def test_multiple_disposals_accumulate(self):
        ty = TaxYear(year=2026)
        # First disposal: gain 300
        r1 = self._nvda_disposal(purchase_price=100.0, sell_price=160.0, shares=5.0)
        ty.apply_disposal(r1)
        # Second disposal: gain 500
        r2 = self._nvda_disposal(purchase_price=100.0, sell_price=200.0, shares=5.0)
        ty.apply_disposal(r2)

        # Total gain 800, all within allowance
        assert ty.realised_gains == pytest.approx(800.0)
        assert ty.allowance_used == pytest.approx(800.0)
        assert ty.tax_owed == pytest.approx(0.0)
        assert ty.harvest_headroom == pytest.approx(200.0)

    def test_gain_exceeding_allowance_creates_tax(self):
        ty = TaxYear(year=2026)
        r = self._nvda_disposal(purchase_price=100.0, sell_price=400.0, shares=5.0)
        # gain = 5 × 300 = 1500; taxable = 1500 - 1000 = 500
        ty.apply_disposal(r)

        assert ty.realised_gains == pytest.approx(1_500.0)
        assert ty.allowance_used == pytest.approx(1_000.0)
        assert ty.taxable_gain == pytest.approx(500.0)
        assert ty.tax_owed == pytest.approx(round(500.0 * ABGELTUNGSTEUER_RATE, 2))


# ── TaxYear: harvest headroom ─────────────────────────────────────────────────

class TestHarvestHeadroom:
    def test_full_headroom_at_start(self):
        ty = TaxYear(year=2026)
        assert ty.harvest_headroom == pytest.approx(1_000.0)

    def test_headroom_reduced_after_gain(self):
        ty = TaxYear(year=2026, allowance_used=600.0)
        assert ty.harvest_headroom == pytest.approx(400.0)

    def test_headroom_includes_loss_pot(self):
        # 400 allowance remaining + 300 loss pot = 700 headroom
        ty = TaxYear(year=2026, allowance_used=600.0, loss_pot_carried_in=300.0)
        assert ty.harvest_headroom == pytest.approx(700.0)

    def test_no_headroom_when_both_exhausted(self):
        ty = TaxYear(year=2026, allowance_used=1_000.0, realised_gains=1_500.0)
        assert ty.harvest_headroom == pytest.approx(0.0)


# ── TaxYear: loss pot carry-forward mechanics ─────────────────────────────────

class TestLossPotCarryForward:
    def test_loss_pot_remaining_when_no_gains(self):
        ty = TaxYear(year=2026, loss_pot_carried_in=500.0)
        assert ty.loss_pot_remaining == pytest.approx(500.0)

    def test_loss_pot_partially_absorbed_by_gains(self):
        # gain 300, loss pot 500 → 200 remains
        ty = TaxYear(year=2026, loss_pot_carried_in=500.0, realised_gains=300.0)
        assert ty.loss_pot_remaining == pytest.approx(200.0)

    def test_loss_pot_fully_absorbed(self):
        ty = TaxYear(year=2026, loss_pot_carried_in=300.0, realised_gains=500.0)
        assert ty.loss_pot_remaining == pytest.approx(0.0)


# ── recompute_tax_year_from_realised_gains_eur ────────────────────────────────

class TestRecomputeTaxYear:
    def test_recompute_with_no_disposals_returns_empty_year(self):
        ty = recompute_tax_year_from_realised_gains_eur(year=2026, realised_gains_eur=[])
        assert ty.realised_gains == pytest.approx(0.0)
        assert ty.realised_losses == pytest.approx(0.0)
        assert ty.allowance_used == pytest.approx(0.0)
        assert ty.tax_owed == pytest.approx(0.0)

    def test_recompute_with_only_gains_consumes_allowance_correctly(self):
        # gains €1,500 — allowance caps at €1,000 → taxable €500
        ty = recompute_tax_year_from_realised_gains_eur(
            year=2026, realised_gains_eur=[800.0, 700.0]
        )
        assert ty.realised_gains == pytest.approx(1_500.0)
        assert ty.realised_losses == pytest.approx(0.0)
        assert ty.allowance_used == pytest.approx(1_000.0)
        assert ty.taxable_gain == pytest.approx(500.0)

    def test_recompute_with_only_losses_keeps_allowance_full(self):
        ty = recompute_tax_year_from_realised_gains_eur(
            year=2026, realised_gains_eur=[-300.0, -500.0]
        )
        assert ty.realised_gains == pytest.approx(0.0)
        assert ty.realised_losses == pytest.approx(800.0)
        assert ty.allowance_used == pytest.approx(0.0)
        assert ty.tax_owed == pytest.approx(0.0)

    def test_recompute_mixed_gains_losses_aggregates_separately(self):
        # gains 500+800=1300, losses 300 → net 1000; allowance_used=min(1000,1300)=1000
        ty = recompute_tax_year_from_realised_gains_eur(
            year=2026, realised_gains_eur=[500.0, 800.0, -300.0]
        )
        assert ty.realised_gains == pytest.approx(1_300.0)
        assert ty.realised_losses == pytest.approx(300.0)
        assert ty.allowance_used == pytest.approx(1_000.0)

    def test_recompute_idempotent_when_called_twice(self):
        gains = [400.0, -150.0, 900.0]
        ty1 = recompute_tax_year_from_realised_gains_eur(year=2026, realised_gains_eur=gains)
        ty2 = recompute_tax_year_from_realised_gains_eur(year=2026, realised_gains_eur=gains)
        assert ty1.realised_gains == pytest.approx(ty2.realised_gains)
        assert ty1.realised_losses == pytest.approx(ty2.realised_losses)
        assert ty1.allowance_used == pytest.approx(ty2.allowance_used)
        assert ty1.taxable_gain == pytest.approx(ty2.taxable_gain)

    def test_recompute_caps_allowance_at_total_gains_when_gains_below_1000(self):
        # gains €600 — allowance can only consume €600, not the full €1,000
        ty = recompute_tax_year_from_realised_gains_eur(
            year=2026, realised_gains_eur=[600.0]
        )
        assert ty.allowance_used == pytest.approx(600.0)
        assert ty.taxable_gain == pytest.approx(0.0)


# ── TaxYear.taxable_gain: direct formula tests ────────────────────────────────

class TestTaxableGainFormula:
    def test_taxable_gain_zero_when_gains_under_allowance(self):
        # €600 gain, €600 allowance consumed → taxable = 0
        ty = TaxYear(year=2026, realised_gains=600.0, allowance_used=600.0)
        assert ty.taxable_gain == pytest.approx(0.0)

    def test_taxable_gain_excludes_consumed_allowance(self):
        # €1,500 gain, €1,000 allowance fully used → taxable = €500
        ty = TaxYear(year=2026, realised_gains=1_500.0, allowance_used=1_000.0)
        assert ty.taxable_gain == pytest.approx(500.0)

    def test_taxable_gain_with_loss_pot_carried_in(self):
        # €2,000 gain, €500 loss pot, €1,000 allowance → taxable = €500
        ty = TaxYear(
            year=2026,
            realised_gains=2_000.0,
            allowance_used=1_000.0,
            loss_pot_carried_in=500.0,
        )
        assert ty.taxable_gain == pytest.approx(500.0)

    def test_taxable_gain_negative_clamps_to_zero(self):
        # losses exceed gains → net_gain negative → taxable = 0
        ty = TaxYear(year=2026, realised_gains=200.0, realised_losses=500.0)
        assert ty.taxable_gain == pytest.approx(0.0)

    def test_apply_disposal_then_taxable_gain_consistency(self):
        # Replay: gain 800, gain 900, loss 400 → verify taxable at each step
        ty = TaxYear(year=2026)

        # Step 1: gain €800 — within allowance
        r1 = dispose_fifo(
            [OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1),
                 purchase_price=100.0, shares=8.0)],
            shares_to_sell=8.0, sell_price=200.0,
        )
        ty.apply_disposal(r1)
        # realised_gains=800, allowance_used=800; taxable = max(0, 800-0-800) = 0
        assert ty.taxable_gain == pytest.approx(0.0)

        # Step 2: gain €900 — allowance only has €200 left
        r2 = dispose_fifo(
            [OpenLot(ticker="NVDA", purchase_date=date(2025, 2, 1),
                 purchase_price=100.0, shares=9.0)],
            shares_to_sell=9.0, sell_price=200.0,
        )
        ty.apply_disposal(r2)
        # realised_gains=1700, allowance_used=1000; taxable = max(0, 1700-0-1000) = 700
        assert ty.taxable_gain == pytest.approx(700.0)

        # Step 3: loss €400 — reduces net_gain, does not touch allowance
        r3 = dispose_fifo(
            [OpenLot(ticker="NVDA", purchase_date=date(2025, 3, 1),
                 purchase_price=200.0, shares=4.0)],
            shares_to_sell=4.0, sell_price=100.0,
        )
        ty.apply_disposal(r3)
        # net_gain = 1700-400 = 1300; taxable = max(0, 1300-0-1000) = 300
        assert ty.taxable_gain == pytest.approx(300.0)
        assert ty.tax_owed == pytest.approx(round(300.0 * ABGELTUNGSTEUER_RATE, 2))
