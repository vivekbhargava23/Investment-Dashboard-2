from __future__ import annotations

from typing import Protocol

from app.domain.catalysts import CatalystsDocument


class CatalystsRepository(Protocol):
    def load(self) -> CatalystsDocument: ...
    def save(self, doc: CatalystsDocument) -> None: ...
