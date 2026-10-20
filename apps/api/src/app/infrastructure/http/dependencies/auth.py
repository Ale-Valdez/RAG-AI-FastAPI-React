from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.actor import Actor
from app.domain.errors import UnauthenticatedError
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.auth.oidc import OidcTokenVerifier

_bearer = HTTPBearer(auto_error=False)
_MAX_ID_LENGTH = 36


def build_require_actor(
    jwt_service: JwtService,
    oidc_verifier: OidcTokenVerifier | None = None,
) -> Callable[..., Actor]:
    def require_actor(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> Actor:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise UnauthenticatedError("Authentication required")
        token = credentials.credentials
        algorithm = _unverified_algorithm(token)
        if algorithm == "HS256":
            claims = jwt_service.verify_access_token(token)
        elif algorithm == "RS256" and oidc_verifier is not None:
            claims = oidc_verifier.verify_access_token(token)
        else:
            raise UnauthenticatedError("Invalid or expired token")
        return _actor_from_claims(claims)

    return require_actor


def _unverified_algorithm(token: str) -> str:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise UnauthenticatedError("Invalid or expired token") from exc
    algorithm = header.get("alg")
    if not isinstance(algorithm, str):
        raise UnauthenticatedError("Invalid or expired token")
    return algorithm


def _actor_from_claims(claims: dict[str, Any]) -> Actor:
    user_id = claims.get("user_id")
    tenant_id = claims.get("tenant_id")
    if not _valid_actor_id(user_id) or not _valid_actor_id(tenant_id):
        raise UnauthenticatedError("Invalid or expired token")
    return Actor(tenant_id=tenant_id, user_id=user_id)


def _valid_actor_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= _MAX_ID_LENGTH
