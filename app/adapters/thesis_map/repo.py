from __future__ import annotations

import json
import os
from pathlib import Path

from app.domain.thesis_map import ThesisMapDocument


class JsonThesisMapRepository:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> ThesisMapDocument:
        if not self.path.exists():
            return ThesisMapDocument()
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        return ThesisMapDocument.model_validate(data)

    def save(self, doc: ThesisMapDocument) -> None:
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
