---
title: 'Make a PDF ready, replace it, or remove it'
type: 'feature'
created: '2026-09-22'
status: 'done'
baseline_commit: '402c5e3f645401fc4b094e04905191994b846827'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A pending PDF never becomes searchable, and a member cannot replace its chunks or remove the file from SQL, S3, and Qdrant together. Old points would keep answering later questions.

**Approach:** `ProcessDocument` is the only writer of `processing`, `ready`, and `failed`. Members re-ingest or delete over `/api/v1`. Re-ingest keeps the same `document_id` and the same stored bytes. The worker deletes that document's points before the new upsert.

## Boundaries & Constraints

**Always:**
- HTTP `Actor` comes from the Bearer JWT. The worker builds `Actor` from flat job strings `tenant_id`, `user_id`, `document_id`. Never use a client tenant id as the only filter.
- `ProcessDocument` loads the document, checks the tenant, then `pending` → `processing` → `ready` or `failed`. A job whose status is not `pending` changes nothing. A missing row (already deleted) is not recreated.
- While the tenant already has `MAX_CONCURRENT_INGESTIONS_PER_TENANT` documents in `processing` (default 2), this document stays `pending`. The Celery task retries itself after 5 seconds with no retry cap.
- More than `MAX_DOCUMENT_PAGES` pages (default 100), a failed extract, or zero chunks: status `failed`, and no points remain for that `document_id`. The same cleanup follows an embed or upsert failure.
- A `ready` document has points in Qdrant collection `chunks`, distance Cosine. Payload: `tenant_id`, `document_id`, `filename`, `page` (0-based), `chunk_index` (0-based), `text`. Point id is UUID5 of `{document_id}:{chunk_index}` with namespace `8b3e1c4a-6f2d-4a7e-9c1b-2d5e6f708192`. Embed model is `OPENAI_EMBED_MODEL`, default `text-embedding-3-small`. Vector size is the length of the returned vector.
- Chunks are page-aware, at most 1000 characters, split on the last whitespace in the window or hard-cut at 1000, no overlap. Whitespace-only page text adds no chunk. Empty pages still count toward the page limit.
- Re-ingest allows only `ready` or `failed`. It sets `pending`, enqueues the same flat job, and does not upload new bytes. `ProcessDocument` deletes existing points for that `document_id` before upsert.
- Delete removes Qdrant points, then the S3 object at `{tenant_id}/{document_id}/{filename}`, then the SQL row, for any status in the member's tenant. Another tenant's id is `404` `NOT_FOUND`. A loaded row whose tenant does not match the job `Actor` is `403` `TENANT_ISOLATION`.
- JSON is `{data, error}`. Persist `processing` and commit it before extract or embed, with the tenant's document rows locked in that transaction, so the concurrency count is visible.
- Domain and application tests use in-memory fakes and do not need Docker.

