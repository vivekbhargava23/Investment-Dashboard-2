from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.tax.classification import InstrumentKind


class IsinMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str | None
    name: str
    status: Literal["mapped", "unmapped"]
    last_seen_in_csv: date | None = None
    instrument_kind: InstrumentKind | None = None


class IsinMapDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = 1
    entries: dict[str, IsinMapping] = Field(default_factory=dict)
