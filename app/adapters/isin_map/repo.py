from __future__ import annotations

import json
import os
from pathlib import Path

from app.domain.isin_map import IsinMapDocument


class JsonIsinMapRepository:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> IsinMapDocument:
        if not self.path.exists():
            return IsinMapDocument()
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        return IsinMapDocument.model_validate(data)

    def save(self, doc: IsinMapDocument) -> None:
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
