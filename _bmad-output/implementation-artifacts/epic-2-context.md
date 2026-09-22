# Epic 2 Context: Build and maintain the tenant corpus

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A tenant member can upload PDFs into a shared corpus, watch them move through ingest to a searchable `ready` state, and delete or re-ingest so SQL, object storage, and vector points stay consistent—without leaking files or chunks across tenants. Epic 1 auth and the `/api/v1` `{data, error}` envelope are assumed. Planning artifacts include architecture and the epics inventory; no standalone PRD, product brief, or UX design contract was present.

## Stories

- Story 2.1: Upload a PDF and see it waiting
- Story 2.2: Make a PDF ready, replace it, or remove it

## Requirements & Constraints

- Authenticated members upload PDFs into their tenant only; documents start `pending`, keep the original filename, and are invisible to other tenants.
- Reject non-PDF and files over `MAX_DOCUMENT_SIZE_MB` (MVP default 20) with no Document row and no object created.
- Members can list documents and see status: `pending`, `processing`, `ready`, or `failed`.
- Upload leaves status `pending` and enqueues work; it must not write `processing`. Only `ProcessDocument` writes `processing`, `ready`, or `failed`. Re-ingest may move `ready`/`failed` back to `pending` and enqueue.
- A successful ingest yields `ready` points in Qdrant collection `chunks` with payload: `tenant_id`, `document_id`, `filename`, `page` (0-based), `chunk_index` (0-based), `text`. Ingest embed uses `OPENAI_EMBED_MODEL`.
- PDFs over `MAX_DOCUMENT_PAGES` (MVP default 100) or failed extract become `failed` and are not retrievable.
- At most `MAX_CONCURRENT_INGESTIONS_PER_TENANT` (MVP default 2) documents may be `processing` per tenant; extras stay `pending` until a slot frees.
- Delete removes the SQL row, the S3 object at `tenant_id/document_id/filename`, and all Qdrant points for that `document_id`.
- Re-ingest keeps the same `document_id`, resets to `pending`, deletes existing points for that id before upsert, then runs the normal process transitions.
- Tenant isolation is a security boundary: `tenant_id` comes from Actor (JWT or job record), never from an untrusted client field as the only filter. Cross-tenant access is HTTP 403 (`TenantIsolationError`).
- Until roles exist, every user in a tenant may use every document in that tenant.
- Product JSON is `{data, error}`; IDs are UUID strings; limits and secrets come from the environment; each use case ships tests with in-memory fakes (no Docker for domain/application).
- Out of scope for this epic: retrieval/chat HTTP, hybrid search, roles/ACL, public signup, OIDC, non-PDF formats, collection-per-tenant, API-local disk, forwarding JWT to the worker.

## Technical Decisions

- Hexagonal: domain ports and entities; application use cases with sync `execute()`; HTTP and Celery adapters share the composition root. Domain imports none of FastAPI/SQLAlchemy/Celery/Qdrant/LangChain/OpenAI/boto3. Product FastAPI routes are `def`; SQLAlchemy sync Session.
- Every tenant-touching use case takes `Actor` (`tenant_id`, `user_id`). Worker builds Actor from flat job JSON: `tenant_id`, `user_id`, `document_id`—jobs do not carry the JWT.
- `Document` is the only ingest lifecycle. Status machine: `pending` → `processing` → `ready` or `failed`; `ready`/`failed` may return to `pending` on re-ingest.
- Bytes behind domain port `DocumentBytes`; one S3 bucket; key `tenant_id/document_id/filename`. Add Garage (`dxflrs/garage:v2.4.1`) to Compose with S3 settings on `api` and `worker` when documents land.
- Extract, chunk, embed, and upsert are domain ports; LangChain is not the engine. PDF is the first corpus format; extractor library is chosen in the ingestion slice. Chunking runs only at ingest.
- One Qdrant collection `chunks`, Cosine distance; ingestion creates it if missing. Point id is deterministic from `document_id` and `chunk_index`. Delete/re-ingest must span SQL, S3, and Qdrant under Actor.
- One Postgres schema; `documents` table has `tenant_id`; repositories always filter by `actor.tenant_id`. RLS not required yet.
- HTTP maps domain errors: 401 unauthenticated, 403 tenant isolation, 404 not found, 409 other domain errors. Redis + Celery is the only async fabric.
- Slice order for this epic: documents (upload/list + Garage) then ingestion (ProcessDocument, limits, delete, re-ingest).

## Cross-Story Dependencies

- Depends on Epic 1: Bearer JWT, Actor from verified claims, and `/api/v1` `{data, error}` on product routes.
- Story 2.1 before 2.2: upload/list/`pending`/enqueue and Garage/S3 must exist before ProcessDocument, concurrency/page limits, delete, and re-ingest.
- Epic 3 depends on this epic’s `ready` documents and tenant-scoped `chunks` payloads; this epic does not add retrieval or chat routes.
