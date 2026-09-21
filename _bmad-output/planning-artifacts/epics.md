---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/specs/spec-AI-RAG/SPEC.md
  - _bmad-output/specs/spec-AI-RAG/architecture-diagrams.md
  - _bmad-output/specs/spec-AI-RAG/stack.md
  - _bmad-output/specs/spec-AI-RAG/slice-map.md
  - _bmad-output/specs/spec-AI-RAG/config.md
  - _bmad-output/specs/spec-AI-RAG/http-envelope.md
  - _bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md
  - _bmad-output/specs/spec-AI-RAG/stories.yaml
---

# AI-RAG - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for AI-RAG, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: `python -m app.cli bootstrap` creates one Tenant and one password-authenticated User from `BOOTSTRAP_TENANT_NAME`, `BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD`. The password is stored only as a hash. "Admin" is that account, not a Role on Actor.

FR2: Login issues a Bearer JWT whose claims include `user_id` and `tenant_id` as strings. HTTP builds Actor only from those verified claims.

FR3: A missing or invalid token on a product route returns HTTP 401.

FR4: An authenticated tenant member can upload a PDF into that tenant's shared corpus. The document is created `pending`, keeps the original filename, and is invisible to other tenants.

FR5: Upload rejects a non-PDF and rejects a file over `MAX_DOCUMENT_SIZE_MB` (MVP default 20).

FR6: A tenant member can list documents and read each status as `pending`, `processing`, `ready`, or `failed`.

FR7: HTTP upload leaves the document `pending` and enqueues processing. It does not write `processing`. Re-ingest may write `ready` or `failed` back to `pending` and enqueue. Only ProcessDocument writes `processing`, `ready`, or `failed`.

FR8: A processed PDF becomes `ready` with points in the Qdrant collection `chunks`. Each payload includes `tenant_id`, `document_id`, `filename`, `page` (0-based), `chunk_index` (0-based), and `text`.

FR9: A PDF with more than `MAX_DOCUMENT_PAGES` (MVP default 100) fails ingest. A failed extract marks the document `failed`. Failed documents are not retrieved.

FR10: At most `MAX_CONCURRENT_INGESTIONS_PER_TENANT` (MVP default 2) ingestions run per tenant at once. Additional documents stay `pending` until a slot frees.

FR11: Retrieval with tenant A's Actor never returns tenant B's points or points from documents that are not `ready`. Every query filter includes `actor.tenant_id`.

FR12: Ingest embed and query embed use the same `OPENAI_EMBED_MODEL`. A query returns at most `RAG_TOP_K` chunks (MVP default 5) with scores at or above `RAG_SCORE_THRESHOLD` (MVP default 0.70).

FR13: A member can ask a question over the tenant corpus. Omitted `document_id` searches all `ready` documents in the actor tenant. A provided `document_id` searches that document only, and that document must be `ready` and in the same tenant.

FR14: The chat use case retrieves, assembles chunk text as context, then generates. Assistant messages include a SourceRef (`document_id`, `filename`, `page`, `chunk_index`) for each grounding chunk.

FR15: When retrieval is empty or no hit is at or above `RAG_SCORE_THRESHOLD`, the assistant answers that it does not know and does not generate ungrounded content.

FR16: A Conversation stores `tenant_id` and `user_id`. Messages, including sources, reload for that user in that tenant. Another tenant cannot load the thread.

FR17: Delete removes the SQL row, the S3 object at `tenant_id/document_id/filename`, and all Qdrant points for that `document_id`.

FR18: Re-ingest keeps the same `document_id`. It resets `ready` or `failed` to `pending`, then ProcessDocument runs `pending` → `processing` → `ready`, or `processing` → `failed`. Existing Qdrant points for that `document_id` are deleted before the new upsert.

FR19: Later (`rag-engineering`): hybrid search, rerank, and query rewrite sit behind the same retrieve and embed ports and the same `chunks` collection. No second unfiltered index.

