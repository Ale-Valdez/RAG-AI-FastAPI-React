from __future__ import annotations

from typing import Protocol


class AnswerGenerator(Protocol):
    def generate(self, question: str, context_texts: list[str]) -> str: ...
