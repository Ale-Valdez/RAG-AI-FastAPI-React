from __future__ import annotations

from typing import Any

from openai import OpenAI


class OpenAIQueryRewriter:
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self._client = OpenAI(api_key=api_key) if client is None else client
        self._model = model

    def rewrite(self, question: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Rewrite the question as a short document search query. "
                        "Return only the query.\n\n"
                        f"Question: {question}"
                    ),
                }
            ],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty rewrite")
        return content.strip()
