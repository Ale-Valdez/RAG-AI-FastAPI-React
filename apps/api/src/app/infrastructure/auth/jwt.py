from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.domain.errors import UnauthenticatedError

ACCESS_TOKEN_TTL = timedelta(days=15)


class JwtService:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def create_access_token(self, *, user_id: str, tenant_id: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "exp": now + ACCESS_TOKEN_TTL,
            "iat": now,
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def verify_access_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise UnauthenticatedError("Invalid or expired token") from exc
        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")
        if not isinstance(user_id, str) or not isinstance(tenant_id, str):
            raise UnauthenticatedError("Invalid or expired token")
        if not user_id.strip() or not tenant_id.strip():
            raise UnauthenticatedError("Invalid or expired token")
        return {"user_id": user_id, "tenant_id": tenant_id}
