"""JSON-backed adapter for the TaxProfileRepository port."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.ports.tax_profile_repo import TaxProfileDocument


class LegacyTaxProfileError(Exception):
    """Raised when tax_profile.json contains an unsupported version field.

    Run a manual migration: edit the file's "version" field to 1 and validate
    the carryforward values against your last Steuerbescheid.
    """

    def __init__(self, path: Path, found_version: int) -> None:
        self.path = path
        self.found_version = found_version
        super().__init__(
            f"{path} has version={found_version}; only version=1 is supported. "
            "Edit the file manually and set \"version\": 1."
        )


class JsonTaxProfileRepository:
    """Reads and writes tax_profile.json using the TaxProfileDocument schema."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> TaxProfileDocument:
        if not self.path.exists():
            return TaxProfileDocument()

        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Cannot read {self.path}: {exc}") from exc

        version = data.get("version", 1)
        if version != self.SCHEMA_VERSION:
            raise LegacyTaxProfileError(self.path, version)

        try:
            return TaxProfileDocument.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Invalid tax profile at {self.path}: {exc}") from exc

    def save(self, doc: TaxProfileDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc.model_dump(mode="json"), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
