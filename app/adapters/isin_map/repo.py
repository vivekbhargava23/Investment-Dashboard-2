from __future__ import annotations

import json
import os
from pathlib import Path

from app.domain.isin_map import IsinMapDocument


def _migrate_v1_to_v2(data: dict[str, object]) -> dict[str, object]:
    """No-op migration: 'ignored' status is additive; only bump version."""
    data["version"] = 2
    return data


class JsonIsinMapRepository:
    SCHEMA_VERSION = 2

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> IsinMapDocument:
        if not self.path.exists():
            return IsinMapDocument()
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version", 1) == 1:
            data = _migrate_v1_to_v2(data)
            doc = IsinMapDocument.model_validate(data)
            self._atomic_write(doc)
            return doc
        return IsinMapDocument.model_validate(data)

    def save(self, doc: IsinMapDocument) -> None:
        self._atomic_write(doc)

    def _atomic_write(self, doc: IsinMapDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc.model_dump(mode="json"), f, indent=2, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
