---
title: 'Find ready chunks for a question'
type: 'feature'
created: '2026-09-23'
status: 'done'
route: 'dispatch'
baseline_commit: '1bb09681c949bf94167f2a8c179a31576bb477aa'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Ingest stores tenant-scoped points in `chunks`, but a question cannot search them, so a later answer cannot be grounded in the caller's ready documents alone.

**Approach:** Add a retrieve port and a use case that embeds the question with the ingest model and returns at most the configured number of chunks that clear the score threshold and belong to the actor's ready documents.

## Boundaries & Constraints

**Always:**
- Every vector query filter includes `actor.tenant_id`. A client tenant is never the filter.
- Query embedding uses `OPENAI_EMBED_MODEL`, the same setting as ingest.
- At most `RAG_TOP_K` chunks (default 5). Each returned score is >= `RAG_SCORE_THRESHOLD` (default 0.70).
- Omitted `document_id` searches every `ready` document in the actor's tenant. A provided id limits the query to that document. If that document is missing, in another tenant, or not `ready`, retrieval raises `NotFoundError` and does not search.
- `ready` comes from `Document.status`. The Qdrant payload has no status.
- The use case takes `Actor` and is synchronous. Domain imports none of FastAPI, SQLAlchemy, Qdrant, LangChain, or OpenAI.
- Domain and application tests use in-memory fakes. No Docker.

**Never:**
- Chat HTTP, a generate adapter, or conversation persistence.
- A second Qdrant collection, or creating `chunks` during search.
- Changes to upsert, delete, `ProcessDocument`, document HTTP, or auth.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Corpus search | Actor A; ready points for A and B; A also has points on a non-ready document | Only A's ready chunks, at most `RAG_TOP_K`, each score >= threshold | N/A |
| One document | Actor A and a `document_id` of a ready document in A | Only that document's qualifying chunks; the filter still includes A's tenant | N/A |
| Low scores | Ready points exist but every score is below the threshold | Empty list | N/A |
| No ready documents | Documents are only pending, processing, or failed | Empty list; the vector store is not queried without a ready-document filter | N/A |
| Bad document id | `document_id` is missing, in another tenant, or not `ready` | No search | `NotFoundError` |

</frozen-after-approval>

## Code Map

Paths below are under `apps/api/`.

