from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.application.documents.process_document import ProcessOutcome
from app.bootstrap.create_app import create_app
from app.bootstrap.worker import SessionBoundProcessDocument
from app.cli import main
from app.domain.actor import Actor
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.config.settings import Settings
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.models import (
    ConversationRow,
    DocumentRow,
    MessageRow,
    UserRow,
)
from app.infrastructure.persistence.session import session_scope, to_sqlalchemy_url
from app.infrastructure.persistence.user_repository import SqlAlchemyUserRepository

_TENANT_A = "tenant-a"
_TENANT_B = "tenant-b"
_CREATED = datetime(2026, 1, 1, tzinfo=UTC)
_JWT_SECRET = "test-secret-key-at-least-32-bytes!!"


@pytest.fixture(scope="module")
def rls_database() -> Iterator[tuple[Engine, str]]:
    raw = os.environ.get("RLS_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("RLS_TEST_DATABASE_URL is unset")

    from sqlalchemy.engine.url import make_url

    url = make_url(raw)
    admin = create_engine(
        to_sqlalchemy_url(url.render_as_string(hide_password=False)),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    scratch = f"rls_{uuid4().hex[:12]}"
    created = False
    test_engine: Engine | None = None
    previous = os.environ.get("DATABASE_URL")
    try:
        try:
            with admin.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            pytest.skip(f"RLS_TEST_DATABASE_URL does not connect: {exc}")

        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{scratch}"'))
        created = True

        scratch_url = url.set(database=scratch).render_as_string(hide_password=False)
        os.environ["DATABASE_URL"] = scratch_url
        api_root = Path(__file__).resolve().parents[1]
        config = Config(str(api_root / "alembic.ini"))
        config.set_main_option("script_location", str(api_root / "alembic"))
        command.upgrade(config, "head")
        test_engine = create_engine(
            to_sqlalchemy_url(scratch_url),
            pool_size=2,
            max_overflow=0,
        )
        yield test_engine, scratch_url
    finally:
        if test_engine is not None:
            test_engine.dispose()
        if created:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        admin.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
def db(rls_database: tuple[Engine, str]) -> Iterator[tuple[Engine, str]]:
    engine, url = rls_database
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE TABLE messages, conversations, documents, users, tenants")
        )
    yield engine, url


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _add_document(session: Session, document_id: str, tenant_id: str, filename: str) -> None:
    session.add(
        DocumentRow(
            id=document_id,
            tenant_id=tenant_id,
            filename=filename,
            status="pending",
            created_at=_CREATED,
        )
    )


def test_missed_document_filter_returns_only_session_tenant(db: tuple[Engine, str]) -> None:
    engine, _url = db
    factory = _factory(engine)
    with factory() as session:
        _add_document(session, "doc-a", _TENANT_A, "a.pdf")
        _add_document(session, "doc-b", _TENANT_B, "b.pdf")
        session.commit()

    with session_scope(factory, _TENANT_A) as session:
        rows = session.scalars(text("SELECT tenant_id FROM documents")).all()

    assert set(rows) == {_TENANT_A}


def test_unset_tenant_returns_no_document_rows(db: tuple[Engine, str]) -> None:
    engine, _url = db
    factory = _factory(engine)
    with factory() as session:
        _add_document(session, "doc-a", _TENANT_A, "a.pdf")
        _add_document(session, "doc-b", _TENANT_B, "b.pdf")
        session.commit()

    with session_scope(factory) as session:
        assert session.scalar(text("SELECT current_user")) == "app_rls"
        rows = session.scalars(text("SELECT id FROM documents")).all()

    assert rows == []


def test_cross_tenant_document_insert_rolls_back(db: tuple[Engine, str]) -> None:
    engine, _url = db
    factory = _factory(engine)
    with session_scope(factory, _TENANT_A) as session:
        session.execute(
            text(
                "INSERT INTO documents (id, tenant_id, filename, status, created_at) "
                "VALUES (:id, :tenant_id, :filename, :status, :created_at)"
            ),
            {
                "id": "doc-own",
                "tenant_id": _TENANT_A,
                "filename": "own.pdf",
                "status": "pending",
                "created_at": _CREATED,
            },
        )

    with pytest.raises(SQLAlchemyError, match="row-level security"):
        with session_scope(factory, _TENANT_A) as session:
            session.execute(
                text(
                    "INSERT INTO documents (id, tenant_id, filename, status, created_at) "
                    "VALUES (:id, :tenant_id, :filename, :status, :created_at)"
                ),
                {
                    "id": "doc-cross",
                    "tenant_id": _TENANT_B,
                    "filename": "cross.pdf",
                    "status": "pending",
                    "created_at": _CREATED,
                },
            )

    with engine.connect() as conn:
        own = conn.scalar(text("SELECT id FROM documents WHERE id = 'doc-own'"))
        cross = conn.scalar(text("SELECT id FROM documents WHERE id = 'doc-cross'"))
    assert own == "doc-own"
    assert cross is None


def test_own_update_persists_and_cross_tenant_update_and_delete_do_not(
    db: tuple[Engine, str],
) -> None:
    engine, _url = db
    factory = _factory(engine)
    with factory() as session:
        _add_document(session, "doc-a", _TENANT_A, "a.pdf")
        _add_document(session, "doc-a-del", _TENANT_A, "delete-me.pdf")
        _add_document(session, "doc-b", _TENANT_B, "b.pdf")
        session.commit()

    with session_scope(factory, _TENANT_A) as session:
        updated = session.execute(
            text("UPDATE documents SET filename = 'renamed.pdf' WHERE id = 'doc-a'")
        )
        deleted = session.execute(text("DELETE FROM documents WHERE id = 'doc-a-del'"))
        missed_update = session.execute(
            text("UPDATE documents SET filename = 'hacked.pdf' WHERE id = 'doc-b'")
        )
        missed_delete = session.execute(text("DELETE FROM documents WHERE id = 'doc-b'"))
        assert updated.rowcount == 1
        assert deleted.rowcount == 1
        assert missed_update.rowcount == 0
        assert missed_delete.rowcount == 0

    with pytest.raises(SQLAlchemyError, match="row-level security"):
        with session_scope(factory, _TENANT_A) as session:
            session.execute(
                text("UPDATE documents SET tenant_id = :tenant_id WHERE id = 'doc-a'"),
                {"tenant_id": _TENANT_B},
            )

    with engine.connect() as conn:
        renamed = conn.scalar(text("SELECT filename FROM documents WHERE id = 'doc-a'"))
        owner = conn.scalar(text("SELECT tenant_id FROM documents WHERE id = 'doc-a'"))
        removed = conn.scalar(text("SELECT id FROM documents WHERE id = 'doc-a-del'"))
        other = conn.scalar(text("SELECT filename FROM documents WHERE id = 'doc-b'"))
    assert renamed == "renamed.pdf"
    assert owner == _TENANT_A
    assert removed is None
    assert other == "b.pdf"


def test_chat_tables_hide_other_tenant_and_reject_writes(db: tuple[Engine, str]) -> None:
    engine, _url = db
    factory = _factory(engine)
    with factory() as session:
        session.add(
            ConversationRow(
                id="conv-a",
                tenant_id=_TENANT_A,
                user_id="user-a",
                created_at=_CREATED,
            )
        )
        session.add(
            ConversationRow(
                id="conv-b",
                tenant_id=_TENANT_B,
                user_id="user-b",
                created_at=_CREATED,
            )
        )
        session.add(
            MessageRow(
                id="msg-a",
                conversation_id="conv-a",
                tenant_id=_TENANT_A,
                position=0,
                role="user",
                content="from a",
                sources=[],
            )
        )
        session.add(
            MessageRow(
                id="msg-b",
                conversation_id="conv-b",
                tenant_id=_TENANT_B,
                position=0,
                role="user",
                content="from b",
                sources=[],
            )
        )
        session.commit()

    with session_scope(factory, _TENANT_A) as session:
        conversations = session.scalars(text("SELECT tenant_id FROM conversations")).all()
        messages = session.scalars(text("SELECT tenant_id FROM messages")).all()
        session.add(
            ConversationRow(
                id="conv-own",
                tenant_id=_TENANT_A,
                user_id="user-a",
                created_at=_CREATED,
            )
        )
    assert set(conversations) == {_TENANT_A}
    assert set(messages) == {_TENANT_A}

    with pytest.raises(SQLAlchemyError, match="row-level security"):
        with session_scope(factory, _TENANT_A) as session:
            session.add(
                ConversationRow(
                    id="conv-cross",
                    tenant_id=_TENANT_B,
                    user_id="user-b",
                    created_at=_CREATED,
                )
            )
            session.flush()

    with pytest.raises(SQLAlchemyError, match="row-level security"):
        with session_scope(factory, _TENANT_A) as session:
            session.add(
                MessageRow(
                    id="msg-cross",
                    conversation_id="conv-a",
                    tenant_id=_TENANT_B,
                    position=1,
                    role="user",
                    content="cross",
                    sources=[],
                )
            )
            session.flush()

    with engine.connect() as conn:
        own = conn.scalar(text("SELECT id FROM conversations WHERE id = 'conv-own'"))
        cross = conn.scalar(text("SELECT id FROM conversations WHERE id = 'conv-cross'"))
        message = conn.scalar(text("SELECT id FROM messages WHERE id = 'msg-cross'"))
    assert own == "conv-own"
    assert cross is None
    assert message is None


def test_missed_user_filter_returns_only_session_tenant(db: tuple[Engine, str]) -> None:
    engine, _url = db
    factory = _factory(engine)
    with factory() as session:
        session.add(
            UserRow(
                id="user-a",
                tenant_id=_TENANT_A,
                email="a@example.com",
                password_hash="hash-a",
            )
        )
        session.add(
            UserRow(
                id="user-b",
                tenant_id=_TENANT_B,
                email="b@example.com",
                password_hash="hash-b",
            )
        )
        session.commit()

    with session_scope(factory, _TENANT_A) as session:
        rows = session.scalars(text("SELECT tenant_id FROM users")).all()

    assert set(rows) == {_TENANT_A}


def test_login_as_restricted_role_returns_bearer_jwt(db: tuple[Engine, str]) -> None:
    engine, url = db
    factory = _factory(engine)
    password_hash = Argon2PasswordHasher().hash("secret")
    with factory() as session:
        session.add(
            UserRow(
                id="user-a",
                tenant_id=_TENANT_A,
                email="admin@example.com",
                password_hash=password_hash,
            )
        )
        session.commit()

    with session_scope(factory) as session:
        assert session.scalar(text("SELECT current_user")) == "app_rls"
        assert session.scalar(text("SELECT id FROM users LIMIT 1")) is None
        found = SqlAlchemyUserRepository(session).get_by_email("admin@example.com")
    assert found is not None
    assert found.id.value == "user-a"
    assert found.tenant_id.value == _TENANT_A

    client = TestClient(
        create_app(
            settings=Settings(
                jwt_secret=_JWT_SECRET,
                database_url=url,
                _env_file=None,
            ),
            readiness_probes=[],
        )
    )
    ok = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )
    assert ok.status_code == 200
    token = ok.json()["data"]["access_token"]
    claims = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    assert claims["user_id"] == "user-a"
    assert claims["tenant_id"] == _TENANT_A

    for payload in (
        {"email": "admin@example.com", "password": "wrong"},
        {"email": "missing@example.com", "password": "secret"},
    ):
        denied = client.post("/api/v1/auth/login", json=payload)
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_bootstrap_twice_keeps_password_hash(
    db: tuple[Engine, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, url = db
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("BOOTSTRAP_TENANT_NAME", "Demo")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "secret")

    assert main(["bootstrap"]) == 0
    with engine.connect() as conn:
        first_hash = conn.scalar(text("SELECT password_hash FROM users"))
        user_count = conn.scalar(text("SELECT count(*) FROM users"))
    assert user_count == 1
    assert isinstance(first_hash, str) and first_hash

    factory = _factory(engine)
    with session_scope(factory) as session:
        assert session.scalar(text("SELECT current_user")) == "app_rls"
        assert session.scalar(text("SELECT id FROM users LIMIT 1")) is None
        assert SqlAlchemyUserRepository(session).any_exist() is True

    assert main(["bootstrap"]) == 0
    with engine.connect() as conn:
        second_hash = conn.scalar(text("SELECT password_hash FROM users"))
        user_count = conn.scalar(text("SELECT count(*) FROM users"))
    assert user_count == 1
    assert second_hash == first_hash


def test_worker_after_processing_commit_sees_only_actor_rows(
    db: tuple[Engine, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _url = db
    factory = _factory(engine)
    with factory() as session:
        _add_document(session, "doc-a", _TENANT_A, "a.pdf")
        _add_document(session, "doc-b", _TENANT_B, "b.pdf")
        session.commit()

    captured: dict[str, object] = {}

    class SpyRepository(SqlAlchemyDocumentRepository):
        def __init__(self, session: Session) -> None:
            super().__init__(session)
            captured["session"] = session

    class Bytes:
        def get(self, *, tenant_id: str, document_id: str, filename: str) -> bytes:
            with engine.connect() as conn:
                status = conn.scalar(
                    text("SELECT status FROM documents WHERE id = 'doc-a'")
                )
            assert status == "processing"
            session = captured["session"]
            assert isinstance(session, Session)
            captured["tenants"] = set(
                session.scalars(text("SELECT tenant_id FROM documents")).all()
            )
            raise RuntimeError("stop after commit")

    class Chunks:
        def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
            return None

    class Unused:
        def extract(self, content: bytes) -> list[str]:
            raise AssertionError("extractor should not run")

        def chunk(self, extracted: object) -> list[object]:
            raise AssertionError("chunker should not run")

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("embeddings should not run")

    monkeypatch.setattr(
        "app.bootstrap.worker.SqlAlchemyDocumentRepository",
        SpyRepository,
    )
    outcome = SessionBoundProcessDocument(
        factory,
        Bytes(),  # type: ignore[arg-type]
        Unused(),  # type: ignore[arg-type]
        Unused(),  # type: ignore[arg-type]
        Unused(),  # type: ignore[arg-type]
        Chunks(),  # type: ignore[arg-type]
        max_pages=10,
        max_concurrent=2,
    ).execute(Actor(tenant_id=_TENANT_A, user_id="user-a"), "doc-a")

    assert outcome is ProcessOutcome.FAILED
    assert captured["tenants"] == {_TENANT_A}


def test_commit_returns_connection_as_app_with_tenant_unset(db: tuple[Engine, str]) -> None:
    engine, _url = db
    factory = _factory(engine)
    held = engine.connect()
    try:
        with session_scope(factory, _TENANT_A) as session:
            session.execute(text("SELECT 1"))
            pinned_pid = session.scalar(text("SELECT pg_backend_pid()"))
        held_pid = held.scalar(text("SELECT pg_backend_pid()"))
        assert pinned_pid != held_pid
    finally:
        held.close()

    checked = [engine.connect(), engine.connect()]
    try:
        pids = set()
        for conn in checked:
            pids.add(conn.scalar(text("SELECT pg_backend_pid()")))
            assert conn.scalar(text("SELECT current_user")) == "app"
            # Postgres reports an untouched custom GUC as NULL or as ''.
            # Either value matches no tenant_id. A leaked pin would be the tenant.
            setting = conn.scalar(text("SELECT current_setting('app.tenant_id', true)"))
            assert setting in (None, "")
        assert pinned_pid in pids
    finally:
        for conn in checked:
            conn.close()
