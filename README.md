# AI-RAG

AI Knowledge Assistant grounded in organization documents.

Generated from `ai-rag-fastapi-react` 1.0. This repository is independent from
the `project-blueprint` factory.

## Stack

- React (Vite) → FastAPI
- PostgreSQL, Qdrant, Redis, Celery
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

API and domain tests (no Docker):

```bash
cd apps/api
pip install -e ".[dev]"
pytest
```

## What this seed includes

- Compose services: `postgres`, `qdrant`, `redis`, `api`, `worker`, `web`
- Wired slices: **health / readiness** and **identity / tenancy** (bootstrap CLI, Bearer JWT, `/api/v1` envelope)
- Alembic owns the `tenants` and `users` tables (this identity slice); later document tables will add migrations too
- Domain model for tenant, user, document, and conversation
- React features for health, documents, and chat (documents/chat are empty states)

## Next slices

1. ~~Identity and tenancy (auth, tenant from authenticated context)~~ (in progress / this slice)
2. Documents (PDF upload; more SQLAlchemy/Postgres tables)
3. Ingestion (Celery: extract → chunk → embed)
4. Retrieval (Qdrant filter by `tenant_id`)
5. Chat (grounded answers + citations)
6. RAG engineering and evaluation
7. Production hardening