**Never:**
- No retrieval or chat route, no second Qdrant collection, no LangChain, no `apps/web` change, no new Alembic revision.
- Do not change `mark_processing`, `mark_ready`, or `mark_failed` preconditions, the `/api/v1` error-code map, JWT claims, queue `ai-rag-ingestion`, task name `app.infrastructure.worker.tasks.process_document`, or migrations `0001_tenants_users` and `0002_documents`.
- Upload still creates `pending` only. Do not accept a replacement file on re-ingest. Do not forward the JWT to the worker.
- Domain and application do not import FastAPI, SQLAlchemy, Celery, Qdrant, OpenAI, boto3, or pypdf.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ingest | Job for a `pending` PDF within the page limit; fewer than 2 `processing` | Status `ready`. Points use the payload and UUID5 id above. `processing` was stored before embed. | N/A |
| Too many pages | Extracted page count > limit | Status `failed`. No points for that id. | N/A |
| Extract fails or no chunks | Extract raises, or every page is empty | Status `failed`. No points. | N/A |
| At capacity | Tenant already has 2 `processing` | Stays `pending`. Task retries in 5s. No extract. | N/A |
| Duplicate job | Status is `processing`, `ready`, or `failed` | Status unchanged. No upsert. | N/A |
| Other tenant job | Loaded row tenant ≠ job tenant | Status unchanged. | `TenantIsolationError` |
| Deleted before finish | Row gone after claim | No new row. No upsert. | N/A |
| Re-ingest | Member; status `ready` or `failed` | `200` `{data:{id,filename,status:"pending"},error:null}`. Same id. Job enqueued. Bytes unchanged. | N/A |
| Re-ingest wrong status | `pending` or `processing` | No enqueue. | `409` `DOMAIN_RULE_VIOLATION` |
| Delete | Member; any status in that tenant | `200` `{data:{id},error:null}`. Row, object, and points gone. | N/A |
| Delete other tenant | Id belongs to tenant B | Row, object, and points remain. | `404` `NOT_FOUND` |
| No token | Missing or invalid Bearer on delete or re-ingest | No mutation. | `401` `UNAUTHENTICATED` |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/domain/documents.py` — add `mark_pending` for `ready`/`failed` only. Leave `mark_processing` (24–26), `mark_ready` (28–30), `mark_failed` (32–34) as they are.
- `apps/api/src/app/domain/ports/documents.py` — add `get`, `delete`, and `count_processing` on `DocumentRepository`; add `get` on `DocumentBytes`. Keep `save`, `list_for_tenant`, `put`, `delete`, `enqueue`.
- `apps/api/src/app/domain/errors.py` — reuse `NotFoundError`, `TenantIsolationError`, `InvalidDocumentTransition`. Do not edit `infrastructure/http/error_handlers.py`.
- `apps/api/src/app/domain/tenancy.py` — `assert_same_tenant` for a loaded row. `domain/actor.py` — `Actor` is the only tenant scope.
- `apps/api/src/app/application/documents/upload_document.py` — leave the pending-only flow. `list_documents.py` — unchanged list payload.
- `apps/api/src/app/infrastructure/persistence/document_repository.py` — `save` (17–25) inserts only and stamps `created_at` now. Update the same id in place and keep `created_at`. `models.py` `DocumentRow` needs no new columns.
- `apps/api/src/app/infrastructure/storage/s3_document_bytes.py` — key `{tenant_id}/{document_id}/{filename}` (`_key` ~66). Add `get`. Do not change `put` / `delete`.
- `apps/api/src/app/infrastructure/worker/tasks.py` — body is a no-op (4–7). Replace the body only. `document_job_queue.py` already sends the flat kwargs. `celery_app.py` queue stays `ai-rag-ingestion`.
- `apps/api/src/app/infrastructure/http/documents_router.py` — `POST`/`GET` `/api/v1/documents` and `_document_payload`. Add delete and re-ingest beside them, both behind `require_actor`.
- `apps/api/src/app/bootstrap/create_app.py` — `SessionBoundUploadDocument` commits once around upload (68–88). Wire delete and re-ingest the same way. Do not run `ProcessDocument` inside HTTP. App import must not open the network.
- `apps/api/src/app/infrastructure/config/settings.py` — add page limit, concurrency limit, and embed model. `qdrant_url` and `openai_api_key` already exist.
- `apps/api/src/app/infrastructure/persistence/session.py` — `session_scope` commits at the end. The worker claim must commit `processing` before the slow calls; do not wrap extract and embed in that same transaction.
- `apps/api/tests/fakes.py` — `InMemoryDocumentRepository.save` appends. Upsert by id so a second save does not duplicate the row. Extend bytes with `get`.
- `compose.yaml` — worker has Garage and `QDRANT_URL` but no `depends_on: qdrant` (101–107). `pyproject.toml` has no `qdrant-client`, `openai`, or `pypdf`.
- `apps/api/tests/test_documents_http.py` — inject use cases through `create_app`. `test_document_adapters.py` — monkeypatch boto3 and Celery.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/documents.py` -- add `mark_pending` -- re-ingest is the only return to `pending`
- [x] `apps/api/src/app/domain/ports/documents.py` and `apps/api/src/app/domain/ports/ingestion.py` -- repository get/delete/count, bytes `get`, and extract/chunk/embed/chunk-store ports -- use cases stay free of SDKs
- [x] `apps/api/src/app/application/documents/process_document.py` -- `ProcessDocument.execute(actor, document_id)` -- claim, limits, delete-then-upsert, terminal status
- [x] `apps/api/src/app/application/documents/delete_document.py` and `reingest_document.py` -- member delete and re-ingest -- three-store delete; same id and bytes on re-ingest
- [x] `apps/api/tests/fakes.py`, `test_documents.py`, `test_process_document.py`, `test_delete_document.py`, `test_reingest_document.py` -- I/O matrix with fakes and the real chunker -- no Docker
- [x] `apps/api/src/app/infrastructure/persistence/document_repository.py` and `apps/api/tests/test_persistence.py` -- update-by-id, scoped get, delete, processing count with a tenant row lock -- keep `created_at`
- [x] `apps/api/src/app/infrastructure/storage/s3_document_bytes.py` and `apps/api/tests/test_document_adapters.py` -- `get` of the existing key -- bucket, key, and body asserted
- [x] `apps/api/src/app/infrastructure/ingestion/` -- pypdf extract, page chunker, OpenAI embed, Qdrant upsert/delete -- pins `qdrant-client==1.13.3`, `openai==3.14.0`, and a pinned `pypdf`
- [x] `apps/api/src/app/bootstrap/worker.py` and `apps/api/src/app/infrastructure/worker/tasks.py` -- build `Actor`, run `ProcessDocument`, retry when deferred -- task name and kwargs stay
- [x] `apps/api/src/app/infrastructure/http/documents_router.py`, `apps/api/src/app/bootstrap/create_app.py`, `apps/api/tests/test_documents_http.py` -- `DELETE /api/v1/documents/{document_id}` and `POST /api/v1/documents/{document_id}/reingest` -- envelope, 401, 404, 409
- [x] `apps/api/src/app/infrastructure/config/settings.py`, `.env.example`, `compose.yaml`, `README.md` -- page, concurrency, and embed-model env; worker `depends_on` qdrant -- README names ready, delete, and re-ingest

