from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ThesisStatus = Literal["intact", "watch", "broken"]
Horizon = Literal["H1", "H2", "H3"]


class ThesisEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    thesis: ThesisStatus
    horizon: Horizon


class ThesisMapDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = 1
    entries: dict[str, ThesisEntry] = Field(default_factory=dict)