FR20: Later (`evaluation`): evaluation jobs enqueue Actor as flat JSON (`tenant_id`, `user_id`, plus job ids) and call application use cases. Redis + Celery remains the only async fabric.

FR21: Later (`production-hardening`): Postgres RLS, OIDC, observability, and managed topology can be added while Actor, the hexagonal ports, and the one filtered collection stay.

### NonFunctional Requirements

NFR1: Tenant isolation is a security boundary. `tenant_id` comes from the authenticated Actor (JWT claims or the job record), never from an untrusted client field used as the only filter. Cross-tenant retrieval is prohibited. Authenticated-but-not-allowed, including `TenantIsolationError`, is HTTP 403.

NFR2: Hexagonal layout is binding. Domain imports none of FastAPI, SQLAlchemy, Celery, Qdrant, LangChain, OpenAI, boto3, or web. Application imports domain only. The web app talks to the HTTP API only. No empty layer folders. One vertical slice at a time: identity-and-tenancy → documents → ingestion → retrieval → chat → rag-engineering → evaluation → production-hardening.

NFR3: Product `execute()` methods and ports are sync. FastAPI product routes are `def`. SQLAlchemy uses a sync Session. Existing `GetReadiness` may stay async until rewritten and is not a product template.

NFR4: Product `/api/v1` JSON is always `{data, error}`. Success has a data object and `"error": null`. Failure has `"data": null` and `error: {"code": "<STABLE_CODE>", "message": "<human>"}`. `data` is an object, never a top-level array. `error.code` is uppercase snake_case. HTTP status mapping is 401, 403, 404, 409. `/health` and `/ready` stay on their current paths and outside this envelope. The web client reads status plus `error.code` and `error.message` and does not invent codes.

NFR5: IDs are UUID strings created in application or domain. JSON dates are UTC ISO-8601. Product limits, bootstrap values, and secrets come from the environment only and are never committed.

NFR6: Each use case ships tests. Domain and application tests use in-memory fakes and do not require Docker. Python type hints are required. TypeScript is `strict`. Untrusted input is validated at the HTTP and worker adapters.

NFR7: The named environment is Docker Compose (`postgres`, `redis`, `qdrant`, `api`, `worker`, `web`, plus Garage when documents land). One Postgres schema. Every tenant-owned table has `tenant_id`, including messages. One Qdrant collection named `chunks`, distance Cosine. One S3 bucket. Object key is `tenant_id/document_id/filename`.

NFR8: Chunking runs only at ingest. The query path does not re-split text. Context assembly is an application step in chat, not a new port. One embedding model is used for both upsert and query-embed.

NFR9: This API issues JWTs for local User rows, signed with `jwt_secret`. The web app sends `Authorization: Bearer` and keeps the token in memory, not `localStorage`. Jobs do not carry the JWT. There is no public self-register in MVP. There is no Role on Actor.

NFR10: Until a slice adds roles, every user in a tenant may use every document in that tenant. Retrieval and chat use only `ready` documents. An optional `document_id` does not bypass tenant isolation.

### Additional Requirements

