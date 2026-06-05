from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.tax.classification import InstrumentKind


class IsinMapping(BaseModel):
    """Single entry in the ISIN map.

    status values:
    - ``mapped``: ticker is not None; used by the importer to attach to transactions.
    - ``unmapped``: ticker is None; surfaced in the Mappings page for the user to resolve.
    - ``ignored``: ticker is None; rows for this ISIN are skipped by the importer
      with no warning and no counter bump. Reversible via the Mappings page.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str | None
    name: str
    status: Literal["mapped", "unmapped", "ignored"]
    last_seen_in_csv: date | None = None
    instrument_kind: InstrumentKind | None = None


class IsinMapDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = 2
    entries: dict[str, IsinMapping] = Field(default_factory=dict)
