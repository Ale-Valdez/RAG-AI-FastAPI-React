---
title: 'See what the API and the worker did'
type: 'feature'
created: '2026-10-20'
status: 'done'
route: 'dispatch'
baseline_commit: 'af13b8581f2c5799c2e4acea1bec5fb25efa95b3'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** An operator cannot trace a tenant's document from the request that enqueued ingestion to the finished job. Nothing records either event, and logging the token or the PDF would expose secrets.

**Approach:** The HTTP adapter writes one structured record when a `/api/v1` request finishes. The worker writes one when `ProcessDocument` finishes `ready` or `failed`. They share a correlation id. `Actor`, the ports, and collection `chunks` stay as they are.

## Boundaries & Constraints

**Always:**
- `tenant_id` only when `require_actor` returned an `Actor`; otherwise null. `/api/health` and `/api/ready` are not this log and keep their bodies.
- **Decision:** One JSON object on logger `app.ops` at INFO. Request: `event`=`http.request`, `correlation_id`, `tenant_id`, `route`, `status_code`. Job: `event`=`ingestion.job`, `correlation_id`, `tenant_id`, `document_id`, `status` (`ready` or `failed`). `route` is method plus matched template, else method plus path. No query string.
- **Decision:** UUID per request. No client header and no response header. Celery header `ai_rag_correlation_id`; kwargs stay the three ids. Missing id logs null. Retry keeps the id; one job line, on `ready` or `failed`.
- Omit passwords, `jwt_secret`, tokens, `Authorization`, document bytes, and exception text. Domain and application import no logging SDK.

**Never:**
- Changing `Actor`, `DocumentJobQueue.enqueue`, task arguments, repository filters, row-level security, OIDC, or `chunks`.
- Logging `user_id`, a body, a header, a query string, or a stack trace.
- A job line for `skipped`, `deferred`, or an exception from `SessionBoundProcessDocument` before an outcome.
- A new setting, package, migration, or web-app change.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Authenticated | Valid JWT `GET /api/v1/me` | `tenant_id` set, route `GET /api/v1/me`, 200, UUID. No token | N/A |
| Login | `POST /api/v1/auth/login` | That status, `tenant_id` null. No password or `access_token` | N/A |
| Bad token | Bad Bearer `GET /api/v1/me` | 401, `tenant_id` null, token absent, `UNAUTHENTICATED` | N/A |
| Missing route | `GET /api/v1/does-not-exist` | 404, `tenant_id` null, `NOT_FOUND` | N/A |
| Unhandled | A `/api/v1` route raises | 500, `INTERNAL_ERROR`, no exception text | N/A |
| Probes | `GET /api/health`, `GET /api/ready` | No `app.ops` line. Bodies outside `{data, error}` | N/A |
| Enqueue | Upload calls `CeleryDocumentJobQueue.enqueue` | Kwargs are the three ids. Header equals the request id | N/A |
| Job done | Header set; `ready` or `failed` | Same id, `tenant_id`, `document_id`, that status | N/A |
| Job open | `deferred`, `skipped`, or no header | No line for defer or skip. Defer retries in 5s. No header: `correlation_id` null | N/A |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/bootstrap/create_app.py` — line 338; CORS at line 389. Middleware outside CORS. Stderr `%(message)s` handler only when `root.handlers` is empty.
- `apps/api/src/app/infrastructure/http/dependencies/auth.py` — `build_require_actor` line 19. Set `request.state.tenant_id` after verify succeeds.
- `apps/api/src/app/infrastructure/http/error_handlers.py` — `_is_product_route` line 17. Do not log `exc`. Health routes: `health_router.py` lines 13 and 18.
- `apps/api/src/app/domain/ports/documents.py` — `enqueue` line 36, three ids. Callers `upload_document.py` line 45 and `reingest_document.py` line 25 stay. Fake: `tests/fakes.py` line 125.
- `apps/api/src/app/infrastructure/worker/document_job_queue.py` — `enqueue` line 7. Read the middleware `ContextVar`. Celery 5.4 copies `request.headers` on retry and overwrites a header named `correlation_id`.
- `apps/api/src/app/infrastructure/worker/tasks.py` — line 12; retry line 18. Log `READY` or `FAILED` only. `bootstrap/worker.py` line 56 re-raises with no job line. `ProcessOutcome` is `process_document.py` line 18.
- `apps/api/tests/test_document_adapters.py` — lines 99 and 121 stay green. `test_auth_http.py` line 165; 500 uses `raise_server_exceptions=False`.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/infrastructure/ops_log.py` — JSON on `app.ops` and the request correlation id.
- [x] `apps/api/src/app/infrastructure/http/access_log.py` — ASGI middleware for the request line. Not `BaseHTTPMiddleware`. Do not read the body.
- [x] `apps/api/src/app/infrastructure/http/dependencies/auth.py` — Store `actor.tenant_id` on `request.state` after success.
- [x] `apps/api/src/app/bootstrap/create_app.py` — Install the middleware and the stderr handler.
- [x] `apps/api/src/app/infrastructure/worker/document_job_queue.py` — Pass `ai_rag_correlation_id`. Kwargs stay the three ids.
- [x] `apps/api/src/app/infrastructure/worker/tasks.py` — Log `ingestion.job` for `READY` or `FAILED` only. Missing header is null.
- [x] `apps/api/tests/test_access_log.py` — Matrix with `TestClient`, `caplog`, patched `send_task`, and `push_request`. No Docker or broker.

