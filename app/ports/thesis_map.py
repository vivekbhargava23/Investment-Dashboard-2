from __future__ import annotations

from typing import Protocol

from app.domain.thesis_map import ThesisMapDocument


class ThesisMapRepository(Protocol):
    def load(self) -> ThesisMapDocument: ...
    def save(self, doc: ThesisMapDocument) -> None: ...
