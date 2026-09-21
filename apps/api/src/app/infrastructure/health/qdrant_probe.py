from __future__ import annotations

import httpx


class QdrantProbe:
    name = "qdrant"

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")

    async def check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self._url}/readyz")
            return response.status_code == 200
        except Exception:
            return False
