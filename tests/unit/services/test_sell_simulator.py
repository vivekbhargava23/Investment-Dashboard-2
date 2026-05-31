# ruff: noqa: E501
"""Unit tests for app.services.sell_simulator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, Position
from app.domain.tax.classification import InstrumentKind
from app.domain.tax.models import FilingStatus, TaxProfile
from app.services.sell_simulator import SellSimulationRequest, simulate_sell

_EUR = Currency.EUR
_USD = Currency.USD
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)

# Use RHM.DE — a EUR-native ticker — so all prices are in EUR and fx_rate=1
_TICKER = "RHM.DE"

_SIM_MAP = IsinMapDocument(entries={
    "ISIN-RHM.DE": IsinMapping(ticker="RHM.DE", name="RHM.DE", status="mapped", instrument_kind=InstrumentKind.AKTIE),
    "ISIN-VUSA.DE": IsinMapping(ticker="VUSA.DE", name="VUSA.DE", status="mapped", instrument_kind=InstrumentKind.AKTIENFONDS),
})


def _eur(v: str) -> Money:
    return Money(amount=Decimal(v), currency=_EUR)


def _zero() -> Money:
    return Money.zero(_EUR)


def _buy(d: str, shares: str, price_eur: str, ticker: str = _TICKER) -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.BUY,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price_eur), currency=_EUR),
        fx_rate_eur=Decimal("1"),
    )


def _sell_tx(d: str, shares: str, price_eur: str, ticker: str = _TICKER) -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.SELL,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price_eur), currency=_EUR),
        fx_rate_eur=Decimal("1"),
    )


def _request(
    shares: str,
    price_eur: str,
    sell_date: str = "2026-05-01",
    ticker: str = _TICKER,
) -> SellSimulationRequest:
    return SellSimulationRequest(
        ticker=ticker,
        shares=Decimal(shares),
        sell_price_native=Money(amount=Decimal(price_eur), currency=_EUR),
        sell_fx_rate_eur=Decimal("1"),
        sell_date=date.fromisoformat(sell_date),
    )


def _stale_live_pos(shares: str) -> LivePosition:
    lot = OpenLot(
        source_transaction_id="t",
        ticker=_TICKER,
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal(shares),
        cost_per_share_native=Money(amount=Decimal("100"), currency=_EUR),
        fx_rate_eur=Decimal("1"),
    )
    pos = Position(
        ticker=_TICKER,
        open_shares=Decimal(shares),
        open_lots=(lot,),
        realised_gain_eur_ytd=_zero(),
        cost_basis_eur=Money(amount=Decimal(shares) * Decimal("100"), currency=_EUR),
    )
    return LivePosition(
        position=pos,
        live_price_native=None,
        live_value_eur=None,
        unrealised_gain_eur=None,
        unrealised_gain_pct=None,
        current_fx_rate=None,
        staleness_reason="price unavailable",
    )


class TestSimulateSellHappyPaths:
    def test_partial_sell_single_lot(self) -> None:
        txs = [_buy("2025-01-01", "12", "100")]
        req = _request("5", "120")
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)

        assert sim.is_valid
        assert len(sim.lot_consumption) == 1
        assert sim.lot_consumption[0].shares_consumed == Decimal("5")
        # Gain = (120 - 100) * 5 = 100
        assert sim.total_realised_gain_eur.amount == Decimal("100")
        assert sim.position_after is not None
        assert sim.position_after.open_shares_after == Decimal("7")

    def test_sell_crossing_two_lots(self) -> None:
        txs = [
            _buy("2025-01-01", "5", "100"),
            _buy("2026-01-01", "5", "110"),
        ]
        req = _request("7", "130")
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)

        assert sim.is_valid
        assert len(sim.lot_consumption) == 2
        assert sim.lot_consumption[0].shares_consumed == Decimal("5")
        assert sim.lot_consumption[1].shares_consumed == Decimal("2")
        # Lot 1: (130-100)*5 = 150; Lot 2: (130-110)*2 = 40; Total = 190
        assert sim.total_realised_gain_eur.amount == Decimal("190")

    def test_big_lot_small_lot_fifo_order(self) -> None:
        """The canonical FIFO test: oldest lot always consumed first."""
        txs = [
            _buy("2025-05-12", "5", "100"),  # 2025 lot
            _buy("2026-04-15", "3", "150"),  # 2026 lot
        ]
        req = _request("6", "130")
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)

        assert sim.is_valid
        assert len(sim.lot_consumption) == 2
        # Lot 1 (2025): 5 shares, gain (130-100)*5 = 150
        assert sim.lot_consumption[0].buy_date == date(2025, 5, 12)
        assert sim.lot_consumption[0].realised_gain_eur.amount == Decimal("150")
        # Lot 2 (2026): 1 share, gain (130-150)*1 = -20
        assert sim.lot_consumption[1].buy_date == date(2026, 4, 15)
        assert sim.lot_consumption[1].realised_gain_eur.amount == Decimal("-20")
        assert sim.total_realised_gain_eur.amount == Decimal("130")

    def test_deterministic_same_input_same_output(self) -> None:
        txs = [_buy("2025-01-01", "10", "100")]
        req = _request("3", "120")
        sim1 = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)
        sim2 = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)
        assert sim1 == sim2

    def test_marginal_tax_populated(self) -> None:
        txs = [_buy("2025-01-01", "10", "100")]
        req = _request("5", "120")
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)
        assert sim.marginal_tax is not None
        assert sim.marginal_tax.marginal_total_tax_owed_eur.amount >= Decimal("0")


class TestSimulateSellValidationErrors:
    def test_no_open_position(self) -> None:
        req = _request("5", "120")
        sim = simulate_sell(req, [], _SINGLE, {})
        assert not sim.is_valid
        assert _TICKER in (sim.validation_error or "")

    def test_over_sell(self) -> None:
        txs = [_buy("2025-01-01", "5", "100")]
        req = _request("10", "120")
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)
        assert not sim.is_valid
        assert sim.validation_error is not None
        # error message should mention the excess
        assert "5" in sim.validation_error or "10" in sim.validation_error


class TestMarginalAllowanceState:
    def test_gain_partially_sheltered_by_allowance(self) -> None:
        """Sell producing €600 gain when €400 allowance remains → €200 taxable → €52.75 tax."""
        # Buy 20 shares at €100. Sell 6 at €200 → gain €600 (consumes €600 of €1000 allowance).
        # 14 shares remain (all at €100 cost). Proposed sell of 6 more at €200:
        # gain = (200-100)*6 = €600. Remaining allowance = €400.
        # Sheltered: €400, taxable: €200 → 26.375% = €52.75
        txs = [
            _buy("2025-01-01", "20", "100"),
            _sell_tx("2026-01-15", "6", "200"),   # gain: (200-100)*6 = €600
        ]
        req = _request("6", "200")  # another €600 gain from remaining 14 shares
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)

        assert sim.is_valid
        mt = sim.marginal_tax
        assert mt is not None
        # marginal_taxable_gain_eur = delta in total_taxable_after_loss_offset (before allowance)
        assert mt.marginal_taxable_gain_eur.amount == Decimal("600")
        # €400 remaining allowance is consumed
        assert mt.marginal_allowance_consumed_eur.amount == Decimal("400")
        # Net taxable after allowance = €200; tax = €200 × 26.375% = €52.75
        assert mt.marginal_total_tax_owed_eur.amount == Decimal("52.75")

    def test_aktien_gain_not_offset_by_general_loss(self) -> None:
        """Aktienfonds losses (general pot) cannot offset Aktie gains (firewall rule)."""
        # VUSA.DE is classified as Aktienfonds (70% Teilfreistellung, general pot)
        # RHM.DE is classified as Aktie (aktien pot)
        # A loss on VUSA.DE feeds the general pot and cannot offset gains on RHM.DE
        txs = [
            _buy("2026-01-01", "10", "100", ticker="VUSA.DE"),
            _sell_tx("2026-02-01", "10", "50", ticker="VUSA.DE"),  # loss: -€500 raw; -350 after Teilfreistellung → general pot
            _buy("2025-01-01", "5", "100"),  # RHM.DE position
        ]
        req = _request("5", "200")  # €500 gain on RHM.DE (Aktie)
        sim = simulate_sell(req, txs, _SINGLE, {}, isin_map=_SIM_MAP)

        assert sim.is_valid
        mt = sim.marginal_tax
        assert mt is not None
        # RHM.DE is an Aktie. The general-pot loss from VUSA.DE cannot offset it.
        # €500 Aktie gain is fully sheltered by the €1000 Sparerpauschbetrag.
        assert mt.marginal_total_tax_owed_eur.amount == Decimal("0")
