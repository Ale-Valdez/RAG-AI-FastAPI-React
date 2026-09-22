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
