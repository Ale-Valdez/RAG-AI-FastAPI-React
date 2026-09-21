from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.identity import User, UserId
from app.domain.tenancy import Tenant, TenantId
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.session import to_sqlalchemy_url
from app.infrastructure.persistence.tenant_repository import SqlAlchemyTenantRepository
from app.infrastructure.persistence.user_repository import SqlAlchemyUserRepository


def test_to_sqlalchemy_url_rewrites_postgresql() -> None:
    assert (
        to_sqlalchemy_url("postgresql://app:app@localhost:5432/app")
        == "postgresql+psycopg://app:app@localhost:5432/app"
    )
    assert to_sqlalchemy_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_sqlalchemy_repositories_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        assert isinstance(session, Session)
        tenants = SqlAlchemyTenantRepository(session)
        users = SqlAlchemyUserRepository(session)

        assert tenants.any_exist() is False
        assert users.any_exist() is False

        tenant = Tenant(id=TenantId("t1"), name="Demo")
        user = User(
            id=UserId("u1"),
            tenant_id=TenantId("t1"),
            email="admin@example.com",
            password_hash="hashed:secret",
        )
        tenants.save(tenant)
        users.save(user)
        session.commit()

        assert tenants.any_exist() is True
        assert users.any_exist() is True
        assert tenants.get_by_id(TenantId("t1")) == tenant
        assert users.get_by_id(UserId("u1")) == user
        assert users.get_by_email("admin@example.com") == user
        assert users.get_by_email("missing@example.com") is None
