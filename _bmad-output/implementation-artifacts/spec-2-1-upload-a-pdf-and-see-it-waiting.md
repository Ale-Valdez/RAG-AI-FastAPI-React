---
title: 'Upload a PDF and see it waiting'
type: 'feature'
created: '2026-09-21'
status: 'done'
baseline_commit: '92635516fd09c0056a09cfa817ecda2bfac65dd9'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A signed-in member cannot add a PDF to their tenant corpus or see it waiting. Other tenants must not see that file.

**Approach:** Add upload and list under `/api/v1`. A valid PDF is stored as `pending` with its original filename, bytes go to the one S3 bucket, and a flat job is enqueued. Invalid uploads create nothing.

## Boundaries & Constraints

**Always:**
- `Actor` comes from the Bearer JWT. Keys and queries use `actor.tenant_id`, never a client-supplied tenant id as the only filter.
- Upload creates `pending` only. Do not call `Document.mark_processing`.
- Key `{tenant_id}/{document_id}/{filename}`. Job is flat strings `tenant_id`, `user_id`, `document_id` on queue `ai-rag-ingestion`.
- Reject unless the body starts with `%PDF-` and size is ≤ `MAX_DOCUMENT_SIZE_MB` (default 20). Reject an empty filename or one with `/`, `\`, or NUL. Check before any insert or put. If enqueue fails after a put, delete the object and leave no row.
- JSON is `{data, error}`. IDs are UUID strings. Domain and application tests use in-memory fakes, no Docker.
- Duplicate filenames are allowed. List is that tenant only, newest `created_at` first. JSON fields are `id`, `filename`, `status` (`created_at` is not returned).

**Never:**
- No delete, replace, re-ingest, download, or `ProcessDocument`. Do not write `processing`, `ready`, or `failed`.
- Do not change `Document` status methods, the `/api/v1` error-code map, JWT claims, the queue name, or migration `0001_tenants_users`.
- Do not change `apps/web`. No API-local disk. Domain and application do not import FastAPI, SQLAlchemy, Celery, or boto3.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Upload PDF | Bearer member; multipart `file`; starts with `%PDF-`; size ≤ limit | `201` `{data:{id,filename,status:"pending"},error:null}`. Row `pending`. Key and flat job as above. Status is not `processing`. | N/A |
| List | That member | `200` `{data:{documents:[{id,filename,status}]},error:null}` includes it as `pending` | N/A |
| Other tenant | Tenant B lists | Document absent. No bytes returned. | N/A |
| Not a PDF | Body does not start with `%PDF-` | No row, no object | `409` `DOMAIN_RULE_VIOLATION` |
| Oversize | Size > limit | No row, no object | `409` `DOMAIN_RULE_VIOLATION` |
| Bad filename | Empty, or contains `/`, `\`, or NUL | No row, no object | `409` `DOMAIN_RULE_VIOLATION` |
| Enqueue fails | Put succeeded, enqueue raises | No row, object deleted | Request fails; nothing left behind |
| No token | Missing or invalid Bearer | No row, no object | `401` `UNAUTHENTICATED` |
| No file | Multipart has no `file` | No row, no object | `422` `VALIDATION_ERROR` |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/domain/documents.py` — reuse `Document` (default `pending`). Do not change status methods. `domain/actor.py` — `Actor` is the only tenant scope.
- `apps/api/src/app/domain/errors.py` — add `InvalidDocument(DomainError)`. `infrastructure/http/error_handlers.py` already maps that base to `409` `DOMAIN_RULE_VIOLATION`. Do not edit it.
- `apps/api/src/app/domain/ports/auth.py` — Protocol style. `application/auth/login.py` — class + sync `execute`. `infrastructure/http/auth_router.py` — `/api/v1`, `require_actor`, `success_body`.
- `apps/api/src/app/bootstrap/create_app.py` — copy `SessionBoundLogin`. App construction must not open the network.
- `apps/api/src/app/infrastructure/persistence/models.py` — add `DocumentRow` beside `TenantRow` / `UserRow`. `alembic/versions/0001_tenants_users.py` — next revision only; do not edit.
- `apps/api/src/app/infrastructure/worker/celery_app.py` — keep queue `ai-rag-ingestion`. `infrastructure/config/settings.py` — no S3 or size fields. `compose.yaml` — no Garage.
- `apps/api/tests/fakes.py`, `test_auth_http.py`, `test_persistence.py` — fakes, injected `create_app`, sqlite. Leave `apps/web`.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/errors.py` -- add `InvalidDocument` -- rejections use the existing 409 map
- [x] `apps/api/src/app/domain/ports/documents.py` -- add `DocumentRepository`, `DocumentBytes`, `DocumentJobQueue`
- [x] `apps/api/src/app/application/documents/` -- `UploadDocument.execute(actor, command)` and `ListDocuments.execute(actor)` -- validate, then put, insert `pending`, enqueue; list by `actor.tenant_id`
- [x] `apps/api/tests/fakes.py` and `apps/api/tests/test_documents_upload.py` -- I/O matrix with fakes, including no put and no save on reject, and object delete when enqueue fails
- [x] `apps/api/src/app/infrastructure/config/settings.py` and `.env.example` -- `MAX_DOCUMENT_SIZE_MB` default 20; `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_USE_PATH_STYLE` default true
- [x] `apps/api/pyproject.toml` -- add `boto3==1.43.98`
- [x] `apps/api/src/app/infrastructure/persistence/models.py`, `document_repository.py`, `alembic/versions/0002_documents.py` -- table `documents` (`id`, `tenant_id`, `filename`, `status`, `created_at`) revising `0001_tenants_users`; every query filters `actor.tenant_id`
- [x] `apps/api/tests/test_persistence.py` -- sqlite save and tenant-scoped list
- [x] `apps/api/src/app/infrastructure/storage/s3_document_bytes.py` -- one bucket, key `{tenant_id}/{document_id}/{filename}`, path-style from env
- [x] `apps/api/src/app/infrastructure/worker/celery_app.py` and `tasks.py` -- enqueue the flat payload; register a task the worker can import; the body must not load or transition the document
- [x] `apps/api/src/app/infrastructure/http/documents_router.py` -- `POST` and `GET` `/api/v1/documents` (field `file`), both behind `require_actor`
- [x] `apps/api/src/app/bootstrap/create_app.py` -- session-bound upload and list, overridable in tests
- [x] `apps/api/tests/test_documents_http.py` -- envelope, 401, 409, 422, two-tenant list, injected fakes
- [x] `compose.yaml`, `infra/garage/garage.toml`, `README.md` -- Garage `dxflrs/garage:v2.4.1`, one bucket, same S3 env on `api` and `worker`

**Acceptance Criteria:**
- Given the new routes, when this story is done, then there is no delete, replace, re-ingest, or download route.
- Given Compose, when documents land, then Garage `dxflrs/garage:v2.4.1` is a service and `api` and `worker` share its S3 settings.
- Given domain and application tests, when they run, then they use in-memory fakes and do not need Docker.

## Implementation Notes

- Added `python-multipart` so FastAPI can accept the upload field.
- Restored `require_signing_secret` in `jwt.py`. `create_app` already imported it and the baseline file did not define it. JWT claims are unchanged.
- Garage access key is `GK` plus 30 hex characters, which v2.4.1 requires for `--default-bucket`.
- HTTP tests cover oversize, a path-like filename, and an invalid bearer token in addition to the use-case matrix.

## Spec Change Log

## Review Triage Log

- `false` — Code Map still describes pre-change `settings.py` and `compose.yaml`. That section is a planning snapshot. The fix would edit the spec. Rejected.
- `false` — Spec `in-review` vs sprint `in-progress`. Step 4 sets the spec status before review finishes; sprint stays `in-progress` until the workflow syncs it.
- `low` — Enqueue can succeed and a later commit can fail, leaving a job and an S3 object. Design Notes require enqueue inside the request transaction so a failed enqueue rolls back the row. Rejected: the window is rare, and the fix is an outbox.
- `false` — Enqueue failure does not need a repository `remove`. `session_scope` rolls the insert back, and the sqlite test asserts the tenant list is empty.
- `low` — `documents_router.py` reads the whole multipart body before the size check. The use case still rejects before put, and its command is `content: bytes`. Rejected: a streaming cap is extra machinery for a path normal PDFs do not hit.
- `low` — `document_repository.py` orders only by `created_at`, so equal timestamps are unordered. Patch: add `id` desc.
- `low` — `0002_documents` has no foreign key to `tenants`. Upload uses the JWT tenant, and this story has no tenant delete. Rejected: a foreign key is a new constraint.
- `low` — Garage is `service_started`, not healthy. A human signs in before uploading, so the race is outside everyday use. Rejected: a healthcheck is new compose machinery.
- `false` — The Celery body is a no-op and consumed jobs are not replayed. Design Notes require that.
- `false` — No Compose smoke test. Verification and the acceptance criteria require pytest without Docker.
- `false` — Spec Change Log and Review Triage Log start empty. This review fills the triage log; the change log waits for a spec amendment.
- `false` — `python-multipart` is missing from the task checklist. Implementation Notes already record it. Rejected: the fix would edit the spec.
- `false` — No HTTP test for enqueue failure. The use-case test and the sqlite session test cover that matrix row.
- `false` — README marks the API slice done and still says the documents UI is an empty state.
- `false` — `rpc_public_addr` is `127.0.0.1:3901`. S3 binds `[::]:3900`, and clients use `http://garage:3900`. The RPC address is not the S3 endpoint.
- `low` — Same unbounded multipart read as above. Rejected on the same grounds.
- `low` — Same enqueue-then-commit window as above. Rejected on the same grounds.
- `false` — A worker can receive the job before commit. `process_document` does not load the row, so the race does not change status.
- `low` — If the cleanup `delete` raises, it replaces the original enqueue error. The session still rolls back. Rejected: the extra branch is not the everyday path.
- `false` — A whitespace filename is stored. The spec rejects only an empty name or `/`, `\`, or NUL. Spaces stay part of the original filename.
- `false` — An unknown status string crashes list. Upload only writes `pending`. A corrupt row is not a path this story creates.
- `low` — Same `created_at` tie as above. Patch with that row.
- `medium` — `S3DocumentBytes` is never called by tests, so a wrong bucket or key would stay green. Pre-verified. Patch: assert `put`/`delete` bucket, key, and body, and path-style config.
- `medium` — `CeleryDocumentJobQueue` is never called by tests, so a wrong task name or kwargs would stay green. Pre-verified. Patch: assert `send_task` name and flat kwargs.
- `medium` — `max_document_size_bytes` is never asserted, so dropping the MiB conversion would stay green. Pre-verified. Patch: assert 20 MB is `20 * 1024 * 1024`.
- `low` — A second upload of the same filename is allowed but untested. Pre-verified. Patch: expect two ids.
- `low` — Same enqueue-before-commit note from the verification pass. Rejected on the same grounds as the earlier commit-window finding.

## Design Notes

Validate in the use case. Do not add an HTTP error handler.

Write order: magic bytes, size, filename; allocate id; put; insert in the request transaction; enqueue. Enqueue failure deletes the object and rolls back the row.

Register the Celery task with the flat kwargs. Its body is a no-op so a running worker leaves `pending`. Story 2.2 replaces that body. Consumed jobs are not replayed.

Garage: one node, `replication_factor` 1, path-style, bucket `S3_BUCKET`. Dev credentials sit in Compose the same way Postgres credentials do.

## Verification

**Commands:**
- `cd apps/api && pytest` -- expected: existing tests still pass; upload, list, HTTP, and sqlite tests pass; no Docker
