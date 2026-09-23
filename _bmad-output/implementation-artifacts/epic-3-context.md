# Epic 3 Context: Ask a grounded question

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A tenant member can ask a question over the ready corpus, or over one ready document, and get a cited answer in a thread they can reopen. Retrieval stays inside that tenant: Tenant B never receives Tenant A's chunks. Epic 1 auth and the `/api/v1` `{data, error}` envelope, plus Epic 2 ready documents and `chunks` payloads, are assumed. Planning artifacts include architecture and the epics inventory; no standalone PRD, product brief, or UX design contract was present.

## Stories

- Story 3.1: Find ready chunks for a question
- Story 3.2: Ask a question and keep the thread

## Requirements & Constraints

- Every retrieval filter includes `actor.tenant_id`. Results contain no other tenant's points and no points from a document that is not `ready`.
- Query embedding uses the same `OPENAI_EMBED_MODEL` as ingest. A query returns at most `RAG_TOP_K` chunks (MVP default 5), each scoring at or above `RAG_SCORE_THRESHOLD` (MVP default 0.70).
- Omitted `document_id` searches all `ready` documents in the actor's tenant. A provided `document_id` searches that document only, and it must be `ready` and in the same tenant. Optional `document_id` does not bypass tenant isolation.
- The chat path retrieves, assembles that chunk text as context, then generates. The query path does not re-split text. Context assembly is an application step, not a new port.
- Each grounding chunk is a `SourceRef` (`document_id`, `filename`, `page`, `chunk_index`) on the assistant message. Do not invent a second citation type.
- Empty retrieval, or no chunk at or above `RAG_SCORE_THRESHOLD`, answers that it does not know and does not generate ungrounded content.
- A conversation stores `tenant_id` and `user_id`. Messages, including sources, reload for that user in that tenant. Another tenant cannot load the thread.
- Until roles exist, every user in a tenant may use every document in that tenant. Retrieval and chat use only `ready` documents.
- Product JSON is `{data, error}`. IDs are UUID strings (including conversations). Limits and secrets come from the environment. Each use case ships tests with in-memory fakes (no Docker for domain/application).
- Story 3.1 adds no chat HTTP route and no second Qdrant collection. Story 3.2's done check is the authenticated path: tenant, `ready` document, question, tenant-scoped retrieval, grounded answer, `SourceRef`s, persisted conversation, and Tenant B cannot retrieve Tenant A's document or chunks.
- Out of scope: hybrid search, rerank, query rewrite, roles/ACL, public signup, OIDC, Postgres RLS, non-PDF formats, collection-per-tenant, LangChain as the engine, and evaluation jobs.

## Technical Decisions

- Hexagonal and sync: retrieve and generate are domain ports; the chat use case orchestrates them with sync `execute()`. Domain imports none of FastAPI, SQLAlchemy, Qdrant, LangChain, or OpenAI. Product FastAPI routes are `def`. Use cases take `Actor`, never `Request`/`Response`.
- Infrastructure implements retrieve with `qdrant-client` and generate with the official `openai` SDK. The chat model id is `OPENAI_CHAT_MODEL` on the first generate adapter. LangChain is not imported from domain or application.
- One Qdrant collection, `chunks`, Cosine distance. Ingestion creates it if missing; retrieval and chat never create another. Vector size is the embed model's size. Payload used for context and citations: `tenant_id`, `document_id`, `filename`, `page` (0-based), `chunk_index` (0-based), `text`.
- Retrieve, upsert, and related ports take `Actor` (or `actor.tenant_id` derived inside the use case). A client-supplied tenant is never the only filter. HTTP builds `Actor` from verified JWT claims.
- Chat persistence is one shared Postgres schema. Conversations belong to a user; messages belong to a conversation. Every tenant-owned table, including messages, has `tenant_id`. Repositories filter by `actor.tenant_id`. RLS is not required yet. `Chunk` stays a Qdrant point, not a SQL table.
- Ask and reload live under `/api/v1`. HTTP maps unauthenticated to 401, `TenantIsolationError` to 403, `NotFoundError` to 404, and other domain errors to 409. The web feature talks only through the HTTP client and does not invent error codes or backend behavior.
- Slice order inside this epic: retrieval (port + Qdrant adapter, including optional `document_id`) then chat (conversation, generate, HTTP).

## Cross-Story Dependencies

- Depends on Epic 1 for Bearer JWT, `Actor` from verified claims, and the `{data, error}` envelope.
- Depends on Epic 2 for `ready` documents and tenant-scoped `chunks` payloads. This epic does not ingest, delete, or re-embed.
- Story 3.1 before 3.2: the retrieve port and filtered Qdrant adapter exist before the chat use case calls them. Chat must not embed search inside the generate adapter.
- Epic 4 later improves search behind the same retrieve and embed ports and the same collection, and must keep `SourceRef` and the score-threshold refusal unchanged.
