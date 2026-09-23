from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.application.auth.bootstrap_tenant import BootstrapTenant
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import BootstrapCommand
from app.application.chat.ask_question import AskQuestion
from app.application.chat.get_conversation import GetConversation
from app.application.chat.list_conversations import ListConversations
from app.application.documents.delete_document import DeleteDocument
from app.application.documents.list_documents import ListDocuments
from app.application.documents.reingest_document import ReingestDocument
from app.application.documents.upload_document import UploadDocument
from app.application.retrieval.retrieve_chunks import RetrieveChunks
from app.bootstrap.create_app import create_app
from app.domain.documents import Document, DocumentStatus
from app.domain.tenancy import TenantId
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.config.settings import Settings
from tests.fakes import (
    FakeAnswerGenerator,
    FakeDocumentJobQueue,
    FakeEmbeddingGenerator,
    FakePasswordHasher,
    InMemoryChunkStore,
    InMemoryConversationRepository,
    InMemoryDocumentBytes,
    InMemoryDocumentRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
)

_SECRET = "test-secret-key-at-least-32-bytes!!"
_QUESTION = "what is the policy?"
_REFUSAL = "I don't know based on the ready documents."


class _ChatApp:
    def __init__(self) -> None:
        tenants = InMemoryTenantRepository()
        users = InMemoryUserRepository()
        hasher = FakePasswordHasher()
        BootstrapTenant(tenants, users, hasher).execute(
            BootstrapCommand(
                tenant_name="Demo",
                admin_email="admin@example.com",
                admin_password="secret",
            )
        )
        user = next(iter(users.items.values()))
        self.documents = InMemoryDocumentRepository()
        self.bytes_store = InMemoryDocumentBytes()
        self.jobs = FakeDocumentJobQueue()
        self.chunk_store = InMemoryChunkStore()
        self.embeddings = FakeEmbeddingGenerator()
        self.conversations = InMemoryConversationRepository()
        self.generator = FakeAnswerGenerator()
        self.jwt_service = JwtService(_SECRET)
        self.user_id = user.id.value
        self.tenant_id = user.tenant_id.value
        retrieve = RetrieveChunks(
            self.documents,
            self.embeddings,
            self.chunk_store,
            top_k=5,
            score_threshold=0.70,
        )
        self.client = TestClient(
            create_app(
                settings=Settings(jwt_secret=_SECRET),
                readiness_probes=[],
                login=Login(users, hasher),
                get_current_member=GetCurrentMember(users),
                jwt_service=self.jwt_service,
                upload_document=UploadDocument(self.documents, self.bytes_store, self.jobs, 1024),
                list_documents=ListDocuments(self.documents),
                delete_document=DeleteDocument(self.documents, self.bytes_store, self.chunk_store),
                reingest_document=ReingestDocument(self.documents, self.jobs),
                ask_question=AskQuestion(self.conversations, retrieve, self.generator),
                get_conversation=GetConversation(self.conversations),
                list_conversations=ListConversations(self.conversations),
            )
        )

    def headers(self, user_id: str | None = None, tenant_id: str | None = None) -> dict[str, str]:
        token = self.jwt_service.create_access_token(
            user_id=user_id or self.user_id,
            tenant_id=tenant_id or self.tenant_id,
        )
        return {"Authorization": f"Bearer {token}"}


def _ready_chunk(app: _ChatApp) -> None:
    app.documents.save(
        Document(
            id="ready-1",
            tenant_id=TenantId(app.tenant_id),
            filename="ready-1.pdf",
            status=DocumentStatus.READY,
        )
    )
    app.chunk_store.points["ready-1:0"] = {
        "tenant_id": app.tenant_id,
        "document_id": "ready-1",
        "filename": "ready-1.pdf",
        "page": 2,
        "chunk_index": 0,
        "text": "policy text",
        "vector": [1.0, 1.0, 1.0],
    }


