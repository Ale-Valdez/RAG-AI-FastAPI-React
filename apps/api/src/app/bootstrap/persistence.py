"""Shared database session factory for the API and the bootstrap CLI."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.session import create_db_engine, create_session_factory


class LazySessionFactory:
    """Opens a SQLAlchemy session on first use so importing the app does not connect."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._factory: sessionmaker[Session] | None = None

    def __call__(self) -> Session:
        if self._factory is None:
            self._factory = create_session_factory(create_db_engine(self._database_url))
        return self._factory()
