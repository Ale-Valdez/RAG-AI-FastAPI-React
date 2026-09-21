# Agent Instructions

Project: AI-RAG (`ai-rag`)

AI Knowledge Assistant grounded in organization documents.

Blueprint: `ai-rag-fastapi-react` 1.0

## Rules

1. Tenant isolation is a security boundary. `tenant_id` comes from the authenticated context, never from an untrusted client field used as the only filter.
2. Domain logic stays independent of FastAPI, SQLAlchemy, Celery, Qdrant, and LangChain.
3. Use cases do not take `Request`/`Response`. HTTP adapters map domain errors to status codes.
4. Do not invent backend behavior in the React app. Handle loading, empty, and error states.
5. Never commit secrets. Read configuration from the environment.
6. Add tests with each use case. Domain tests use in-memory fakes (no Docker).
7. Implement one vertical slice at a time. Do not add empty layer folders.

## Layout

- `apps/api/src/app/domain/` — entities, value objects, errors, port interfaces
- `apps/api/src/app/application/` — use cases
- `apps/api/src/app/infrastructure/` — HTTP, persistence, queues, vector store
- `apps/api/src/app/bootstrap/` — composition root
- `apps/web/src/features/` — UI by feature; `apps/web/src/api/` talks to the backend

## Slice order

identity-and-tenancy → documents → ingestion → retrieval → chat → rag-engineering → evaluation → production-hardening