- `src/app/domain/ports/ingestion.py` — reuse `EmbeddingGenerator.embed`. Do not add search to `ChunkVectorStore`.
- `src/app/domain/ports/documents.py` — `get`, `list_for_tenant`. The use case picks `ready` ids.
- `src/app/domain/documents.py` — `DocumentStatus.READY` only. Do not change transitions.
- `src/app/domain/errors.py` — raise `NotFoundError`, as `DeleteDocument` does on a miss or a different tenant.
- `src/app/domain/actor.py` — compare `Actor.tenant_id` with `Document.tenant_id.value`.
- `src/app/domain/chat.py` — hits need `SourceRef` fields plus `text` and `score`.
- `src/app/application/documents/delete_document.py` — follow `execute(self, actor, ...)`.
- `src/app/infrastructure/ingestion/qdrant_chunk_store.py` — collection `chunks`. Payload: `tenant_id`, `document_id`, `filename`, `page`, `chunk_index`, `text`. Add search; do not create the collection.
- `src/app/infrastructure/config/settings.py` — add `rag_top_k` and `rag_score_threshold`. `.env.example` lacks `RAG_*` keys.
- `tests/fakes.py` — `InMemoryChunkStore` stores payload plus `vector`. `FakeEmbeddingGenerator` is deterministic.
- `tests/test_document_adapters.py` — copy the fake client in `test_qdrant_upsert_uses_uuid5_cosine_and_payload`. Leave upsert assertions unchanged.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/ports/retrieval.py` — port takes `Actor`, query vector, optional `document_id`, ready ids, `top_k`, and `score_threshold`, and returns hits — one port for story 3.2
- [x] `apps/api/src/app/application/retrieval/retrieve_chunks.py` — embed the question, resolve ready documents, then search — orchestration stays out of Qdrant
- [x] `apps/api/src/app/infrastructure/config/settings.py` and `.env.example` — add `RAG_TOP_K=5` and `RAG_SCORE_THRESHOLD=0.70`
- [x] `apps/api/src/app/infrastructure/ingestion/qdrant_chunk_store.py` — search `chunks` with tenant filter, ready-id filter, limit, and score cutoff
- [x] `apps/api/tests/fakes.py` and `apps/api/tests/test_retrieve_chunks.py` — in-memory cosine search and matrix tests for both tenants — no Docker
- [x] `apps/api/tests/test_document_adapters.py` — assert the Qdrant filter includes `tenant_id` and search does not create a collection

**Acceptance Criteria:**
- Given chunks for tenants A and B, when retrieval runs as A, then every query filter includes A's `tenant_id` and no returned point is from B or from a document that is not `ready`
- Given defaults 5 and 0.70, when retrieval runs, then it returns at most 5 chunks, each scoring at or above 0.70, embedded with `OPENAI_EMBED_MODEL`
- Given a `document_id` of a ready document in the actor's tenant, when retrieval runs, then the port and the Qdrant adapter limit the query to that document; omitted, it covers that tenant's ready documents
- Given a `document_id` that is missing, in another tenant, or not `ready`, when retrieval runs, then it raises `NotFoundError` and does not search
- Given this story, when it is implemented, then there is no chat HTTP route and no second Qdrant collection

## Implementation Notes

## Spec Change Log

## Review Triage Log

- `low` — `QdrantChunkStore.search` indexes payload keys directly, so a missing key raises. Ingest always writes `tenant_id`, `document_id`, `filename`, `page`, `chunk_index`, and `text`, and the query filter already requires the actor's tenant and the ready ids. A score below the threshold is not shown: `query_points` is called with `score_threshold`. Rejected: everyday retrieval does not meet a corrupt point, and the fix would add guards.
- `false` — `RetrieveChunks` returns the port's list. Both `QdrantChunkStore.search` and `InMemoryChunkStore.search` apply `top_k` and `score_threshold`. A retriever that ignored them is not a path this story builds.
- `low` — `execute` embeds a blank question. There is no chat route in this story, so a user does not send that input. Rejected: rejecting whitespace would add a branch the spec does not require.
- `low` — `rag_top_k` and `rag_score_threshold` are unconstrained, and a negative `top_k` slices the fake or is rejected by Qdrant. Defaults are 5 and 0.70. Rejected: only a bad environment value reaches this, and the fix is new validation.
- `low` — equal scores keep client order in Qdrant and a sort key only in the fake. The spec caps the count and the score; it does not choose which tied chunk is dropped. Rejected: the fix adds an ordering rule callers were not given.
- `false` — `RetrievedChunk` carries `SourceRef` fields plus `text` and `score`, which is the hit shape in the code map. This story does not build chat citations.
- `false` — `RetrieveChunks` takes `top_k` and `score_threshold` from its caller. This story adds no retrieve route, so nothing in the process reads the new settings yet. Tests pass the defaults in.
- `medium` — in-memory keys and the existing Qdrant point id are `document_id:chunk_index`, so the same index in two tenants cannot both exist. That id function is unchanged from ingest. Deferred as pre-existing. Real documents use distinct ids, so the new tenant filter is not what drops the other tenant's point.
- `low` — a non-numeric or missing Qdrant payload aborts the whole `search` loop. Same corrupt-point case as the first row. Rejected: the fix is a skip guard, and ingest does not write those payloads.
- `low` — `query_points(limit=top_k)` receives `top_k` unchanged, so zero or negative fails in the client. Same configuration case as the settings row. Rejected.
- `false` — `RetrieveChunks` passes `embeddings.embed([question])[0]`. `OpenAIEmbeddingGenerator` and `FakeEmbeddingGenerator` return one vector per input string. Nothing in this story calls `search` with an empty vector.
- `low` — `ranked[:top_k]` on a negative `top_k` keeps all but the tail. Same configuration case. Rejected.
- `low` — the in-memory fake raises if a planted point has a non-numeric vector. Tests plant numeric vectors, and production upsert writes floats. Rejected: only a hand-built fake point hits this.
- `low` — a NaN cosine fails the `< threshold` check and would be kept. Embeddings from the ingest generator are finite. Rejected.
- `low` — a whitespace question is still embedded. Same blank-question case. Rejected.
- `low` — ready ids are captured before `embed`, so a document that leaves `ready` during that call can still be in the filter. Re-ingest deletes points before the new upsert, and this story has no concurrent caller. Rejected: closing the window adds a second status read.
- `medium` — `test_qdrant_search_filters_tenant_and_does_not_create_collection` never asserts `query`. Dropping the question vector would still pass, and `query_points` with `query=None` returns the first `limit` points. Patch: assert the vector on both calls.
- `low` — the empty `ready_ids` call runs only after `collection_exists` is false, so deleting the early return still passes. `RetrieveChunks` does not call `search` in that case. Patch: assert the early return while the collection exists.

## Design Notes

`QdrantChunkStore` implements the retrieve port and upsert. The use case passes ready ids in; a bad `document_id` raises `NotFoundError` before search. The fake ranks by cosine, drops scores under the threshold, and keeps at most `top_k`.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` -- expected: existing tests pass; retrieve tests pass; no Docker
