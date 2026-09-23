from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import CurrentMember, LoginCommand, LoginResult
from app.application.chat.ask_question import AskQuestion
from app.application.chat.get_conversation import GetConversation
from app.application.chat.list_conversations import ListConversations
from app.application.documents.delete_document import DeleteDocument
from app.application.documents.list_documents import ListDocuments
from app.application.documents.models import UploadDocumentCommand
from app.application.documents.reingest_document import ReingestDocument
from app.application.documents.upload_document import UploadDocument
from app.application.health.get_health import GetHealth
from app.application.health.get_readiness import GetReadiness, ReadinessProbe
from app.application.retrieval.retrieve_chunks import RetrieveChunks
from app.bootstrap.persistence import LazySessionFactory
from app.domain.actor import Actor
from app.domain.chat import Conversation
from app.domain.documents import Document
from app.infrastructure.auth.jwt import JwtService, require_signing_secret
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.chat.openai_answer_generator import OpenAIAnswerGenerator
from app.infrastructure.config.settings import Settings, load_settings
from app.infrastructure.health.postgres_probe import PostgresProbe
from app.infrastructure.health.qdrant_probe import QdrantProbe
from app.infrastructure.health.redis_probe import RedisProbe
from app.infrastructure.http.auth_router import (
    GetCurrentMemberUseCase,
    LoginUseCase,
    build_auth_router,
)
from app.infrastructure.http.conversations_router import (
    AskQuestionUseCase,
    GetConversationUseCase,
    ListConversationsUseCase,
    build_conversations_router,
)
from app.infrastructure.http.documents_router import (
    DeleteDocumentUseCase,
    ListDocumentsUseCase,
    ReingestDocumentUseCase,
    UploadDocumentUseCase,
    build_documents_router,
)
from app.infrastructure.http.error_handlers import register_error_handlers
from app.infrastructure.http.health_router import build_health_router
from app.infrastructure.ingestion.openai_embeddings import OpenAIEmbeddingGenerator
from app.infrastructure.ingestion.qdrant_chunk_store import QdrantChunkStore
from app.infrastructure.persistence.conversation_repository import (
    SqlAlchemyConversationRepository,
)
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.session import session_scope
from app.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.infrastructure.storage.s3_document_bytes import S3DocumentBytes
from app.infrastructure.worker.document_job_queue import CeleryDocumentJobQueue


def default_probes(settings: Settings) -> list[ReadinessProbe]:
    return [
        PostgresProbe(settings.database_url),
        RedisProbe(settings.redis_url),
        QdrantProbe(settings.qdrant_url),
    ]


class SessionBoundLogin:
    def __init__(self, open_session: LazySessionFactory, hasher: Argon2PasswordHasher) -> None:
        self._open_session = open_session
        self._hasher = hasher

    def execute(self, command: LoginCommand) -> LoginResult:
        with session_scope(self._open_session) as session:
            return Login(SqlAlchemyUserRepository(session), self._hasher).execute(command)


class SessionBoundGetCurrentMember:
    def __init__(self, open_session: LazySessionFactory) -> None:
        self._open_session = open_session

    def execute(self, actor: Actor) -> CurrentMember:
        with session_scope(self._open_session) as session:
            return GetCurrentMember(SqlAlchemyUserRepository(session)).execute(actor)


class SessionBoundUploadDocument:
    def __init__(
        self,
        open_session: LazySessionFactory,
        bytes_store: S3DocumentBytes,
        jobs: CeleryDocumentJobQueue,
        max_size_bytes: int,
    ) -> None:
        self._open_session = open_session
        self._bytes_store = bytes_store
        self._jobs = jobs
        self._max_size_bytes = max_size_bytes

    def execute(self, actor: Actor, command: UploadDocumentCommand) -> Document:
        with session_scope(self._open_session) as session:
            return UploadDocument(
                SqlAlchemyDocumentRepository(session),
                self._bytes_store,
                self._jobs,
                self._max_size_bytes,
            ).execute(actor, command)