def test_ask_reload_and_list_envelope() -> None:
    app = _ChatApp()
    _ready_chunk(app)
    headers = app.headers()

    created = app.client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"question": _QUESTION, "document_id": "ready-1"},
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"data", "error"}
    assert body["error"] is None
    data = body["data"]
    assert set(data) == {"id", "messages"}
    assert data["messages"][0] == {"role": "user", "content": _QUESTION, "sources": []}
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"] == "grounded answer"
    assert data["messages"][1]["sources"] == [
        {
            "document_id": "ready-1",
            "filename": "ready-1.pdf",
            "page": 2,
            "chunk_index": 0,
        }
    ]
    assert set(data["messages"][1]["sources"][0]) == {
        "document_id",
        "filename",
        "page",
        "chunk_index",
    }
    conversation_id = data["id"]
    assert app.generator.calls == [(_QUESTION, ["policy text"])]

    reloaded = app.client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert reloaded.status_code == 200
    assert reloaded.json()["error"] is None
    assert reloaded.json()["data"] == data

    listed = app.client.get("/api/v1/conversations", headers=headers)
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["error"] is None
    assert len(listed_body["data"]["conversations"]) == 1
    item = listed_body["data"]["conversations"][0]
    assert set(item) == {"id", "created_at"}
    assert item["id"] == conversation_id
    assert item["created_at"] == app.conversations.items[conversation_id].created_at.isoformat()
    datetime.fromisoformat(item["created_at"])


def test_continue_appends_messages() -> None:
    app = _ChatApp()
    _ready_chunk(app)
    headers = app.headers()
    created = app.client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"question": _QUESTION},
    )
    conversation_id = created.json()["data"]["id"]
    first_messages = created.json()["data"]["messages"]

    continued = app.client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"question": "what about leave?"},
    )
    assert continued.status_code == 200
    messages = continued.json()["data"]["messages"]
    assert messages[:2] == first_messages
    assert len(messages) == 4
    assert messages[2]["content"] == "what about leave?"
    assert messages[3]["sources"][0]["document_id"] == "ready-1"


def test_empty_retrieval_returns_refusal() -> None:
    app = _ChatApp()
    response = app.client.post(
        "/api/v1/conversations",
        headers=app.headers(),
        json={"question": _QUESTION},
    )
    assert response.status_code == 201
    messages = response.json()["data"]["messages"]
    assert messages[1]["content"] == _REFUSAL
    assert messages[1]["sources"] == []
    assert app.generator.calls == []
    assert app.conversations.save_calls == 1


def test_blank_question_is_domain_rule_violation() -> None:
    app = _ChatApp()
    response = app.client.post(
        "/api/v1/conversations",
        headers=app.headers(),
        json={"question": "   "},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOMAIN_RULE_VIOLATION"
    assert response.json()["data"] is None
    assert app.conversations.items == {}
    assert app.embeddings.calls == 0
    assert app.generator.calls == []


def test_bad_document_is_not_found_and_writes_nothing() -> None:
    app = _ChatApp()
    response = app.client.post(
        "/api/v1/conversations",
        headers=app.headers(),
        json={"question": _QUESTION, "document_id": "missing"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert app.conversations.items == {}
    assert app.generator.calls == []


def test_other_owner_cannot_reload_or_continue() -> None:
    app = _ChatApp()
    _ready_chunk(app)
    created = app.client.post(
        "/api/v1/conversations",
        headers=app.headers(),
        json={"question": _QUESTION},
    )
    conversation_id = created.json()["data"]["id"]
    app.generator.calls.clear()
    saves = app.conversations.save_calls
    other_headers = app.headers(user_id="other-user", tenant_id="other-tenant")

    reloaded = app.client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=other_headers,
    )
    continued = app.client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=other_headers,
        json={"question": "stolen?"},
    )
    listed = app.client.get("/api/v1/conversations", headers=other_headers)

    assert reloaded.status_code == 404
    assert reloaded.json()["error"]["code"] == "NOT_FOUND"
    assert continued.status_code == 404
    assert continued.json()["error"]["code"] == "NOT_FOUND"
    assert listed.status_code == 200
    assert listed.json()["data"]["conversations"] == []
    assert app.generator.calls == []
    assert app.conversations.save_calls == saves
    assert len(app.conversations.items[conversation_id].messages) == 2


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/conversations"),
        ("post", "/api/v1/conversations/missing/messages"),
        ("get", "/api/v1/conversations/missing"),
        ("get", "/api/v1/conversations"),
    ],
)
def test_conversation_routes_require_bearer(method: str, path: str) -> None:
    app = _ChatApp()
    _ready_chunk(app)
    kwargs: dict[str, object] = {}
    if method == "post":
        kwargs["json"] = {"question": _QUESTION}
    response = getattr(app.client, method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert app.conversations.items == {}
    assert app.embeddings.calls == 0
    assert app.generator.calls == []
    assert app.chunk_store.search_calls == []
