from __future__ import annotations

from app.application.auth.models import LoginCommand, LoginResult
from app.domain.errors import UnauthenticatedError
from app.domain.ports.auth import PasswordHasher, UserRepository


class Login:
    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def execute(self, command: LoginCommand) -> LoginResult:
        user = self._users.get_by_email(command.email)
        if user is None or not self._password_hasher.verify(
            command.password, user.password_hash
        ):
            raise UnauthenticatedError("Invalid credentials")
        return LoginResult(user_id=user.id.value, tenant_id=user.tenant_id.value)