class SessionBoundListDocuments:
    def __init__(self, open_session: LazySessionFactory) -> None:
        self._open_session = open_session

    def execute(self, actor: Actor) -> list[Document]:
        with session_scope(self._open_session) as session:
            return ListDocuments(SqlAlchemyDocumentRepository(session)).execute(actor)


class SessionBoundDeleteDocument:
    def __init__(
        self,
        open_session: LazySessionFactory,
        bytes_store: S3DocumentBytes,
        chunk_store: QdrantChunkStore,
    ) -> None:
        self._open_session = open_session
        self._bytes_store = bytes_store
        self._chunk_store = chunk_store

    def execute(self, actor: Actor, document_id: str) -> str:
        with session_scope(self._open_session) as session:
            return DeleteDocument(
                SqlAlchemyDocumentRepository(session),
                self._bytes_store,
                self._chunk_store,
            ).execute(actor, document_id)


class SessionBoundReingestDocument:
    def __init__(
        self,
        open_session: LazySessionFactory,
        jobs: CeleryDocumentJobQueue,
    ) -> None:
        self._open_session = open_session
        self._jobs = jobs

    def execute(self, actor: Actor, document_id: str) -> Document:
        with session_scope(self._open_session) as session:
            return ReingestDocument(
                SqlAlchemyDocumentRepository(session),
                self._jobs,
            ).execute(actor, document_id)


class SessionBoundAskQuestion:
    def __init__(
        self,
        open_session: LazySessionFactory,
        retriever: QdrantChunkStore,
        *,
        api_key: str,
        embed_model: str,
        chat_model: str,
        top_k: int,
        score_threshold: float,
    ) -> None:
        self._open_session = open_session
        self._retriever = retriever
        self._api_key = api_key
        self._embed_model = embed_model
        self._chat_model = chat_model
        self._top_k = top_k
        self._score_threshold = score_threshold
        self._embeddings: OpenAIEmbeddingGenerator | None = None
        self._generator: OpenAIAnswerGenerator | None = None

    def execute(
        self,
        actor: Actor,
        question: str,
        document_id: str | None = None,
        conversation_id: str | None = None,
    ) -> Conversation:
        embeddings, generator = self._clients()
        with session_scope(self._open_session) as session:
            retrieve = RetrieveChunks(
                SqlAlchemyDocumentRepository(session),
                embeddings,
                self._retriever,
                top_k=self._top_k,
                score_threshold=self._score_threshold,
            )
            return AskQuestion(
                SqlAlchemyConversationRepository(session),
                retrieve,
                generator,
            ).execute(actor, question, document_id, conversation_id)

    def _clients(self) -> tuple[OpenAIEmbeddingGenerator, OpenAIAnswerGenerator]:
        if self._embeddings is None or self._generator is None:
            self._embeddings = OpenAIEmbeddingGenerator(
                api_key=self._api_key,
                model=self._embed_model,
            )
            self._generator = OpenAIAnswerGenerator(
                api_key=self._api_key,
                model=self._chat_model,
            )
        return self._embeddings, self._generator


class SessionBoundGetConversation:
    def __init__(self, open_session: LazySessionFactory) -> None:
        self._open_session = open_session

    def execute(self, actor: Actor, conversation_id: str) -> Conversation:
        with session_scope(self._open_session) as session:
            return GetConversation(SqlAlchemyConversationRepository(session)).execute(
                actor, conversation_id
            )


class SessionBoundListConversations:
    def __init__(self, open_session: LazySessionFactory) -> None:
        self._open_session = open_session

    def execute(self, actor: Actor) -> list[Conversation]:
        with session_scope(self._open_session) as session:
            return ListConversations(SqlAlchemyConversationRepository(session)).execute(actor)


