from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from app.domain.errors import UnauthenticatedError

_MAX_ID_LENGTH = 36


class OidcTokenVerifier(Protocol):
    def verify_access_token(self, token: str) -> dict[str, str]: ...


class _DeferredSigningKey:
    def __init__(self, load: Callable[[], Any]) -> None:
        self._load = load

    def material(self) -> Any:
        return self._load()


def verify_rs256_access_token(
    token: str,
    *,
    issuer: str,
    audience: str,
    signing_key: Any,
) -> dict[str, str]:
    try:
        key = signing_key.material() if isinstance(signing_key, _DeferredSigningKey) else signing_key
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": [], "verify_exp": True},
        )
    except Exception as exc:
        raise UnauthenticatedError("Invalid or expired token") from exc
    return _actor_claims(payload)


class OidcAccessTokenVerifier:
    def __init__(self, *, issuer: str, audience: str, jwks_url: str) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks = PyJWKClient(jwks_url)

    def verify_access_token(self, token: str) -> dict[str, str]:
        return verify_rs256_access_token(
            token,
            issuer=self._issuer,
            audience=self._audience,
            signing_key=_DeferredSigningKey(
                lambda: self._jwks.get_signing_key_from_jwt(token).key
            ),
        )


def _actor_claims(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise UnauthenticatedError("Invalid or expired token")
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    if not _valid_actor_id(user_id) or not _valid_actor_id(tenant_id):
        raise UnauthenticatedError("Invalid or expired token")
    return {"user_id": user_id, "tenant_id": tenant_id}


def _valid_actor_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= _MAX_ID_LENGTH
