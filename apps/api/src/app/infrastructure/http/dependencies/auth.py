from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.actor import Actor
from app.domain.errors import UnauthenticatedError
from app.infrastructure.auth.jwt import JwtService

_bearer = HTTPBearer(auto_error=False)


def build_require_actor(jwt_service: JwtService) -> Callable[..., Actor]:
    def require_actor(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> Actor:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise UnauthenticatedError("Authentication required")
        claims = jwt_service.verify_access_token(credentials.credentials)
        return Actor(tenant_id=claims["tenant_id"], user_id=claims["user_id"])

    return require_actor
