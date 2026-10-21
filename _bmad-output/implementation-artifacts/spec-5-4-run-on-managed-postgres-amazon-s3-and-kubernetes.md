---
title: 'Run on managed Postgres, Amazon S3, and Kubernetes'
type: 'feature'
created: '2026-10-21'
status: 'done'
route: 'dispatch'
baseline_commit: '357a8cc431461d3d38bdcb1e7cfd3a6e35570040'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The API and worker already take Postgres, Redis, Qdrant, and object storage from the environment, and Compose points object storage at Garage. Nothing starts those processes on Kubernetes, and nothing locks the Amazon S3 client shape.

**Approach:** Keep `S3DocumentBytes`, `DATABASE_URL`, and Alembic. Add manifests so `api` and `worker` use the same variable names against external Postgres, Redis, Qdrant, and one S3 bucket. Compose, including Garage, stays local.

## Boundaries & Constraints

**Always:**
- One bucket. Key stays `tenant_id/document_id/filename`. Empty `S3_ENDPOINT_URL` is `endpoint_url=None`. `S3_USE_PATH_STYLE=false` passes `config=None`. Credentials stay access key and secret.
- `DATABASE_URL` is the only database setting. `sslmode` stays in that URL. The login role stays `app` (`0004_tenant_rls` grants `app_rls` to `app`). Filters and `pin_rls_session` stay.
- `deploy/kubernetes/`, namespace `ai-rag`. Secret example `ai-rag-env` is placeholders only. Job `ai-rag-migrate` runs `alembic upgrade head` with `restartPolicy: Never`. Deployment and Service `api` use port 8000, liveness `GET /api/health`, readiness `GET /api/ready`. Deployment `worker` uses the Compose Celery command. Job, `api`, and `worker` share one image and `envFrom` that Secret. The API command stays the image default.
- Compose keeps Garage: `http://garage:3900`, region `garage`, path style true.

**Never:**
- A second storage port, a bucket per tenant, IAM roles, Helm, Terraform, an Ingress, or a `web` Deployment. No in-cluster Postgres, Redis, Qdrant, or Garage.
- Changes to `Actor`, ports, collection `chunks`, the RLS migration, domain or application code, or readiness-probe code. No migrate-on-boot. No real secrets, no new dependency, no Docker in tests.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Amazon client | Endpoint `""`, region `us-east-1`, path style false | `endpoint_url` None, `config` None, that region and the keys. Put key `tenant_id/document_id/filename` | N/A |
| Garage client | Compose `S3_*` | Path-style client at `http://garage:3900`. Existing test stays | N/A |
| Managed Postgres | URL user `app`, optional `sslmode` | Alembic uses that URL. Session still sets `app_rls` and `app.tenant_id` | No new role setting |
| Kubernetes | Secret has `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_USE_PATH_STYLE` | Both workloads `envFrom` it. Example endpoint empty, path style false. Worker command is Celery | No worker HTTP probe |
| API probes | `api` pod | Liveness `/api/health`, readiness `/api/ready` | No object-storage probe |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/infrastructure/storage/s3_document_bytes.py` — `_get_client` lines 58–71; `_key` line 74. Empty endpoint becomes None. Do not add a client class.
- `apps/api/src/app/infrastructure/config/settings.py` — S3 fields lines 27–32. Keep defaults `garage` and path style true. No new settings.
- `apps/api/src/app/bootstrap/create_app.py` — store wiring lines 285–292. `default_probes` lines 67–72. Do not migrate on startup.
- `apps/api/src/app/bootstrap/worker.py` — `build_process_document` lines 64–86.
- `apps/api/src/app/infrastructure/persistence/session.py` — `to_sqlalchemy_url` line 11; `pin_rls_session` line 28. `apps/api/alembic/env.py` `get_url` line 21. `apps/api/alembic/versions/0004_tenant_rls.py` line 40. Do not edit the migration.
- Leave unchanged: `DocumentBytes` (`documents.py` line 21), `_COLLECTION` and the tenant filter (`qdrant_chunk_store.py` lines 22 and 112), Celery (`celery_app.py` lines 6–12), probes (`health_router.py` lines 13 and 18), `compose.yaml` Garage and `S3_*` (lines 37, 63–69, 88, 97–103), `Dockerfile` `CMD` line 15, Garage test lines 75–96, `README.md` lines 27–34.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/tests/test_document_adapters.py` — Add the Amazon client case. Keep the Garage case.
- [x] `deploy/kubernetes/` — Namespace, placeholder Secret, migrate Job, `api` Deployment and Service, `worker` Deployment.
- [x] `apps/api/tests/test_kubernetes_manifests.py` — Read manifests and `compose.yaml` as text. Assert shared image, Secret names, empty Amazon endpoint, path style false, Celery command, probe paths, migrate command, and Garage Compose values.
- [x] `README.md` — Document the managed URL, Amazon `S3_*`, and apply order: Secret, migrate Job, `api`, `worker`.