**Acceptance Criteria:**
- Given `cd apps/api && uv run --extra dev pytest` and no Postgres, when it runs, then the suite passes, including `tests/test_access_log.py`, without Docker.
- Given `Actor`, `DocumentJobQueue`, and `chunks`, when this story is done, then those contracts are unchanged and `domain/` and `application/` import no logging SDK.

## Implementation Notes

- `cd apps/api && uv run --extra dev pytest` was 212 passed, 10 skipped. The skips are `tests/test_tenant_rls.py`. `tests/test_access_log.py` covers the matrix with `TestClient`, `caplog`, a patched `send_task`, and `push_request`. No Docker and no broker.
- The request line is pure ASGI middleware outside CORS. It does not read the body. `tenant_id` is copied from `request.state` only after `require_actor` returns an `Actor`.
- The Celery header is `ai_rag_correlation_id`. Celery 5.4 keeps that name in `request.headers` across `signature_from_request` (the copy `retry` uses) and drops a header named `correlation_id`.
- An unhandled `/api/v1` error is logged as 500. Starlette's server-error middleware sits outside this middleware and sends the envelope after the line is written; the line does not include the exception text.

## Spec Change Log

## Review Triage Log

- low — `install_ops_stderr_handler` puts a `%(message)s` handler on the root logger when it is empty. Uvicorn's own loggers set `propagate` false, so they keep their formatters. The code map asks for that root handler, and the worker line stays a JSON message under Celery's formatter.
- false — A Celery `Context` drops a header named `correlation_id`. This code sends `ai_rag_correlation_id`, which is not a `Context` attribute, so it stays on `request.headers`. `test_finished_job_logs_ready_or_failed` pushes that header through `Context` and reads it back in the job line. `test_retry_options_keep_the_correlation_header` checks `signature_from_request` copies it.
- low — A browser preflight is answered by `CORSMiddleware` before routing, and this middleware sits outside CORS, so the line uses the raw path. The frozen rule for an unmatched `/api/v1` request is method plus path.
- low — `status_code` starts at 500, so a disconnect before `http.response.start` is logged as 500. Unhandled `Exception` is handled by `ServerErrorMiddleware` outside this middleware; `finally` logs the default 500, and that handler also returns 500. 401 and 404 tests show the wrapper reads a real status.
- low — A raise from `logger.info` in the request `finally`, or from `log_ingestion_job` after the worker commit, would surface as the request or task error. The stdlib logger does not raise on a normal stream.
- low — The code map line numbers are a few lines off after the edit (`create_app` is 340, CORS middleware is 392, `enqueue` is 8, `process_document` is 13, `retry` is 19, the worker `raise` is 58).
- low — `sprint-status.yaml` still has `5-3-see-what-the-api-and-the-worker-did` at `in-progress` while the spec is `in-review`.
- low — Uvicorn's access formatter writes `request_line`, query string included. That logger is pre-existing; the ops line omits the query, which the access-log tests check.
- false — Reingest uses the same `CeleryDocumentJobQueue.enqueue` as upload. The middleware sets the correlation id for every `/api/v1` request, and the upload test already checks that enqueue during a request.
- false — The frozen Never list says there is no job line for `skipped`, `deferred`, or an exception before an outcome. A commit failure raises out of `SessionBoundProcessDocument.execute` before the task can log.
- false — `_is_product_path` uses `startswith("/api/v1")`, which is `_is_product_route` in `error_handlers.py`. The spec says to reuse that rule. `/api/health` does not match.
- low — Same disconnect-as-500 claim at `access_log.py` lines 23–40. `status_code` stays 500 when no response starts.
- medium — `test_stderr_handler_only_when_root_has_no_handlers` calls `install_ops_stderr_handler` itself. Deleting the `create_app` call stays green, and `logging.lastResort` drops INFO, so the API would emit no ops lines.
- medium — The missing-header job test uses `push_request(headers={})`. Celery sets `request.headers` to `None` when no custom header remains. Dropping the `Mapping` check then raises `AttributeError` after a successful job, and the suite still passes.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` — 212 passed, 10 skipped. The skips are `tests/test_tenant_rls.py` (no Postgres). `tests/test_access_log.py` passed. No Docker.