- The repo is brownfield on blueprint `ai-rag-fastapi-react` 1.0. Epic 1 Story 1 extends the existing API and web seed. It does not scaffold a new repository. `/health` and `/ready` already exist.
- HTTP and the worker share the composition root and the same use cases. The bootstrap CLI is another adapter on that composition root. `Document` is the only ingest lifecycle. Job JSON is flat strings: `tenant_id`, `user_id`, `document_id`. Redis + Celery is the only async fabric.
- Extract, chunk, embed, upsert, retrieve, and generate are domain ports. LangChain is not the engine. The first corpus format is PDF. The PDF extractor library is chosen in the ingestion slice. The password-hashing library is chosen in the identity slice. The chat model id is `OPENAI_CHAT_MODEL` at the first generate adapter.
- Bytes go through the domain port `DocumentBytes`. The adapter speaks the S3 API. Garage (`dxflrs/garage:v2.4.1`) is added with the documents slice. It is not in `compose.yaml` today. Production may point the same adapter at Amazon S3.
- Ingestion creates the `chunks` collection if it is missing. Retrieval and chat do not create a different collection. Point id is deterministic from `document_id` and `chunk_index`.
- Domain raises `DomainError` subclasses. Missing resources raise `NotFoundError`. Product routes replace the existing FastAPI `detail` handlers with the `{data, error}` envelope. `DOCUMENT_NOT_FOUND` is the code pattern, not a closed catalog.
- Architectural decisions AD-1 through AD-12 are binding. Stack pins live in `stack.md`. Version bumps are not product invariants.
- Agreed MVP story boundaries in `stories.yaml` constrain later epic design. Story 1 establishes identity and the `/api/v1` envelope, inherited by every later story. Story 2 is upload and list only, status stays `pending`, and it adds Garage. Story 3 owns ProcessDocument, page and concurrency limits, and all delete, replace, and re-ingest behavior across SQL, S3, and Qdrant. Story 4 puts `document_id` filtering in the retrieve port and the Qdrant adapter and adds no chat HTTP route. Story 5's done check is the authenticated path: tenant, READY document, question, tenant-scoped retrieval, grounded answer, SourceRefs, persisted conversation, plus Tenant B cannot retrieve Tenant A's document or chunks.
- FR19 and FR21 stay out of the five MVP stories. FR20 (evaluation) stays in the inventory and has no epic in this breakdown.
- MVP non-goals stay out of early stories: roles and in-tenant ACL, public signup, OIDC, cookies, sessions, refresh, revocation, Postgres RLS, non-PDF formats, hybrid retrieval, Kafka, collection-per-tenant, schema-per-tenant, bucket-per-tenant, LangChain as the engine, async product use cases, API-local disk, forwarding the JWT to the worker, structured logging as a first-slice requirement, and a named k8s or managed-cloud topology.

### UX Design Requirements

None. The confirmed input set includes no UX design contract. React page scope was left out of `stories.yaml`.

### FR Coverage Map

FR1: Epic 1 — Bootstrap one tenant and one password-hashed user
FR2: Epic 1 — Bearer JWT and Actor from verified claims
FR3: Epic 1 — Missing or invalid token returns 401
FR4: Epic 2 — Upload a PDF into the tenant corpus
FR5: Epic 2 — Reject non-PDF and oversize uploads
FR6: Epic 2 — List document status
FR7: Epic 2 — Upload leaves pending; only ProcessDocument writes processing, ready, or failed
FR8: Epic 2 — Ready PDF with page-aware chunk payload
FR9: Epic 2 — Page limit and failed extract
FR10: Epic 2 — Per-tenant concurrent ingestion cap
FR11: Epic 3 — Retrieval stays inside the actor tenant and ready documents
FR12: Epic 3 — Same embed model, top-k, and score threshold
FR13: Epic 3 — Ask over the corpus or one document
FR14: Epic 3 — Grounded answer with SourceRefs
FR15: Epic 3 — Below threshold answers that it does not know
FR16: Epic 3 — Persisted conversation for that user and tenant
FR17: Epic 2 — Delete across SQL, S3, and Qdrant
FR18: Epic 2 — Re-ingest on the same document_id after deleting old points
FR19: Epic 4 — Hybrid search, rerank, and query rewrite behind the same ports
FR20: Excluded from this breakdown — evaluation epic declined; requirement stays in the inventory
FR21: Epic 5 — Production hardening without rewriting Actor, ports, or the collection

## Epic List

### Epic 1: Sign in to your organization
A person can authenticate as a member of a tenant, and every later action is scoped to that tenant. This epic also establishes the `/api/v1` `{data, error}` contract.
**FRs covered:** FR1, FR2, FR3

### Epic 2: Build and maintain the tenant corpus
A member can add PDFs, see them become ready, and remove or replace them so old chunks do not linger.
**FRs covered:** FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR17, FR18

### Epic 3: Ask a grounded question
A member can ask over the ready corpus, or over one document, and get a cited answer in a thread they can reopen. Tenant B cannot retrieve Tenant A's chunks.
**FRs covered:** FR11, FR12, FR13, FR14, FR15, FR16

