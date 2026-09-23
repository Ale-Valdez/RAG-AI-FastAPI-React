from __future__ import annotations

from typing import Any

from openai import OpenAI


class OpenAIAnswerGenerator:
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self._client = OpenAI(api_key=api_key) if client is None else client
        self._model = model

    def generate(self, question: str, context_texts: list[str]) -> str:
        excerpts = "\n\n".join(context_texts)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Answer the question using only the document excerpts.\n\n"
                        f"Excerpts:\n{excerpts}\n\n"
                        f"Question: {question}"
                    ),
                }
            ],
        )
        content = response.choices[0].message.content
        return content if isinstance(content, str) else ""
