from __future__ import annotations

from typing import Protocol

from app.domain.isin_map import IsinMapDocument


class IsinMapRepository(Protocol):
    def load(self) -> IsinMapDocument: ...
    def save(self, doc: IsinMapDocument) -> None: ...
