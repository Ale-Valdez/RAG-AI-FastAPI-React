from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.application.chat.ask_question import AskQuestion
from app.application.chat.get_conversation import GetConversation
from app.application.chat.list_conversations import ListConversations
from app.application.retrieval.retrieve_chunks import RetrieveChunks
from app.bootstrap.create_app import _default_chat
from app.domain.actor import Actor
from app.domain.chat import Conversation, Message, SourceRef
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import DomainError, NotFoundError
from app.domain.identity import UserId
from app.domain.tenancy import TenantId
from app.infrastructure.chat.openai_answer_generator import OpenAIAnswerGenerator
from app.infrastructure.config.settings import Settings
from tests.fakes import (
    FakeAnswerGenerator,
    FakeEmbeddingGenerator,
    InMemoryChunkStore,
    InMemoryConversationRepository,
    InMemoryDocumentRepository,
)

_ACTOR_A = Actor(tenant_id="tenant-a", user_id="user-a")
_ACTOR_B = Actor(tenant_id="tenant-b", user_id="user-b")
_OTHER_USER = Actor(tenant_id="tenant-a", user_id="user-b")
_QUESTION = "what is the policy?"
_REFUSAL = "I don't know based on the ready documents."


def _ask(
    documents: InMemoryDocumentRepository,
    embeddings: FakeEmbeddingGenerator,
    chunk_store: InMemoryChunkStore,
    conversations: InMemoryConversationRepository,
    generator: FakeAnswerGenerator,
) -> AskQuestion:
    retrieve = RetrieveChunks(
        documents,
        embeddings,
        chunk_store,
        top_k=5,
        score_threshold=0.70,
    )
    return AskQuestion(conversations, retrieve, generator)


def _save_document(
    documents: InMemoryDocumentRepository,
    document_id: str,
    tenant_id: str,
    status: DocumentStatus,
) -> None:
    documents.save(
        Document(
            id=document_id,
            tenant_id=TenantId(tenant_id),
            filename=f"{document_id}.pdf",
            status=status,
        )
    )


def _point(
    chunk_store: InMemoryChunkStore,
    *,
    tenant_id: str,
    document_id: str,
    chunk_index: int,
    vector: list[float],
    text: str | None = None,
    page: int = 0,
) -> None:
    chunk_store.points[f"{document_id}:{chunk_index}"] = {
        "tenant_id": tenant_id,
        "document_id": document_id,
        "filename": f"{document_id}.pdf",
        "page": page,
        "chunk_index": chunk_index,
        "text": text if text is not None else f"{document_id}:{chunk_index}",
        "vector": vector,
    }


