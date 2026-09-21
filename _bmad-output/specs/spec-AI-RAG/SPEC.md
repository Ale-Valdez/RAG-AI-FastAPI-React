---
id: SPEC-AI-RAG
companions:
  - architecture-diagrams.md
  - stack.md
  - slice-map.md
  - config.md
  - http-envelope.md
  - ../../planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md
  - ../../../AGENTS.md
sources:
  - ../../../docs/domain.md
  - ../../../docs/rag.md
  - ../../../docs/architecture.md
  - ../../../docs/conventions.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# AI-RAG Knowledge Assistant

## Why

Organizations need an assistant that answers from **their** documents, not generic model knowledge. AI-RAG is a multi-tenant knowledge assistant: each tenant's corpus is a security boundary, members upload PDFs, and answers must cite the pages that grounded them. Architectural decisions AD-1 through AD-12 in the adopted spine are already made and must not be reopened by epics.

## Capabilities

MVP is CAP-1 through CAP-8 (slices `identity-and-tenancy` → `chat`). CAP-9 through CAP-11 are later slices.

- **CAP-1**
  - **intent:** A person can authenticate as a local user of a tenant and act as that tenant member for every later feature.
  - **success:** `python -m app.cli bootstrap` creates one `Tenant` and one password-authenticated `User` from `BOOTSTRAP_*` env vars (password stored hashed). Login issues a Bearer JWT whose claims include `user_id` and `tenant_id` as strings; HTTP builds `Actor` only from those verified claims. Missing or invalid token → 401.

- **CAP-2**
  - **intent:** A tenant member can add PDF files to the shared tenant corpus.
  - **success:** Upload creates a `pending` `Document` visible only inside that tenant, preserving the original filename; first slices reject non-PDF and reject files over `MAX_DOCUMENT_SIZE_MB`.

- **CAP-3**
  - **intent:** A tenant member can see whether each document is waiting, in progress, usable, or failed.
  - **success:** Wire status is `pending` | `processing` | `ready` | `failed`; HTTP upload leaves `pending`; re-ingest may write `ready`|`failed` → `pending`; only `ProcessDocument` writes `processing` / `ready` / `failed`.

- **CAP-4**
  - **intent:** The system can turn an uploaded PDF into page-aware chunks that tenant can search.
  - **success:** A processed PDF becomes `ready` with points in Qdrant collection `chunks` whose payload includes `tenant_id`, `document_id`, `filename`, `page`, `chunk_index`, and `text`; more than `MAX_DOCUMENT_PAGES` fails ingest; a failed extract marks the document `failed` and it is not retrieved; at most `MAX_CONCURRENT_INGESTIONS_PER_TENANT` ingestions run per tenant at once.

- **CAP-5**
  - **intent:** The system can find relevant chunks for a question using only the actor's tenant and only ready documents.
  - **success:** Retrieval with tenant A's `Actor` never returns tenant B's points or non-ready documents; every query filter includes `actor.tenant_id`; ingest and query-embed use the same `OPENAI_EMBED_MODEL`; results are limited to `RAG_TOP_K` and scores at or above `RAG_SCORE_THRESHOLD`.

- **CAP-6**
  - **intent:** A tenant member can ask a question over the tenant corpus and receive an answer grounded in retrieved chunks.
  - **success:** The chat use case retrieves, assembles chunk text as context, then generates. Omitted `document_id` searches all `ready` documents in the actor tenant; provided `document_id` searches that document only (must be `ready` and same tenant). Assistant messages include `SourceRef` (`document_id`, `filename`, `page`, `chunk_index`) for the grounding chunks; empty retrieval or no hit above `RAG_SCORE_THRESHOLD` answers that it does not know and does not generate ungrounded content.

- **CAP-7**
  - **intent:** A tenant member can keep a persisted question-answer thread.
  - **success:** A `Conversation` stores `tenant_id` and `user_id`; messages (including sources) reload for that user in that tenant; another tenant cannot load the thread.

