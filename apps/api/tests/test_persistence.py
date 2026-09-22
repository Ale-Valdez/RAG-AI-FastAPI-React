from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.documents import Document, DocumentStatus
from app.domain.identity import User, UserId
from app.domain.tenancy import Tenant, TenantId
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.models import DocumentRow, TenantRow
from app.infrastructure.persistence.session import create_session_factory, session_scope, to_sqlalchemy_url
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


def test_session_scope_commits_and_rolls_back() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    with session_scope(factory) as session:
        session.add(TenantRow(id="t1", name="Demo"))

    with factory() as session:
        assert session.get(TenantRow, "t1") is not None

    with pytest.raises(RuntimeError):
        with session_scope(factory) as session:
            session.add(TenantRow(id="t2", name="Other"))
            raise RuntimeError("fail")

    with factory() as session:
        assert session.get(TenantRow, "t2") is None
        assert session.get(TenantRow, "t1") is not None


def test_document_repository_save_and_tenant_scoped_list() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        documents = SqlAlchemyDocumentRepository(session)
        first = Document(
            id="d1",
            tenant_id=TenantId("t1"),
            filename="a.pdf",
            status=DocumentStatus.PENDING,
        )
        second = Document(
            id="d2",
            tenant_id=TenantId("t1"),
            filename="b.pdf",
            status=DocumentStatus.PENDING,
        )
        other = Document(
            id="d3",
            tenant_id=TenantId("t2"),
            filename="c.pdf",
            status=DocumentStatus.PENDING,
        )
        documents.save(first)
        documents.save(second)
        documents.save(other)
        session.commit()

        listed = documents.list_for_tenant(TenantId("t1"))
        assert [item.id for item in listed] == ["d2", "d1"]
        assert documents.list_for_tenant(TenantId("t2")) == [other]
        assert documents.list_for_tenant(TenantId("t3")) == []


def test_document_repository_update_get_delete_and_count_processing() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        documents = SqlAlchemyDocumentRepository(session)
        document = Document(
            id="d1",
            tenant_id=TenantId("t1"),
            filename="a.pdf",
            status=DocumentStatus.PENDING,
        )
        documents.save(document)
        session.commit()
        created_at = session.get(DocumentRow, "d1").created_at

        document.mark_processing()
        documents.save(document)
        session.commit()

        loaded = documents.get("d1")
        assert loaded is not None
        assert loaded.status is DocumentStatus.PROCESSING
        assert documents.count_processing(TenantId("t1")) == 1
        assert documents.count_processing(TenantId("t2")) == 0

        row = session.get(DocumentRow, "d1")
        assert row.created_at == created_at

        documents.delete("d1")
        session.commit()
        assert documents.get("d1") is None


def test_alembic_upgrade_creates_tenant_and_user_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrated.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "tenants" in inspector.get_table_names()
    assert "users" in inspector.get_table_names()
    assert "documents" in inspector.get_table_names()
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"id", "tenant_id", "email", "password_hash"} <= user_columns
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    assert {"id", "tenant_id", "filename", "status", "created_at"} <= document_columns
    email_unique = any(
        "email" in constraint["column_names"] for constraint in inspector.get_unique_constraints("users")
    )
    email_index = any(
        index.get("unique") and index.get("column_names") == ["email"]
        for index in inspector.get_indexes("users")
    )
    assert email_unique or email_index
