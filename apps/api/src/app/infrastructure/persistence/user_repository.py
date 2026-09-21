from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.identity import User, UserId
from app.domain.tenancy import TenantId
from app.infrastructure.persistence.models import UserRow


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, user: User) -> None:
        self._session.add(
            UserRow(
                id=user.id.value,
                tenant_id=user.tenant_id.value,
                email=user.email,
                password_hash=user.password_hash,
            )
        )

    def get_by_id(self, user_id: UserId) -> User | None:
        row = self._session.get(UserRow, user_id.value)
        if row is None:
            return None
        return self._to_domain(row)

    def get_by_email(self, email: str) -> User | None:
        row = self._session.scalar(select(UserRow).where(UserRow.email == email))
        if row is None:
            return None
        return self._to_domain(row)

    def any_exist(self) -> bool:
        return self._session.scalar(select(UserRow.id).limit(1)) is not None

    @staticmethod
    def _to_domain(row: UserRow) -> User:
        return User(
            id=UserId(row.id),
            tenant_id=TenantId(row.tenant_id),
            email=row.email,
            password_hash=row.password_hash,
        )