**Acceptance Criteria:**
- Given domain and application tests, when they run, then they use in-memory fakes and do not need Docker.
- Given the new routes, when this story is done, then there is no retrieval or chat route and `apps/web` is unchanged.
- Given Compose, when the worker starts, then it depends on Qdrant and reads `OPENAI_EMBED_MODEL`, `MAX_DOCUMENT_PAGES`, and `MAX_CONCURRENT_INGESTIONS_PER_TENANT` from the environment.

## Implementation Notes

- `cd apps/api && uv run --extra dev pytest` — 98 passed, no Docker. Added coverage for delete-after-claim, the 5-second deferred retry, invalid bearer on delete and re-ingest, re-ingest conflict for `processing`, and Qdrant UUID5/Cosine upsert.
- Review patches: if the row is gone after upsert, delete that document's points; if point cleanup raises, still save `failed`. Follow-up `pytest` — 105 passed. Nothing deferred.

## Spec Change Log

## Review Triage Log

- `medium` — `_ready` returns skipped after `upsert_chunks` if the row disappeared, and does not delete the points just written (`process_document.py`). A delete during upsert leaves Qdrant points for a removed document.
- `medium` — Rejected. A crash after the `processing` commit leaves that status, and re-ingest will not accept it. The frozen rules say a non-pending job changes nothing and re-ingest allows only `ready` or `failed`. Delete is the recovery. A reclaim path would edit the spec.
- `false` — Uncapped 5-second retries are the frozen rule (“no retry cap”), not a defect.
- `medium` — Upsert failure is caught and sent to `_fail`, but no test sets `fail_upsert=True`. Removing that cleanup would stay green.
- `low` — Re-ingest of another tenant’s id raises `NotFoundError` in `test_reingest_other_tenant_not_found`, and the existing handler maps that to `404`. The HTTP route for re-ingest does not repeat that case. Patch: one HTTP assertion.
- `low` — Rejected. One embed request for the whole document can fail a very large PDF, and `_fail` already marks `failed`. Batching is extra machinery for a path the page cap already bounds.
- `low` — Rejected. A later embed-model dimension change against an existing `chunks` collection is an operator migration. This story creates the collection if it is missing.
- `false` — No failure reason is stored. The spec forbids a new migration and keeps list JSON to `id`, `filename`, and `status`.
- `false` — A delete that fails after points are removed still leaves the SQL row, which is the retry handle the design notes require. A second delete finishes S3 and the row. `delete_object` on a missing key succeeds.
- `false` — Partial `create_app` overrides do not open the network. `QdrantChunkStore` connects on first use, and current tests that build the app either inject every document use case or already built the upload defaults.
- `false` — A later all-space window inside a non-empty page can be its own chunk. The rule skips whitespace-only pages, which `_split_page` does at the start of the page.
- `low` — Rejected. The README names ready, delete, and re-ingest, which is the task. A runbook for stuck `processing` is out of the spec’s README line.
- `medium` — Same orphan-point window as the first row: `_ready` skips without `delete_by_document` (`process_document.py` around the post-upsert `get`).
- `medium` — `_fail` calls `delete_by_document` before `mark_failed`. If that delete raises, the committed `processing` row is never saved as `failed`, and a later job skips it.
- `low` — Rejected. `max_concurrent` of 0 would defer every job. The default is 2 and everyday env values are positive. A new guard is extra validation.
- `false` — Same partial-delete sequence as the earlier delete row. The row remains for a retry.
- `medium` — Same stuck-`processing` outcome as the `_fail` row, stated as a claim mismatch: terminal status is not reached when cleanup raises.
- `medium` — Success-path `delete_by_document` before upsert is implemented and untested. `test_ingest_ready_with_payload_and_uuid5` never seeds a stale point. Pre-verified.
- `medium` — Upsert-failure cleanup is untested. `fail_upsert` is unused. Pre-verified. Same gap as the upsert-failure row above.
- `medium` — Page limit uses `len(pages)`, so blank pages count, but every limit test uses non-empty text. Pre-verified.
- `medium` — `delete_by_document` filters `tenant_id` and `document_id`, and the adapter test only asserts the collection name. Pre-verified.
- `medium` — `SessionBoundProcessDocument` passes `commit=session.commit`, and no test constructs that class. Pre-verified.
- `medium` — Hard-cut at 1000 when a page has no spaces is implemented and untested. Pre-verified.
- `medium` — The deferred-task test checks the 5-second countdown only, not `Actor` tenant/user or `max_retries is None`. Pre-verified.
- `medium` — `OpenAIEmbeddingGenerator` and `PypdfTextExtractor` are never called in tests. Pre-verified.

## Design Notes

Claim in one transaction: lock the tenant's `documents` rows, count `processing`, and either return deferred or save `processing` and commit. Extract, embed, and upsert run after that commit. A later transaction saves `ready` or `failed`.

On the success path, delete points for `document_id`, then upsert. On any failure after claim, delete points and save `failed`. UUID5 namespace `8b3e1c4a-6f2d-4a7e-9c1b-2d5e6f708192`, name `{document_id}:{chunk_index}`.

`InMemoryDocumentRepository.save` replaces the same id so status changes do not append a second row. List order stays put.

The Celery task uses `bind=True` and, on deferred, `self.retry(countdown=5)` with no retry cap. `send_task` kwargs stay `tenant_id`, `user_id`, `document_id`.

## Verification

**Commands:**
- `cd apps/api && pytest` -- expected: existing tests still pass; process, delete, re-ingest, HTTP, and sqlite tests pass; no Docker
