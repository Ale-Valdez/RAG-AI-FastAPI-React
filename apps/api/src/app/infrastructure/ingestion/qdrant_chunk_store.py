from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.domain.actor import Actor
from app.domain.ports.ingestion import TextChunk
from app.domain.ports.retrieval import RetrievedChunk

_COLLECTION = "chunks"
_POINT_ID_NAMESPACE = UUID("8b3e1c4a-6f2d-4a7e-9c1b-2d5e6f708192")


def chunk_point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid5(_POINT_ID_NAMESPACE, f"{document_id}:{chunk_index}"))


class QdrantChunkStore:
    def __init__(self, *, url: str = "", client: QdrantClient | None = None) -> None:
        self._url = url
        self._client = client

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        client = self._get_client()
        if not client.collection_exists(_COLLECTION):
            return
        client.delete(
            collection_name=_COLLECTION,
            points_selector=Filter(
                must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]
            ),
        )

    def upsert_chunks(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None:
        if not chunks:
            return
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors length mismatch")
        vector_size = len(vectors[0])
        client = self._get_client()
        self._ensure_collection(client, vector_size)
        points = [
            PointStruct(
                id=chunk_point_id(document_id, chunk.chunk_index),
                vector=vector,
                payload={
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "filename": filename,
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        client.upsert(collection_name=_COLLECTION, points=points)

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
        if not ready:
            return []
        client = self._get_client()
        if not client.collection_exists(_COLLECTION):
            return []
        must = [
            FieldCondition(key="tenant_id", match=MatchValue(value=actor.tenant_id)),
            FieldCondition(key="document_id", match=MatchAny(any=ready)),
        ]
        if document_id is not None:
            must.append(
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            )
        response = client.query_points(
            collection_name=_COLLECTION,
            query=query_vector,
            query_filter=Filter(must=must),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        hits: list[RetrievedChunk] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                RetrievedChunk(
                    document_id=str(payload["document_id"]),
                    filename=str(payload["filename"]),
                    page=int(payload["page"]),
                    chunk_index=int(payload["chunk_index"]),
                    text=str(payload["text"]),
                    score=float(point.score),
                )
            )
        return hits

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self._url)
        return self._client

    def _ensure_collection(self, client: QdrantClient, vector_size: int) -> None:
        if client.collection_exists(_COLLECTION):
            return
        client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