def test_chat_model_setting_defaults_to_gpt_4o_mini(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_CHAT_MODEL", "RAG_TOP_K", "RAG_SCORE_THRESHOLD"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_chat_model == "gpt-4o-mini"
    assert settings.rag_top_k == 5
    assert settings.rag_score_threshold == 0.70


def test_default_chat_keeps_retrieve_and_chat_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_KEY", "OPENAI_CHAT_MODEL", "RAG_TOP_K", "RAG_SCORE_THRESHOLD"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    ask, _get_conversation, _list_conversations = _default_chat(settings)
    assert ask._top_k == settings.rag_top_k == 5
    assert ask._score_threshold == settings.rag_score_threshold == 0.70
    assert ask._chat_model == settings.openai_chat_model == "gpt-4o-mini"
    assert ask._embeddings is None
    assert ask._generator is None


def test_grounded_ask_stores_sources_from_actor_ready_chunks() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _save_document(documents, "ready-2", "tenant-a", DocumentStatus.READY)
    _save_document(documents, "pending-a", "tenant-a", DocumentStatus.PENDING)
    _save_document(documents, "ready-b", "tenant-b", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="policy text",
        page=2,
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=1,
        vector=[1.0, 1.0, 1.0],
        text="second text",
        page=4,
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="pending-a",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="not ready",
    )
    _point(
        chunk_store,
        tenant_id="tenant-b",
        document_id="ready-b",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="other tenant",
    )

    conversation = _ask(documents, embeddings, chunk_store, conversations, generator).execute(
        _ACTOR_A,
        _QUESTION,
    )

    UUID(conversation.id)
    assert conversation.tenant_id == TenantId("tenant-a")
    assert conversation.user_id == UserId("user-a")
    assert len(conversation.messages) == 2
    assert conversation.messages[0] == Message(role="user", content=_QUESTION)
    assert conversation.messages[1].role == "assistant"
    assert conversation.messages[1].content == "grounded answer"
    assert conversation.messages[1].sources == (
        SourceRef(document_id="ready-1", filename="ready-1.pdf", page=2, chunk_index=0),
        SourceRef(document_id="ready-2", filename="ready-2.pdf", page=4, chunk_index=1),
    )
    assert all(source.document_id in {"ready-1", "ready-2"} for source in conversation.messages[1].sources)
    assert generator.calls == [(_QUESTION, ["policy text", "second text"])]
    assert embeddings.texts == [[_QUESTION]]
    call = chunk_store.search_calls[0]
    actor = call["actor"]
    assert isinstance(actor, Actor)
    assert actor.tenant_id == "tenant-a"
    assert actor.user_id == "user-a"
    assert call["document_id"] is None
    assert conversations.items[conversation.id] is conversation


def test_ask_passes_document_id_and_limits_sources() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _save_document(documents, "ready-2", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="from one",
        page=3,
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="from two",
    )

    conversation = _ask(documents, embeddings, chunk_store, conversations, generator).execute(
        _ACTOR_A,
        _QUESTION,
        "ready-1",
    )

    assert conversation.messages[1].sources == (
        SourceRef(document_id="ready-1", filename="ready-1.pdf", page=3, chunk_index=0),
    )
    assert generator.calls == [(_QUESTION, ["from one"])]
    assert chunk_store.search_calls[0]["document_id"] == "ready-1"
    assert chunk_store.search_calls[0]["ready_ids"] == ["ready-1"]


@pytest.mark.parametrize("ready", [False, True])
def test_empty_retrieval_saves_refusal_without_calling_generator(ready: bool) -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    if ready:
        _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
        _point(
            chunk_store,
            tenant_id="tenant-a",
            document_id="ready-1",
            chunk_index=0,
            vector=[1.0, 0.0, 0.0],
            text="below threshold",
        )
    else:
        _save_document(documents, "pending-a", "tenant-a", DocumentStatus.PENDING)
        _point(
            chunk_store,
            tenant_id="tenant-a",
            document_id="pending-a",
            chunk_index=0,
            vector=[1.0, 1.0, 1.0],
            text="not ready",
        )

    conversation = _ask(documents, embeddings, chunk_store, conversations, generator).execute(
        _ACTOR_A,
        _QUESTION,
    )

    assert conversation.messages[0] == Message(role="user", content=_QUESTION)
    assert conversation.messages[1] == Message(role="assistant", content=_REFUSAL)
    assert generator.calls == []
    assert conversations.save_calls == 1
    assert conversations.items[conversation.id].messages[1].content == _REFUSAL


def test_continue_appends_one_turn_and_keeps_prior_messages() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="policy text",
        page=1,
    )
    ask = _ask(documents, embeddings, chunk_store, conversations, generator)
    first = ask.execute(_ACTOR_A, _QUESTION)
    prior = list(first.messages)
    created_at = first.created_at

    second = ask.execute(_ACTOR_A, "what about leave?", None, first.id)

    assert second is first
    assert second.created_at == created_at
    assert second.messages[:2] == prior
    assert len(second.messages) == 4
    assert second.messages[2] == Message(role="user", content="what about leave?")
    assert second.messages[3].role == "assistant"
    assert second.messages[3].content == "grounded answer"
    assert second.messages[3].sources == prior[1].sources
    assert [call[0] for call in generator.calls] == [_QUESTION, "what about leave?"]
    assert generator.calls[1][1] == ["policy text"]
    assert "grounded answer" not in generator.calls[1][1]
    assert len(chunk_store.search_calls) == 2
    assert conversations.save_calls == 2


def test_reload_returns_messages_and_sources_in_write_order() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="policy text",
        page=1,
    )
    saved = _ask(documents, embeddings, chunk_store, conversations, generator).execute(
        _ACTOR_A,
        _QUESTION,
    )

    loaded = GetConversation(conversations).execute(_ACTOR_A, saved.id)

    assert loaded.id == saved.id
    assert loaded.messages == saved.messages
    assert [message.role for message in loaded.messages] == ["user", "assistant"]
    assert loaded.messages[1].sources == (
        SourceRef(document_id="ready-1", filename="ready-1.pdf", page=1, chunk_index=0),
    )