- **CAP-8**
  - **intent:** A tenant member can remove a document from the corpus or replace its content so answers no longer use stale chunks.
  - **success:** Delete removes the SQL row, the S3 object at `tenant_id/document_id/filename`, and all Qdrant points for that `document_id`. Re-ingest keeps the same `document_id`, resets `ready` → `pending` (failed documents use the same entry), then `ProcessDocument` runs `pending` → `processing` → `ready` or `processing` → `failed`. Before upsert, existing Qdrant points for that `document_id` are deleted so old fragments do not merge with new.

- **CAP-9** *(later — `rag-engineering`)*
  - **intent:** Retrieval quality can be improved without changing isolation or citation identity.
  - **success:** Hybrid search, rerank, and query rewrite sit behind the same retrieve/embed ports and the same `chunks` collection; no second unfiltered index.

- **CAP-10** *(later — `evaluation`)*
  - **intent:** The pipeline can be evaluated by jobs that reuse the existing worker rule.
  - **success:** Evaluation enqueues `Actor` as flat job JSON (`tenant_id`, `user_id`, plus job ids) and calls application use cases; Redis + Celery remains the only async fabric.

- **CAP-11** *(later — `production-hardening`)*
  - **intent:** Production can add stronger isolation, identity, and operations without rewriting product ports.
  - **success:** Postgres RLS, OIDC, observability, and managed topology are add-ons; `Actor`, hexagonal ports, and one filtered collection remain.

## Constraints

- Architectural decisions **AD-1 through AD-12** in `ARCHITECTURE-SPINE.md` are binding, including AD-10's `{data, error}` body on `/api/v1` (see `http-envelope.md`). Epics do not invent a competing architecture or stack.
- Tenant isolation is a **security boundary**. `tenant_id` comes from authenticated `Actor` (JWT claims or job record), never from an untrusted client field as the only filter. Cross-tenant retrieval is prohibited. Authenticated-but-not-allowed (including `TenantIsolationError`) is 403.
- Hexagonal layout is binding: `domain` imports none of FastAPI, SQLAlchemy, Celery, Qdrant, LangChain, OpenAI, boto3, or web; `application` imports `domain` only; `apps/web` talks to the HTTP API only. No empty layer folders. One vertical slice at a time, in this order: identity-and-tenancy → documents → ingestion → retrieval → chat → rag-engineering → evaluation → production-hardening. Do not skip ahead of identity-and-tenancy.
- Product `execute()` methods and ports are **sync**. FastAPI product routes are `def`. SQLAlchemy uses a sync `Session`. Existing `GetReadiness` may stay async until rewritten; it is not a product template.
- HTTP and the worker share the composition root and the same use cases. The bootstrap CLI is another adapter on that composition root. `Document` is the only ingest lifecycle. Upload persists `pending` and enqueues; it does not call `mark_processing`. Re-ingest may write `ready`|`failed` → `pending` and enqueue. Job JSON is flat strings: `tenant_id`, `user_id`, `document_id`. Redis + Celery is the only async fabric.
- Extract, chunk, embed, upsert, retrieve, and generate are domain ports. LangChain is not the engine. First corpus format is PDF. One embedding model from env (`OPENAI_EMBED_MODEL`) for both upsert and query-embed. Chunking runs only at ingest; the query path must not re-split text. Context assembly is an application step in chat, not a new port.
- Bytes go through one domain port `DocumentBytes`. Adapter speaks the S3 API. One bucket. Object key is `tenant_id/document_id/filename`. Garage is added with the documents slice (not in `compose.yaml` today). Production may point the same adapter at Amazon S3.
- One Qdrant collection named `chunks`. Distance Cosine. Ingestion creates it if missing; retrieval and chat never create a different collection. Point id is deterministic from `document_id` and `chunk_index`. Payload: `tenant_id` string, `document_id` string, `filename` string, `page` int (0-based), `chunk_index` int (0-based), `text` string. Re-ingest deletes that document's points before upsert.
- This API issues JWTs for local `User` rows, signed with `jwt_secret`. Web sends `Authorization: Bearer` and keeps the token in memory, not `localStorage`. Jobs do not carry the JWT. First tenant/admin is provisioned by bootstrap CLI, not public signup. Password is stored hashed. No `Role` on `Actor`.
- One Postgres schema. Every tenant-owned table has `tenant_id` (including messages). Persistence is SQLAlchemy 2.x + Alembic in infrastructure only. SQL table for documents is `documents`. Postgres RLS is not required yet.
- Domain raises `DomainError` subclasses. Missing resources raise `NotFoundError`. HTTP maps: unauthenticated / missing / invalid token → 401; `TenantIsolationError` → 403; `NotFoundError` → 404; other `DomainError` → 409. Product `/api/v1` JSON is always `{"data": ..., "error": ...}`: success has a data object and `"error": null`; failure has `"data": null` and `error: {"code": "<STABLE_CODE>", "message": "<human>"}`. Web reads status plus `error.code` / `error.message`; it does not invent codes. Use cases never take Request/Response.
- Until a slice adds roles, every user in a tenant may use every document in that tenant. Retrieval and chat use only `ready` documents. Optional per-question `document_id` narrows to one ready document in that tenant; it does not bypass tenant isolation.
- MVP ingest/retrieval limits and bootstrap values come from environment only (see `config.md`). Never commit secrets.
- IDs are UUID strings created in application/domain. Dates are UTC ISO-8601 in JSON. Each use case ships tests; domain/application tests use in-memory fakes (no Docker). Python type hints required. TypeScript `strict`. Validate untrusted input at HTTP and worker adapters.
- Named environment is Docker Compose. Cloud providers, managed S3 topology, and orchestrators are not named for MVP. Stack pins live in `stack.md`.