### Epic 4: Improve retrieval quality
Answers can get better through hybrid search, rerank, and query rewrite without a second index or a change to isolation and citations.
**FRs covered:** FR19

### Epic 5: Harden for production
Production can add stronger isolation, identity, and operations without rewriting Actor, the ports, or the one collection.
**FRs covered:** FR21

## Epic 1: Sign in to your organization

A person can authenticate as a member of a tenant, and every later action is scoped to that tenant. This epic also establishes the `/api/v1` `{data, error}` contract.

### Story 1.1: Bootstrap a tenant and sign in

As an operator,
I want to create the first tenant and sign in as its member,
So that every later action is scoped to that tenant.

**Acceptance Criteria:**

**Given** `BOOTSTRAP_TENANT_NAME`, `BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD` are set
**When** the operator runs `python -m app.cli bootstrap`
**Then** one Tenant and one User exist
**And** the password is stored only as a hash
**And** "admin" is that account, not a Role on Actor

**Given** that user exists
**When** they log in with email and password
**Then** the API issues a Bearer JWT whose claims include `user_id` and `tenant_id` as strings
**And** the body is `{ "data": { ... }, "error": null }`

**Given** a product route under `/api/v1`
**When** the request has a missing or invalid token
**Then** the status is 401
**And** the body is `{ "data": null, "error": { "code": "<STABLE_CODE>", "message": "<human>" } }`

**Given** a valid Bearer token
**When** a product route runs
**Then** HTTP builds Actor only from the verified claims
**And** a use case that touches a tenant resource takes that Actor
**And** the web client keeps the token in memory

**Given** a domain error on a product route
**When** the HTTP adapter maps it
**Then** unauthenticated is 401, `TenantIsolationError` is 403, `NotFoundError` is 404, and any other `DomainError` is 409
**And** `/health` and `/ready` stay outside the `{data, error}` envelope
**And** the existing FastAPI `detail` handlers are replaced for `/api/v1`

**Given** the identity use cases
**When** their tests run
**Then** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `domain/actor.py` — Actor (`tenant_id`, `user_id`)
- `domain/errors.py` — authentication and authorization errors, beside the existing `DomainError` and `TenantIsolationError`; add `NotFoundError`
- `domain/ports/auth.py` — auth port
- `application/auth/models.py` — use-case inputs and results for bootstrap and login
- `application/auth/` — bootstrap and login use cases, each with `execute`
- `infrastructure/http/dependencies/auth.py` — build Actor from the verified JWT
- `infrastructure/http/responses/api_response.py` — `{data, error}`
- `infrastructure/auth/jwt.py` — sign and verify with `jwt_secret`

## Epic 2: Build and maintain the tenant corpus

A member can add PDFs, see them become ready, and remove or replace them so old chunks do not linger.

### Story 2.1: Upload a PDF and see it waiting

As a tenant member,
I want to upload a PDF and see it listed as waiting,
So that my file is in the tenant corpus and not visible to anyone else.

**Acceptance Criteria:**

**Given** a signed-in member
**When** they upload a PDF within `MAX_DOCUMENT_SIZE_MB`
**Then** a Document is stored with status `pending` and the original filename
**And** the bytes are stored at `tenant_id/document_id/filename` in the one S3 bucket
**And** a job is enqueued with flat `tenant_id`, `user_id`, and `document_id`
**And** the upload response uses `{data, error}` and does not set status to `processing`

**Given** that member
**When** they list documents
**Then** they see that document with status `pending`
**And** a member of another tenant receives neither the document nor its bytes

**Given** a file that is not a PDF, or a PDF over `MAX_DOCUMENT_SIZE_MB` (MVP default 20)
**When** they upload it
**Then** the API rejects it
**And** no Document row and no S3 object are created

