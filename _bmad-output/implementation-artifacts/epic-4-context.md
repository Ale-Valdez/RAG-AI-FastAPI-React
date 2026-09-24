# Epic 4 Context: Improve retrieval quality

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Answers get better through hybrid search, rerank, and query rewrite, while isolation and citations stay as they are. One shared `chunks` collection remains the only index, and every search stays inside the actor's tenant and its `ready` documents. Epic 1 auth, Epic 2 page-aware chunks, and Epic 3 retrieve-then-cite chat are assumed. Planning artifacts include the architecture spine and the epics inventory; no standalone PRD, product brief, or UX design contract was present.

## Stories

- Story 4.1: Improve search without a second index

## Requirements & Constraints

- Hybrid search, rerank, and query rewrite each sit behind the existing retrieve and embed ports. They share the `chunks` collection. A second collection and an unfiltered index are both out of bounds.
- A rewritten or hybrid query for tenant A still filters on `actor.tenant_id`. Eligible points come only from `ready` documents. An optional `document_id` still limits the query to that one `ready` document in the same tenant.
- Grounding citations stay `SourceRef` fields `document_id`, `filename`, `page`, and `chunk_index`. A score below `RAG_SCORE_THRESHOLD` (MVP default 0.70) still refuses to ground the answer. Empty or below-threshold retrieval still answers that it does not know.
- Query embedding keeps the same `OPENAI_EMBED_MODEL` as ingest. A query still returns at most `RAG_TOP_K` chunks (MVP default 5). Chunking stays an ingest-only step; the query path does not re-split text.
- Context assembly stays a step inside the chat use case. It is not a new port.
- Retrieval-quality use cases ship domain and application tests that use in-memory fakes and do not require Docker.
- Until roles exist, every member of a tenant may use every document in that tenant. This epic does not add roles, a second citation type, evaluation jobs, Postgres row-level security, or OIDC.

## Technical Decisions

- Hexagonal and sync: extract, chunk, embed, upsert, retrieve, and generate stay domain ports. Application use cases orchestrate them with sync `execute()`. Domain imports none of FastAPI, SQLAlchemy, Qdrant, LangChain, or OpenAI. LangChain is not the engine.
- New behavior lands as infrastructure adapters (hybrid, rerank, query rewrite) behind those same ports, implemented with `qdrant-client`, the official `openai` SDK, and owned code. Do not introduce a separate RAG engine that chat and ingestion call differently.
- One Qdrant collection, `chunks`, Cosine distance. Ingestion creates it if missing; this epic does not create another. Vector size is the embed model's size. Point id stays deterministic from `document_id` and `chunk_index`. Payload used for context and citations: `tenant_id`, `document_id`, `filename`, `page` (0-based), `chunk_index` (0-based), `text`.
- Retrieve and embed ports take `Actor` (or `actor.tenant_id` derived inside the use case). A client-supplied tenant is never the only filter. Cross-tenant retrieval is prohibited.
- `Actor`, the port contracts, and the single filtered collection stay stable so later production hardening can add isolation and operations without rewriting them.
- Product limits and model ids come from the environment. Secrets are never committed.

## Cross-Story Dependencies

- Depends on Epic 2 for `ready` documents and tenant-scoped `chunks` payloads. This epic does not ingest, delete, or re-embed.
- Depends on Epic 3 for the retrieve port, optional `document_id` filtering, score-threshold refusal, context assembly in chat, and `SourceRef` on assistant messages. Quality changes must keep that path working, including Tenant B never retrieving Tenant A's chunks.
- This epic has a single story, so there is no intra-epic story order.
- Evaluation stays a later slice and is not part of this epic. Epic 5 assumes `Actor`, the hexagonal ports, and the one `chunks` collection are still the isolation boundary after this work.
