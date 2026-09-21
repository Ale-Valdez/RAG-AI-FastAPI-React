from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import CurrentMember, LoginCommand, LoginResult
from app.application.health.get_health import GetHealth
from app.application.health.get_readiness import GetReadiness, ReadinessProbe
from app.domain.actor import Actor
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.config.settings import Settings, load_settings
from app.infrastructure.health.postgres_probe import PostgresProbe
from app.infrastructure.health.qdrant_probe import QdrantProbe
from app.infrastructure.health.redis_probe import RedisProbe
from app.infrastructure.http.auth_router import (
    GetCurrentMemberUseCase,
    LoginUseCase,
    build_auth_router,
)
from app.infrastructure.http.error_handlers import register_error_handlers
from app.infrastructure.http.health_router import build_health_router
from app.infrastructure.persistence.session import create_db_engine, create_session_factory
from app.infrastructure.persistence.user_repository import SqlAlchemyUserRepository


def default_probes(settings: Settings) -> list[ReadinessProbe]:
    return [
        PostgresProbe(settings.database_url),
        RedisProbe(settings.redis_url),
        QdrantProbe(settings.qdrant_url),
    ]


class _LazySessionFactory:
    """Builds the SQLAlchemy engine on first session open, not at app construction."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._factory: sessionmaker[Session] | None = None

    def __call__(self) -> Session:
        if self._factory is None:
            self._factory = create_session_factory(create_db_engine(self._database_url))
        return self._factory()


class SessionBoundLogin:
    def __init__(self, open_session: _LazySessionFactory, hasher: Argon2PasswordHasher) -> None:
        self._open_session = open_session
        self._hasher = hasher

    def execute(self, command: LoginCommand) -> LoginResult:
        session = self._open_session()
        try:
            result = Login(SqlAlchemyUserRepository(session), self._hasher).execute(command)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class SessionBoundGetCurrentMember:
    def __init__(self, open_session: _LazySessionFactory) -> None:
        self._open_session = open_session

    def execute(self, actor: Actor) -> CurrentMember:
        session = self._open_session()
        try:
            result = GetCurrentMember(SqlAlchemyUserRepository(session)).execute(actor)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _default_auth(
    settings: Settings,
) -> tuple[SessionBoundLogin, SessionBoundGetCurrentMember, JwtService]:
    open_session = _LazySessionFactory(settings.database_url)
    return (
        SessionBoundLogin(open_session, Argon2PasswordHasher()),
        SessionBoundGetCurrentMember(open_session),
        JwtService(settings.jwt_secret),
    )


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probes: list[ReadinessProbe] | None = None,
    login: LoginUseCase | None = None,
    get_current_member: GetCurrentMemberUseCase | None = None,
    jwt_service: JwtService | None = None,
) -> FastAPI:
    loaded = settings or load_settings()
    probes = readiness_probes if readiness_probes is not None else default_probes(loaded)

    if login is None or get_current_member is None or jwt_service is None:
        default_login, default_member, default_jwt = _default_auth(loaded)
        login = login or default_login
        get_current_member = get_current_member or default_member
        jwt_service = jwt_service or default_jwt

    application = FastAPI(title=loaded.app_name)
    application.state.jwt_service = jwt_service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=loaded.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(
        build_health_router(GetHealth(loaded.app_name), GetReadiness(probes))
    )
    application.include_router(
        build_auth_router(
            login=login,
            get_current_member=get_current_member,
            jwt_service=jwt_service,
        )
    )
    return application
