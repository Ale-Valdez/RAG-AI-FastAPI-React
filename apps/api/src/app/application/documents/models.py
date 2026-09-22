from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UploadDocumentCommand:
    filename: str
    content: bytes
