from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker


def to_sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


def create_db_engine(database_url: str) -> Engine:
    url = to_sqlalchemy_url(database_url)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def pin_rls_session(session: Session, tenant_id: str | None) -> None:
    """Re-apply a transaction-local role and tenant whenever a transaction begins.

    ``Session.commit()`` ends the transaction and returns the connection to the
    pool. ``SET LOCAL`` ends with that transaction, so the next checkout is not
    left as ``app_rls`` with the previous tenant. The listener runs again on the
    next transaction, including the one after ``ProcessDocument``'s processing
    commit. In-memory fakes are left untouched.
    """
    if not isinstance(session, Session):
        return

    def _apply(
        _session: Session, _transaction: SessionTransaction, connection: Connection
    ) -> None:
        if connection.dialect.name != "postgresql":
            return
        connection.exec_driver_sql("SET LOCAL ROLE app_rls")
        if tenant_id is not None:
            connection.scalar(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": tenant_id},
            )

    event.listen(session, "after_begin", _apply)
    session.info["rls_after_begin"] = _apply


def clear_rls_session(session: Session) -> None:
    """Drop the pin listener. Does not issue SQL or replace the caller's error."""
    if not isinstance(session, Session):
        return
    listener = session.info.pop("rls_after_begin", None)
    if listener is not None:
        event.remove(session, "after_begin", listener)


@contextmanager
def session_scope(
    open_session: Callable[[], Session],
    tenant_id: str | None = None,
) -> Generator[Session, None, None]:
    session = open_session()
    try:
        pin_rls_session(session, tenant_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        clear_rls_session(session)
        session.close()
