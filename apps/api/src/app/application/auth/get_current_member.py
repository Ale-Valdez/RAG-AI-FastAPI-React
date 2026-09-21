from __future__ import annotations

from app.application.auth.models import CurrentMember
from app.domain.actor import Actor
from app.domain.errors import UnauthenticatedError
from app.domain.identity import UserId
from app.domain.ports.auth import UserRepository
from app.domain.tenancy import TenantId, assert_same_tenant


class GetCurrentMember:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, actor: Actor) -> CurrentMember:
        user = self._users.get_by_id(UserId(actor.user_id))
        if user is None:
            raise UnauthenticatedError("User is not authenticated")
        assert_same_tenant(user.tenant_id, TenantId(actor.tenant_id))
        return CurrentMember(
            user_id=user.id.value,
            tenant_id=user.tenant_id.value,
            email=user.email,
        )
