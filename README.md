# AI-RAG

AI Knowledge Assistant grounded in organization documents.

Generated from `ai-rag-fastapi-react` 1.0. This repository is independent from
the `project-blueprint` factory.

## Stack

- React (Vite) → FastAPI
- PostgreSQL, Qdrant, Redis, Celery, Garage (S3-compatible)
- Hexagonal backend: domain and use cases do not import FastAPI, SQLAlchemy, or Qdrant

## Run

```bash
cp .env.example .env
```

Set `JWT_SECRET` in `.env` to a long random value. The API refuses to start when
that variable is empty or `change-me`.

```bash
docker compose up --build
```

Compose starts the services; it does **not** run Alembic migrations. Apply schema
before bootstrap. Run both inside the `api` container so they use the Compose
network and the variables from `.env`:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli bootstrap
```

- Web: http://localhost:5173
- API health: http://localhost:8000/api/health
- API ready: http://localhost:8000/api/ready
- Login: `POST /api/v1/auth/login`
- Current member: `GET /api/v1/me`
- Documents: `POST /api/v1/documents` (multipart `file`), `GET /api/v1/documents`
- Re-ingest: `POST /api/v1/documents/{id}/reingest` (ready/failed → pending; same bytes)
- Delete: `DELETE /api/v1/documents/{id}` (Qdrant points, S3 object, SQL row)
- Ingestion worker marks documents `ready` or `failed` (page/concurrency limits from env)
- Garage S3 API: http://localhost:3900 (path-style; bucket from `S3_BUCKET`)

## Managed Postgres, Amazon S3, and Kubernetes

`deploy/kubernetes/` runs namespace `ai-rag` against external Postgres, Redis, Qdrant, and one Amazon S3 bucket. `api` and Job `ai-rag-migrate` use image `ai-rag-api:latest`. The worker uses `ai-rag-worker:latest`, the image built with `docker build --target worker`, and sets `DOCLING_ARTIFACTS_PATH`. All three load Secret `ai-rag-env` with `envFrom`. Replace those image names with the images you push. The Secret file is placeholders only.

`DATABASE_URL` is the only database setting. The login user is `app`. Put `sslmode` in that URL when the managed server requires TLS:

`postgresql://app:PASSWORD@db.example:5432/app?sslmode=require`

Alembic reads that URL. Migration `0004` creates role `app_rls` as user `app`, so `app` must be able to `CREATE ROLE`. The session still sets role `app_rls` and `app.tenant_id`.

Amazon S3 uses the same variables as Compose, with an empty endpoint and path style off:

- `S3_ENDPOINT_URL` empty, so the client uses `endpoint_url=None`
- `S3_REGION`, for example `us-east-1`
- `S3_BUCKET` for the one bucket
- `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`
- `S3_USE_PATH_STYLE` `false`, so the client passes `config=None`

Object keys stay `tenant_id/document_id/filename`. Local Compose keeps Garage at `http://garage:3900`, region `garage`, and path style `true`.

Set `JWT_SECRET` in `ai-rag-env` to a long random value. The example leaves it empty, and the API refuses to start when that variable is empty or `change-me`. The API process stays the image command (uvicorn on port 8000). The worker command is `celery -A app.infrastructure.worker.celery_app:celery_app worker --loglevel=INFO`. Liveness is `GET /api/health`. Readiness is `GET /api/ready`. The worker has no HTTP probe. Job `ai-rag-migrate` runs `alembic upgrade head` with `restartPolicy: Never`.

Apply the namespace, the Secret, and the migrate Job. Wait until `job/ai-rag-migrate` completes, then apply `api` and `worker`. A later `kubectl apply` does not start a completed Job again. Delete `job/ai-rag-migrate` before applying a newer Alembic revision.

```bash
kubectl apply -f deploy/kubernetes/namespace.yaml
kubectl apply -f deploy/kubernetes/secret.yaml
kubectl apply -f deploy/kubernetes/migrate-job.yaml
kubectl wait --for=condition=complete job/ai-rag-migrate -n ai-rag
kubectl apply -f deploy/kubernetes/api.yaml
kubectl apply -f deploy/kubernetes/worker.yaml
```

After the Job has completed and the API pod is up, create the first tenant with one exec. Pass the bootstrap variables on that command. Leave `BOOTSTRAP_ADMIN_PASSWORD` out of Secret `ai-rag-env`.

```bash
kubectl exec -n ai-rag deploy/api -- env \
  BOOTSTRAP_TENANT_NAME="Demo Company" \
  BOOTSTRAP_ADMIN_EMAIL="admin@example.com" \
  BOOTSTRAP_ADMIN_PASSWORD="choose-a-password" \
  python -m app.cli bootstrap
```

API and domain tests (no Docker):

```bash
cd apps/api
pip install -e ".[dev]"
pytest
```

## What this seed includes

- Compose services: `postgres`, `qdrant`, `redis`, `garage`, `api`, `worker`, `web`
- Wired slices: **health / readiness**, **identity / tenancy**, **document upload / list**, and **ingestion** (ready / re-ingest / delete)
- Alembic owns `tenants`, `users`, and `documents`
- Domain model for tenant, user, document, and conversation
- React features for health, documents, and chat (documents/chat UI still empty states)

## Next slices

1. ~~Identity and tenancy (auth, tenant from authenticated context)~~
2. ~~Documents (PDF upload; Garage/S3; list as pending)~~
3. ~~Ingestion (Celery: extract → chunk → embed; replace/delete)~~
4. Retrieval (Qdrant filter by `tenant_id`)
5. Chat (grounded answers + citations)
6. RAG engineering and evaluation
7. Production hardening