**Given** this story
**When** its routes are implemented
**Then** there is no delete, replace, or re-ingest route
**And** Garage (`dxflrs/garage:v2.4.1`) is added to Compose with S3 settings on `api` and `worker`
**And** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `domain/documents.py` — the existing `Document` and `pending` status
- `application/documents/` — upload and list use cases, each with `execute`
- `infrastructure/http/` — upload and list routes under `/api/v1`
- `infrastructure/` S3 adapter for `DocumentBytes`
- Compose service `garage`

### Story 2.2: Make a PDF ready, replace it, or remove it

As a tenant member,
I want an uploaded PDF to become searchable, and to replace or remove it completely,
So that answers use the current pages and old chunks do not linger.

**Acceptance Criteria:**

**Given** a `pending` document and an enqueued job for its tenant
**When** `ProcessDocument` runs
**Then** it is the only writer of `processing`, `ready`, and `failed`
**And** it loads the document, checks the tenant, then moves `pending` → `processing` → `ready` or `processing` → `failed`
**And** a `ready` PDF has points in the Qdrant collection `chunks`
**And** each payload includes `tenant_id`, `document_id`, `filename`, `page` (0-based), `chunk_index` (0-based), and `text`
**And** the point id is deterministic from `document_id` and `chunk_index`
**And** ingest uses `OPENAI_EMBED_MODEL`

**Given** a PDF with more pages than `MAX_DOCUMENT_PAGES` (MVP default 100), or an extract that fails
**When** `ProcessDocument` runs
**Then** the document is `failed`
**And** it is not retrievable

**Given** a tenant already has `MAX_CONCURRENT_INGESTIONS_PER_TENANT` documents in `processing` (MVP default 2)
**When** another document is still `pending`
**Then** that document stays `pending` until a slot frees

**Given** a `ready` or `failed` document
**When** the member re-ingests it
**Then** the same `document_id` moves back to `pending` and a job is enqueued
**And** `ProcessDocument` deletes existing Qdrant points for that `document_id` before the new upsert

**Given** a document in the member's tenant
**When** the member deletes it
**Then** the SQL row, the S3 object at `tenant_id/document_id/filename`, and all Qdrant points for that `document_id` are removed
**And** another tenant cannot delete it

**Given** the ingestion use cases
**When** their tests run
**Then** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `application/documents/` — `ProcessDocument`, delete, and re-ingest use cases
- `domain/documents.py` — `ready` and `failed` may return to `pending`
- `infrastructure/worker/` — Celery adapter calls `ProcessDocument`
- `infrastructure/` — extract, chunk, embed, and Qdrant upsert ports

## Epic 3: Ask a grounded question

A member can ask over the ready corpus, or over one document, and get a cited answer in a thread they can reopen. Tenant B cannot retrieve Tenant A's chunks.

### Story 3.1: Find ready chunks for a question

As a tenant member,
I want a question to find only my tenant's ready chunks,
So that an answer can be grounded in my documents alone.

**Acceptance Criteria:**

**Given** chunks for tenant A and tenant B in the existing `chunks` collection
**When** retrieval runs with tenant A's Actor
**Then** every query filter includes `actor.tenant_id`
**And** the result contains no point from tenant B
**And** the result contains no point from a document that is not `ready`

**Given** `RAG_TOP_K` is 5 and `RAG_SCORE_THRESHOLD` is 0.70
**When** retrieval runs
**Then** it returns at most 5 chunks
**And** every returned chunk scores at or above 0.70
**And** the query embedding uses the same `OPENAI_EMBED_MODEL` as ingest

**Given** an optional `document_id`
**When** retrieval runs with that id
**Then** the retrieve port and the Qdrant adapter limit the query to that document
**And** the document must be `ready` and in the actor's tenant
**And** an omitted `document_id` searches all ready documents in that tenant

**Given** this story
**When** it is implemented
**Then** it does not add a chat HTTP route
**And** it does not create a second Qdrant collection
**And** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `domain/` — retrieve port, including optional `document_id`
- `infrastructure/` — Qdrant adapter for that port
- tests — two tenants, ready and non-ready documents