def test_list_returns_actor_threads_newest_first() -> None:
    conversations = InMemoryConversationRepository()
    older = Conversation(
        id="older",
        tenant_id=TenantId("tenant-a"),
        user_id=UserId("user-a"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[Message(role="user", content="first")],
    )
    newer = Conversation(
        id="newer",
        tenant_id=TenantId("tenant-a"),
        user_id=UserId("user-a"),
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
        messages=[Message(role="assistant", content="second", sources=())],
    )
    other_user = Conversation(
        id="other-user",
        tenant_id=TenantId("tenant-a"),
        user_id=UserId("user-b"),
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    other_tenant = Conversation(
        id="other-tenant",
        tenant_id=TenantId("tenant-b"),
        user_id=UserId("user-a"),
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    for item in (older, newer, other_user, other_tenant):
        conversations.save(item)

    listed = ListConversations(conversations).execute(_ACTOR_A)

    assert [item.id for item in listed] == ["newer", "older"]
    assert [item.created_at for item in listed] == [newer.created_at, older.created_at]
    assert all(item.user_id == UserId("user-a") for item in listed)
    assert all(item.tenant_id == TenantId("tenant-a") for item in listed)


@pytest.mark.parametrize(
    ("owner", "conversation_id"),
    [
        (None, "missing"),
        (_OTHER_USER, "thread-b"),
        (_ACTOR_B, "thread-b"),
    ],
)
def test_other_owner_raises_not_found_without_generate_or_write(
    owner: Actor | None,
    conversation_id: str,
) -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="policy text",
    )
    if owner is not None:
        conversations.save(
            Conversation(
                id=conversation_id,
                tenant_id=TenantId(owner.tenant_id),
                user_id=UserId(owner.user_id),
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                messages=[Message(role="user", content="kept")],
            )
        )
    conversations.save_calls = 0

    with pytest.raises(NotFoundError):
        _ask(documents, embeddings, chunk_store, conversations, generator).execute(
            _ACTOR_A,
            _QUESTION,
            None,
            conversation_id,
        )

    assert generator.calls == []
    assert embeddings.calls == 0
    assert chunk_store.search_calls == []
    assert conversations.save_calls == 0
    if owner is not None:
        assert conversations.items[conversation_id].messages == [
            Message(role="user", content="kept")
        ]


@pytest.mark.parametrize(
    ("document_id", "tenant_id", "status"),
    [
        ("missing", "tenant-a", None),
        ("other-tenant", "tenant-b", DocumentStatus.READY),
        ("pending-doc", "tenant-a", DocumentStatus.PENDING),
        ("processing-doc", "tenant-a", DocumentStatus.PROCESSING),
        ("failed-doc", "tenant-a", DocumentStatus.FAILED),
    ],
)
def test_bad_document_raises_not_found_without_writing(
    document_id: str,
    tenant_id: str,
    status: DocumentStatus | None,
) -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    if status is not None:
        _save_document(documents, document_id, tenant_id, status)
        _point(
            chunk_store,
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_index=0,
            vector=[1.0, 1.0, 1.0],
        )

    with pytest.raises(NotFoundError):
        _ask(documents, embeddings, chunk_store, conversations, generator).execute(
            _ACTOR_A,
            _QUESTION,
            document_id,
        )

    assert conversations.items == {}
    assert conversations.save_calls == 0
    assert generator.calls == []
    assert embeddings.calls == 0
    assert chunk_store.search_calls == []


def test_follow_up_with_missing_document_does_not_write() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    existing = Conversation(
        id="thread-a",
        tenant_id=TenantId("tenant-a"),
        user_id=UserId("user-a"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[
            Message(role="user", content="what is the policy?"),
            Message(role="assistant", content="grounded answer"),
        ],
    )
    conversations.save(existing)
    conversations.save_calls = 0
    prior = list(existing.messages)

    with pytest.raises(NotFoundError):
        _ask(documents, embeddings, chunk_store, conversations, generator).execute(
            _ACTOR_A,
            "what about leave?",
            "missing",
            existing.id,
        )

    assert conversations.save_calls == 0
    assert existing.messages == prior


@pytest.mark.parametrize("question", ["", " ", "\n", "\t", " \n\t "])
def test_blank_question_raises_before_retrieve(question: str) -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    conversations = InMemoryConversationRepository()
    generator = FakeAnswerGenerator()
    _save_document(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
    )
    existing = Conversation(
        id="thread-a",
        tenant_id=TenantId("tenant-a"),
        user_id=UserId("user-a"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[Message(role="user", content="kept")],
    )
    conversations.save(existing)
    conversations.save_calls = 0

    with pytest.raises(DomainError) as new_thread:
        _ask(documents, embeddings, chunk_store, conversations, generator).execute(
            _ACTOR_A,
            question,
            "missing",
        )
    assert type(new_thread.value) is DomainError

    with pytest.raises(DomainError) as continued:
        _ask(documents, embeddings, chunk_store, conversations, generator).execute(
            _ACTOR_A,
            question,
            None,
            existing.id,
        )
    assert type(continued.value) is DomainError

    assert conversations.save_calls == 0
    assert conversations.items[existing.id].messages == [Message(role="user", content="kept")]
    assert embeddings.calls == 0
    assert chunk_store.search_calls == []
    assert generator.calls == []


def test_openai_generator_sends_question_and_chunk_texts() -> None:
    class _Completions:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] | None = None

        def create(self, **kwargs: object) -> object:
            self.kwargs = kwargs
            message = type("Message", (), {"content": "from model"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class _Chat:
        def __init__(self) -> None:
            self.completions = _Completions()

    class _Client:
        def __init__(self) -> None:
            self.chat = _Chat()

    client = _Client()
    generator = OpenAIAnswerGenerator(api_key="test", model="gpt-4o-mini", client=client)

    answer = generator.generate("what is the policy?", ["policy text", "second text"])

    assert answer == "from model"
    kwargs = client.chat.completions.kwargs
    assert kwargs is not None
    assert kwargs["model"] == "gpt-4o-mini"
    messages = kwargs["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, str)
    assert "what is the policy?" in content
    assert "policy text" in content
    assert "second text" in content