**Acceptance Criteria:**
- Given `cd apps/api && uv run --extra dev pytest` and no Postgres, when it runs, then the suite passes, including the new tests, without Docker.
- Given `DocumentBytes`, `Actor`, `pin_rls_session`, and `chunks`, when this story is done, then those contracts are unchanged and Compose still starts Garage.

## Implementation Notes

- `cd apps/api && uv run --extra dev pytest` was 217 passed, 10 skipped. The skips are `tests/test_tenant_rls.py`. The Amazon client, manifest, Garage, and managed-URL tests ran. No Docker.
- `S3DocumentBytes` already maps an empty endpoint to `endpoint_url=None` and path style off to `config=None`. That adapter was not given a second client class.
- Manifests are under `deploy/kubernetes/`. The shared image is `ai-rag-api:latest`. Secret `ai-rag-env` is placeholders only. The API command stays the image default.

## Spec Change Log

## Review Triage Log

- medium — `api.yaml` probes set no `timeoutSeconds`. Kubernetes defaults that to 1 second. `PostgresProbe.check` waits up to 2 seconds and `QdrantProbe` uses an httpx timeout of 2 seconds, in sequence. A slow healthy dependency can fail readiness before `/api/ready` returns.
- medium — The README apply block runs the migrate Job and then `api` and `worker` with no wait. `kubectl apply` returns before the Job finishes, so the processes can use the database before Alembic does.
- medium — Job `ai-rag-migrate` stays complete. A later `kubectl apply` does not start it again, so a new Alembic revision is not applied.
- medium — The new README section never runs `python -m app.cli bootstrap`. After the Job, the database has schema and no tenant. The CLI already requires `BOOTSTRAP_TENANT_NAME`, `BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD`.
- medium — Secret `ai-rag-env` omits `OPENAI_API_KEY`. `Settings.openai_api_key` then stays `""`, so ingestion and answers have no key. Model defaults already exist. Empty OIDC leaves local JWT. The Service is ClusterIP because this story has no Ingress.
- medium — `0004_tenant_rls.py` runs `CREATE ROLE app_rls` and `GRANT app_rls TO app` as the `DATABASE_URL` user. The README does not say that user needs `CREATEROLE`. `sslmode=require` stays; the spec and the manifest test lock that URL, and a CA bundle is not part of this change.
- low — `test_kubernetes_manifests.py` does not assert `REDIS_URL`, `QDRANT_URL`, or the Service selector `app: api`. Those lines are present in the manifests. The managed-URL test asserts the rewritten URL and `parameters == [{"tenant_id": "tenant-1"}]`. `S3_USE_PATH_STYLE=false` is checked as text; Pydantic already parses that env string as False.
- low — `worker.yaml` sets no termination grace or preStop. Celery still acks on receipt, and this diff does not change `celery_app.py`. That is the same worker command Compose uses. A grace period does not finish a longer task; changing ack behavior is new worker policy. Rejected: everyday first start is one replica and does not roll a running task, and the fix adds policy.
- low — `image: ai-rag-api:latest` is a placeholder. The README tells the operator to replace it with the image they push. `imagePullPolicy: IfNotPresent` would keep a stale local `latest`. Rejected: applying the placeholder is the same failure as `REPLACE_ME`, and the documented step avoids the pull.
- low — Pods set no `resources`, `securityContext`, or `automountServiceAccountToken`. The image already runs as uid 10001. Those fields do not change Postgres, Redis, Qdrant, or S3. Rejected: this is extra policy, not a broken manifest.
- false — Sprint status is `in-progress` while this review runs. That status moves to review when the story is presented. The spec status `in-review` is this step.

## Design Notes

The Job is the Kubernetes form of `docker compose exec api alembic upgrade head`. The API image command does not migrate. The session user must be named `app` so `SET ROLE app_rls` matches the current grant. `/api/ready` already checks Postgres, Redis, and Qdrant.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` -- expected: pass, no Docker, including `tests/test_document_adapters.py` and `tests/test_kubernetes_manifests.py`
