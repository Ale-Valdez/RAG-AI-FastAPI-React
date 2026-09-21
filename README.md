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
docker compose up --build
```

- Web: http://localhost:5173
- API health: http://localhost:8000/api/health
- API ready: http://localhost:8000/api/ready

API and domain tests (no Docker):

```bash
cd apps/api
pip install -e ".[dev]"
pytest
```

## What this seed includes

- Compose services: `postgres`, `qdrant`, `redis`, `api`, `worker`, `web`
- One wired slice: **health / readiness**
- Domain model for tenant, user, document, and conversation
- React features for health, documents, and chat (documents/chat are empty states)

## Next slices

1. Identity and tenancy (auth, tenant from authenticated context)
2. Documents (PDF upload; add SQLAlchemy/Postgres persistence here)
3. Ingestion (Celery: extract → chunk → embed)
4. Retrieval (Qdrant filter by `tenant_id`)
5. Chat (grounded answers + citations)
6. RAG engineering and evaluation
7. Production hardening