def _default_auth(
    settings: Settings,
) -> tuple[SessionBoundLogin, SessionBoundGetCurrentMember, JwtService]:
    require_signing_secret(settings.jwt_secret)
    open_session = LazySessionFactory(settings.database_url)
    return (
        SessionBoundLogin(open_session, Argon2PasswordHasher()),
        SessionBoundGetCurrentMember(open_session),
        JwtService(settings.jwt_secret),
    )


def _default_documents(
    settings: Settings,
) -> tuple[
    SessionBoundUploadDocument,
    SessionBoundListDocuments,
    SessionBoundDeleteDocument,
    SessionBoundReingestDocument,
]:
    open_session = LazySessionFactory(settings.database_url)
    bytes_store = S3DocumentBytes(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        use_path_style=settings.s3_use_path_style,
    )
    jobs = CeleryDocumentJobQueue()
    # Lazily connects on first delete/reingest call — create_app import stays offline.
    chunk_store = QdrantChunkStore(url=settings.qdrant_url)
    return (
        SessionBoundUploadDocument(
            open_session,
            bytes_store,
            jobs,
            settings.max_document_size_bytes,
        ),
        SessionBoundListDocuments(open_session),
        SessionBoundDeleteDocument(open_session, bytes_store, chunk_store),
        SessionBoundReingestDocument(open_session, jobs),
    )


def _default_chat(
    settings: Settings,
) -> tuple[SessionBoundAskQuestion, SessionBoundGetConversation, SessionBoundListConversations]:
    open_session = LazySessionFactory(settings.database_url)
    # Qdrant and OpenAI clients connect on the first ask — create_app stays offline.
    retriever = QdrantChunkStore(url=settings.qdrant_url)
    return (
        SessionBoundAskQuestion(
            open_session,
            retriever,
            api_key=settings.openai_api_key,
            embed_model=settings.openai_embed_model,
            chat_model=settings.openai_chat_model,
            top_k=settings.rag_top_k,
            score_threshold=settings.rag_score_threshold,
        ),
        SessionBoundGetConversation(open_session),
        SessionBoundListConversations(open_session),
    )


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probes: list[ReadinessProbe] | None = None,
    login: LoginUseCase | None = None,
    get_current_member: GetCurrentMemberUseCase | None = None,
    jwt_service: JwtService | None = None,
    upload_document: UploadDocumentUseCase | None = None,
    list_documents: ListDocumentsUseCase | None = None,
    delete_document: DeleteDocumentUseCase | None = None,
    reingest_document: ReingestDocumentUseCase | None = None,
    ask_question: AskQuestionUseCase | None = None,
    get_conversation: GetConversationUseCase | None = None,
    list_conversations: ListConversationsUseCase | None = None,
) -> FastAPI:
    loaded = settings or load_settings()
    probes = readiness_probes if readiness_probes is not None else default_probes(loaded)

    if login is None or get_current_member is None or jwt_service is None:
        default_login, default_member, default_jwt = _default_auth(loaded)
        login = login or default_login
        get_current_member = get_current_member or default_member
        jwt_service = jwt_service or default_jwt

    if (
        upload_document is None
        or list_documents is None
        or delete_document is None
        or reingest_document is None
    ):
        default_upload, default_list, default_delete, default_reingest = _default_documents(
            loaded
        )
        upload_document = upload_document or default_upload
        list_documents = list_documents or default_list
        delete_document = delete_document or default_delete
        reingest_document = reingest_document or default_reingest

    if ask_question is None or get_conversation is None or list_conversations is None:
        default_ask, default_get, default_list = _default_chat(loaded)
        ask_question = ask_question or default_ask
        get_conversation = get_conversation or default_get
        list_conversations = list_conversations or default_list

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
    application.include_router(
        build_documents_router(
            upload_document=upload_document,
            list_documents=list_documents,
            delete_document=delete_document,
            reingest_document=reingest_document,
            jwt_service=jwt_service,
        )
    )
    application.include_router(
        build_conversations_router(
            ask_question=ask_question,
            get_conversation=get_conversation,
            list_conversations=list_conversations,
            jwt_service=jwt_service,
        )
    )
    return application
