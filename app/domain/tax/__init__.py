"""Public surface of the German capital-gains tax engine."""

from app.domain.tax.classification import (
    InstrumentClassificationError,
    InstrumentKind,
    classify_instrument,
)
from app.domain.tax.engine import compute_tax_year_summary
from app.domain.tax.models import (
    FilingStatus,
    LossPotState,
    TaxImpact,
    TaxProfile,
    TaxYearSummary,
)
from app.domain.tax.rates import TAX_RATES_2026, UnsupportedTaxYearError

__all__ = [
    "compute_tax_year_summary",
    "TaxYearSummary",
    "TaxImpact",
    "LossPotState",
    "TaxProfile",
    "InstrumentKind",
    "FilingStatus",
    "InstrumentClassificationError",
    "UnsupportedTaxYearError",
    "classify_instrument",
    "TAX_RATES_2026",
]