## Non-goals

- Roles or in-tenant document ACL in MVP (tenant membership is enough; bootstrap "admin" is the first password user, not a role on `Actor`).
- Public self-register, invite-links, or an IdP for the first tenant.
- OIDC, cookies, sessions, refresh, or revocation in MVP.
- Postgres RLS in MVP.
- Non-PDF corpus formats in first document/ingestion slices.
- Hybrid retrieval, rerank, query rewrite, or context evaluation in MVP.
- Kafka or a domain-event bus.
- Collection-per-tenant, schema-per-tenant, or bucket-per-tenant.
- LangChain as the RAG engine (including LCEL in infrastructure).
- Cookie/session auth, or storing the access token in `localStorage`.
- Async product use cases or ports.
- API-local disk for document bytes.
- Forwarding the JWT to the worker.
- Structured logging/tracing as a first-slice requirement (`/health` and `/ready` already exist).
- k8s, managed Postgres, or Amazon S3 topology as a named MVP environment.

## Success signal

A member of tenant A uploads a PDF (within size/page limits), it becomes `ready`, they ask a question (whole corpus or one `document_id`), and the assistant answers with `SourceRef` values that match that document's pages. Hits below `RAG_SCORE_THRESHOLD` do not ground. A member of tenant B asking the same question cannot list, retrieve, or be answered from tenant A's document. Re-ingest of that PDF keeps the same `document_id` and does not leave old chunks mixed with new.

## Assumptions

- MVP ship is CAP-1..CAP-8; CAP-9..CAP-11 follow the later slices in `slice-map.md`.
- Conversation ownership follows the domain ERD: a thread belongs to one `user_id` inside a tenant, not a tenant-wide inbox.
- `FAILED` → `PENDING` is the same re-ingest entry as `READY` → `PENDING`, so a failed document can retry without a new id.
- Additional documents beyond two in-flight ingestions stay `pending` until a tenant slot frees; they are not a second concurrent job.
- `/health` and `/ready` stay at their existing paths and outside the `/api/v1` `{data, error}` envelope.
- Password hashing library is chosen at the identity slice (same class of decision as the PDF extractor).
- Installed lockfile/compose versions are seed; intended adds land when the owning slice needs them. Version bumps are not product invariants.
- Chat model id is config (`OPENAI_CHAT_MODEL`) at the first generate adapter, not part of the vector schema.
- AGENTS.md still lists LangChain next to in-use infrastructure frameworks as a domain-import ban; this spec follows AD-5: LangChain is not the engine.
- Success `data` is a JSON object, not a top-level array; list endpoints nest the collection inside `data`. `error.code` is uppercase snake_case; `DOCUMENT_NOT_FOUND` shows the pattern, not a closed catalog.