from __future__ import annotations

import math
from collections.abc import Sequence

from app.domain.actor import Actor
from app.domain.chat import Conversation
from app.domain.documents import Document, DocumentStatus
from app.domain.identity import User, UserId
from app.domain.ports.ingestion import PageText, TextChunk
from app.domain.ports.retrieval import RetrievedChunk
from app.domain.tenancy import Tenant, TenantId


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.items: dict[str, Tenant] = {}

    def save(self, tenant: Tenant) -> None:
        self.items[tenant.id.value] = tenant

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        return self.items.get(tenant_id.value)

    def any_exist(self) -> bool:
        return bool(self.items)


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[str, User] = {}
        self.by_email: dict[str, User] = {}

    def save(self, user: User) -> None:
        self.items[user.id.value] = user
        self.by_email[user.email] = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.items.get(user_id.value)

    def get_by_email(self, email: str) -> User | None:
        return self.by_email.get(email)

    def any_exist(self) -> bool:
        return bool(self.items)


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.items: list[Document] = []
        self.save_calls = 0

    def save(self, document: Document) -> None:
        self.save_calls += 1
        for index, item in enumerate(self.items):
            if item.id == document.id:
                self.items[index] = document
                return
        self.items.append(document)

    def get(self, document_id: str) -> Document | None:
        for item in self.items:
            if item.id == document_id:
                return item
        return None

    def delete(self, document_id: str) -> None:
        self.items = [item for item in self.items if item.id != document_id]

    def list_for_tenant(self, tenant_id: TenantId) -> list[Document]:
        return [item for item in reversed(self.items) if item.tenant_id == tenant_id]

    def count_processing(self, tenant_id: TenantId) -> int:
        return sum(
            1
            for item in self.items
            if item.tenant_id == tenant_id and item.status is DocumentStatus.PROCESSING
        )


class InMemoryDocumentBytes:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls = 0
        self.delete_calls = 0
        self.get_calls = 0

    def put(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> None:
        self.put_calls += 1
        self.objects[f"{tenant_id}/{document_id}/{filename}"] = content

    def get(self, *, tenant_id: str, document_id: str, filename: str) -> bytes:
        self.get_calls += 1
        key = f"{tenant_id}/{document_id}/{filename}"
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    def delete(self, *, tenant_id: str, document_id: str, filename: str) -> None:
        self.delete_calls += 1
        self.objects.pop(f"{tenant_id}/{document_id}/{filename}", None)


class FakeDocumentJobQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.jobs: list[dict[str, str]] = []
        self.fail = fail

    def enqueue(self, *, tenant_id: str, user_id: str, document_id: str) -> None:
        if self.fail:
            raise RuntimeError("enqueue failed")
        self.jobs.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "document_id": document_id,
            }
        )


class FakePdfTextExtractor:
    def __init__(
        self,
        pages: list[PageText] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.pages = pages if pages is not None else [PageText(page=0, text="hello world")]
        self.fail = fail
        self.calls = 0

    def extract_pages(self, content: bytes) -> list[PageText]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("extract failed")
        return list(self.pages)


class FakeEmbeddingGenerator:
    def __init__(
        self,
        *,
        fail: bool = False,
        dim: int = 3,
        vector: list[float] | None = None,
    ) -> None:
        self.fail = fail
        self.dim = dim
        self.vector = vector
        self.calls = 0
        self.texts: list[list[str]] = []
        self.committed_before_embed = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.texts.append(list(texts))
        if self.fail:
            raise RuntimeError("embed failed")
        if self.vector is not None:
            return [list(self.vector) for _ in texts]
        return [[float(index + 1)] * self.dim for index, _ in enumerate(texts)]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class InMemoryChunkStore:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.points: dict[str, dict[str, object]] = {}
        self.delete_calls: list[tuple[str, str]] = []
        self.upsert_calls = 0
        self.fail_upsert = fail_upsert
        self.search_calls: list[dict[str, object]] = []

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        self.delete_calls.append((tenant_id, document_id))
        to_remove = [
            key
            for key, point in self.points.items()
            if point["tenant_id"] == tenant_id and point["document_id"] == document_id
        ]
        for key in to_remove:
            del self.points[key]

    def upsert_chunks(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None:
        self.upsert_calls += 1
        if self.fail_upsert:
            raise RuntimeError("upsert failed")
        for chunk, vector in zip(chunks, vectors, strict=True):
            key = f"{document_id}:{chunk.chunk_index}"
            self.points[key] = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "filename": filename,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "vector": vector,
            }

    def search(
        self,
        *,
        actor: Actor,
        query_vector: list[float],
        document_id: str | None,
        ready_ids: Sequence[str],
        top_k: int,
        score_threshold: float,
    ) -> list[RetrievedChunk]:
        ready = list(ready_ids)
        self.search_calls.append(
            {
                "actor": actor,
                "query_vector": list(query_vector),
                "document_id": document_id,
                "ready_ids": ready,
                "top_k": top_k,
                "score_threshold": score_threshold,
            }
        )
        if not ready:
            return []
        ready_set = set(ready)
        ranked: list[RetrievedChunk] = []
        for point in self.points.values():
            if point["tenant_id"] != actor.tenant_id:
                continue
            point_document_id = str(point["document_id"])
            if point_document_id not in ready_set:
                continue
            if document_id is not None and point_document_id != document_id:
                continue
            raw_vector = point["vector"]
            if not isinstance(raw_vector, list):
                continue
            page = point["page"]
            chunk_index = point["chunk_index"]
            if isinstance(page, bool) or not isinstance(page, int):
                continue
            if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
                continue
            score = _cosine(query_vector, [float(item) for item in raw_vector])
            if score < score_threshold:
                continue
            ranked.append(
                RetrievedChunk(
                    document_id=point_document_id,
                    filename=str(point["filename"]),
                    page=page,
                    chunk_index=chunk_index,
                    text=str(point["text"]),
                    score=score,
                )
            )
        ranked.sort(key=lambda hit: (-hit.score, hit.document_id, hit.chunk_index))
        return ranked[:top_k]


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.items: dict[str, Conversation] = {}
        self.save_calls = 0

    def save(self, conversation: Conversation) -> None:
        self.save_calls += 1
        self.items[conversation.id] = conversation

    def get_for_actor(self, actor: Actor, conversation_id: str) -> Conversation | None:
        conversation = self.items.get(conversation_id)
        if conversation is None:
            return None
        if (
            conversation.tenant_id.value != actor.tenant_id
            or conversation.user_id.value != actor.user_id
        ):
            return None
        return conversation

    def list_for_actor(self, actor: Actor) -> list[Conversation]:
        matches = [
            item
            for item in self.items.values()
            if item.tenant_id.value == actor.tenant_id and item.user_id.value == actor.user_id
        ]
        return sorted(matches, key=lambda item: (item.created_at, item.id), reverse=True)


class FakeAnswerGenerator:
    def __init__(self, answer: str = "grounded answer") -> None:
        self.answer = answer
        self.calls: list[tuple[str, list[str]]] = []

    def generate(self, question: str, context_texts: list[str]) -> str:
        self.calls.append((question, list(context_texts)))
        return self.answer
