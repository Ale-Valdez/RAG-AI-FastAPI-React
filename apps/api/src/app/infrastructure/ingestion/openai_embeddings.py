from __future__ import annotations

from openai import OpenAI


class OpenAIEmbeddingGenerator:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        by_index = {item.index: item.embedding for item in response.data}
        return [list(by_index[index]) for index in range(len(texts))]
