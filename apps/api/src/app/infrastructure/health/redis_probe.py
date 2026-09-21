from __future__ import annotations

from redis.asyncio import Redis


class RedisProbe:
    name = "redis"

    def __init__(self, url: str) -> None:
        self._url = url

    async def check(self) -> bool:
        client = Redis.from_url(self._url)
        try:
            return bool(await client.ping())
        except Exception:
            return False
        finally:
            await client.aclose()