### Story 3.2: Ask a question and keep the thread

As a tenant member,
I want to ask a question and reopen the cited answer later,
So that the reply is grounded in my tenant's ready documents and stays mine.

**Acceptance Criteria:**

**Given** a signed-in member and a `ready` document in that tenant
**When** they ask a question with no `document_id`
**Then** the chat use case retrieves tenant-scoped chunks, assembles that chunk text as context, and then generates
**And** the assistant message includes a `SourceRef` (`document_id`, `filename`, `page`, `chunk_index`) for each grounding chunk
**And** the response uses `{data, error}`

**Given** the same member
**When** they ask with a `document_id`
**Then** retrieval is limited to that document
**And** the document must be `ready` and in the same tenant

**Given** retrieval returns nothing, or no chunk scores at or above `RAG_SCORE_THRESHOLD`
**When** they ask
**Then** the assistant answers that it does not know
**And** it does not generate ungrounded content

**Given** an answer was produced
**When** the member reloads the conversation
**Then** the messages, including sources, are still there for that `user_id` in that tenant
**And** another tenant cannot load the thread

**Given** tenant A has a `ready` document with chunks
**When** tenant B asks the same question
**Then** tenant B does not retrieve tenant A's document or chunks

**Given** the chat use cases
**When** their tests run
**Then** the done check walks the authenticated path: tenant, `ready` document, question, tenant-scoped retrieval, grounded answer, `SourceRef`s, persisted conversation
**And** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `domain/chat.py` — `Conversation`, `Message`, and `SourceRef`
- `application/` — chat use case: retrieve, assemble context, generate
- `infrastructure/` — generate adapter, using `OPENAI_CHAT_MODEL`
- `infrastructure/http/` — ask and reload routes under `/api/v1`

## Epic 4: Improve retrieval quality

Answers can get better through hybrid search, rerank, and query rewrite without a second index or a change to isolation and citations.

### Story 4.1: Improve search without a second index

As a tenant member,
I want a question to surface better passages from my documents,
So that the cited answer is more useful and still comes only from my tenant.

**Acceptance Criteria:**

**Given** the existing retrieve and embed ports and the `chunks` collection
**When** hybrid search, rerank, and query rewrite are added
**Then** each one sits behind those same ports
**And** no second collection is created
**And** no unfiltered index is added

**Given** chunks for tenant A and tenant B
**When** a rewritten or hybrid query runs for tenant A
**Then** every query filter includes `actor.tenant_id`
**And** only `ready` documents are eligible
**And** an optional `document_id` still limits the query to that ready document in the same tenant

**Given** a grounded answer after this change
**When** the assistant message is saved
**Then** each `SourceRef` is still `document_id`, `filename`, `page`, and `chunk_index`
**And** a score below `RAG_SCORE_THRESHOLD` still does not ground the answer

**Given** the retrieval-quality use cases
**When** their tests run
**Then** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `domain/` — the existing retrieve and embed ports
- `infrastructure/` — hybrid, rerank, and query-rewrite adapters
- `application/` — context assembly stays a chat step

## Epic 5: Harden for production

Production can add stronger isolation, identity, and operations without rewriting Actor, the ports, or the one collection.

### Story 5.1: Enforce tenant isolation in Postgres

As an operator,
I want Postgres to enforce the tenant boundary,
So that a query cannot return another tenant's rows when an application filter is missed.

**Acceptance Criteria:**

**Given** tenant-owned tables, including `documents` and messages
**When** row-level security is enabled
**Then** each policy keys off the tenant in the database session
**And** the schema stays one shared schema
**And** repositories still filter by `actor.tenant_id`

**Given** a session set to tenant A
**When** a query reads a tenant-owned table
**Then** rows for tenant B are not returned

**Given** this story
**When** it is implemented
**Then** `Actor`, the hexagonal ports, and the `chunks` collection are unchanged
**And** domain and application tests still use in-memory fakes
**And** the row-level policy is tested at the Postgres adapter

**Lives in** `apps/api/src/app/`:

- `infrastructure/` — SQLAlchemy session and Alembic policy for row-level security
- `domain/actor.py` — stays the application isolation key

### Story 5.2: Sign in with an identity provider

As a tenant member,
I want to sign in through an identity provider,
So that production can use the organization's accounts while every action still runs as my tenant.

**Acceptance Criteria:**

**Given** an OIDC token for a user who belongs to a tenant
**When** they call a product route under `/api/v1`
**Then** the HTTP adapter verifies the token and builds `Actor` from `user_id` and `tenant_id`
**And** the use case receives that `Actor`
**And** the response still uses `{data, error}`

**Given** a missing or invalid OIDC token
**When** they call a product route
**Then** the status is 401
**And** the body is `{ "data": null, "error": { "code": "<STABLE_CODE>", "message": "<human>" } }`

**Given** a worker job
**When** it runs
**Then** the job still carries flat `tenant_id`, `user_id`, and `document_id`
**And** the job does not carry the OIDC token

**Given** this story
**When** it is implemented
**Then** `python -m app.cli bootstrap` and the local Bearer JWT still work
**And** `Actor`, the hexagonal ports, and the `chunks` collection are unchanged
**And** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `infrastructure/http/dependencies/auth.py` — build `Actor` from the verified OIDC token
- `infrastructure/auth/` — verify the OIDC token
- `domain/actor.py` — stays the value object use cases already take

### Story 5.3: See what the API and the worker did

As an operator,
I want a structured record of each request and each ingestion job,
So that I can trace a tenant's document from upload to ready without reading secrets.

**Acceptance Criteria:**

**Given** a product request under `/api/v1`
**When** the request finishes
**Then** the HTTP adapter writes a structured log with the `Actor` `tenant_id`, the route, and the status code
**And** the log omits passwords, `jwt_secret`, tokens, and document bytes

**Given** an ingestion job
**When** `ProcessDocument` finishes as `ready` or `failed`
**Then** the worker adapter writes a structured log with `tenant_id`, `document_id`, and the resulting status
**And** that log shares a correlation id with the request that enqueued the job

**Given** `/health` and `/ready`
**When** a probe calls them
**Then** they stay on their current paths and outside the `{data, error}` envelope

**Given** this story
**When** it is implemented
**Then** domain and application code do not import a logging or tracing SDK
**And** `Actor`, the hexagonal ports, and the `chunks` collection are unchanged
**And** domain and application tests use in-memory fakes and do not require Docker

**Lives in** `apps/api/src/app/`:

- `infrastructure/http/` — log the product request
- `infrastructure/worker/` — log the finished job
- `domain/` and `application/` — stay free of the logging SDK

### Story 5.4: Run on managed Postgres, Amazon S3, and Kubernetes

As an operator,
I want the same API and worker to run against managed services,
So that production can leave Compose without a new storage port or a new tenant boundary.

**Acceptance Criteria:**

**Given** S3 settings pointed at Amazon S3
**When** a member uploads a PDF
**Then** the bytes are stored at `tenant_id/document_id/filename` in the one bucket
**And** the `DocumentBytes` port is unchanged
**And** local Compose still uses Garage

**Given** a managed Postgres database
**When** the API and the worker start
**Then** they use the existing SQLAlchemy repositories and Alembic migrations
**And** repository filters and row-level security still key off the tenant

**Given** a Kubernetes deployment
**When** `api` and `worker` start from environment variables
**Then** both reach Postgres, Redis, Qdrant, and object storage
**And** Redis and Celery remain the only async fabric
**And** Qdrant still has one collection, `chunks`, filtered by `actor.tenant_id`

**Given** this story
**When** it is implemented
**Then** `Actor` and the hexagonal ports are unchanged
**And** domain and application tests use in-memory fakes and do not require Docker

**Lives in:**

- `infrastructure/` — S3 endpoint, region, and credentials come from the environment
- A Kubernetes deployment runs `api` and `worker`
- `compose.yaml` — stays the local environment, including Garage
