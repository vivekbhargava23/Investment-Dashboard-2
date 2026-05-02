"""
app/core/portfolio.py

Portfolio model: all positions with summary metrics and weight calculation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.core.position import Position


class PortfolioSummary(BaseModel):
    """Snapshot totals across all positions."""

    total_cost_basis: float
    total_current_value: float | None   # None if any position lacks a live price
    total_unrealised_gain: float | None
    total_unrealised_gain_pct: float | None
    position_count: int
    fully_priced: bool                  # True only when every position has a live price


class Portfolio(BaseModel):
    """
    The full portfolio: a named collection of positions.

    weights are computed from current_value when live prices are available,
    falling back to cost-basis weights when any price is missing.
    """

    name: str = Field(default="My Portfolio")
    positions: list[Position] = Field(default_factory=list)

    @model_validator(mode="after")
    def tickers_must_be_unique(self) -> Portfolio:
        tickers = [p.ticker for p in self.positions]
        seen, dupes = set(), []
        for t in tickers:
            if t in seen:
                dupes.append(t)
            seen.add(t)
        if dupes:
            raise ValueError(f"Duplicate tickers in portfolio: {dupes}")
        return self

    # ---------------------------------------------------------------- lookups

    def get_position(self, ticker: str) -> Position | None:
        ticker = ticker.strip().upper()
        return next((p for p in self.positions if p.ticker == ticker), None)

    # ---------------------------------------------------------- totals

    @property
    def total_cost_basis(self) -> float:
        return sum(p.total_cost_basis for p in self.positions)

    @property
    def total_current_value(self) -> float | None:
        """None if any position lacks a live price."""
        if not all(p.has_live_price for p in self.positions):
            return None
        return sum(p.current_value for p in self.positions)  # type: ignore[misc]

    @property
    def total_unrealised_gain(self) -> float | None:
        cv = self.total_current_value
        if cv is None:
            return None
        return cv - self.total_cost_basis

    @property
    def total_unrealised_gain_pct(self) -> float | None:
        """Portfolio-level unrealised gain as a decimal ratio."""
        ug = self.total_unrealised_gain
        if ug is None or self.total_cost_basis == 0:
            return None
        return ug / self.total_cost_basis

    @property
    def fully_priced(self) -> bool:
        return bool(self.positions) and all(p.has_live_price for p in self.positions)

    @property
    def summary(self) -> PortfolioSummary:
        return PortfolioSummary(
            total_cost_basis=self.total_cost_basis,
            total_current_value=self.total_current_value,
            total_unrealised_gain=self.total_unrealised_gain,
            total_unrealised_gain_pct=self.total_unrealised_gain_pct,
            position_count=len(self.positions),
            fully_priced=self.fully_priced,
        )

    # ---------------------------------------------------------- weights

    def weight(self, ticker: str) -> float | None:
        """
        Portfolio weight for a ticker as a decimal ratio (0.25 = 25%).

        Uses current_value when all prices are available,
        falls back to cost-basis weight otherwise.
        Returns None if the ticker is not in the portfolio.
        """
        pos = self.get_position(ticker)
        if pos is None:
            return None

        if self.fully_priced:
            total = self.total_current_value
            numerator = pos.current_value
        else:
            total = self.total_cost_basis
            numerator = pos.total_cost_basis

        if not total:
            return None
        return numerator / total  # type: ignore[operator]

    def weights(self) -> dict[str, float]:
        """
        Weight for every position as a dict keyed by ticker.

        Uses current_value weights when fully priced, cost-basis weights otherwise.
        """
        if self.fully_priced:
            total = self.total_current_value or 0.0
            return {
                p.ticker: (p.current_value or 0.0) / total
                for p in self.positions
            }
        total = self.total_cost_basis or 0.0
        return {
            p.ticker: p.total_cost_basis / total
            for p in self.positions
        }
