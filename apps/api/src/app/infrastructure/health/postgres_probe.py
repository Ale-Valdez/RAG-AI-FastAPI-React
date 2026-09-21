from __future__ import annotations

import asyncio
from urllib.parse import urlparse


class PostgresProbe:
    name = "postgres"

    def __init__(self, url: str) -> None:
        normalized = url.replace("postgresql+psycopg://", "postgresql://")
        parsed = urlparse(normalized)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 5432

    async def check(self) -> bool:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=2,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False
