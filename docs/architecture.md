# Architecture

AI-RAG is a multi-tenant knowledge assistant. Tenant isolation is a security
boundary. The backend follows hexagonal (ports and adapters) boundaries.

```text
React -> FastAPI -> PostgreSQL
                 -> Qdrant
                 -> Redis/Celery
                 -> OpenAI
                       |
                    RAG Engine
```

- Domain and application layers do not import FastAPI, SQLAlchemy, Celery, or Qdrant.
- Infrastructure implements ports. The composition root lives in `apps/api/src/app/bootstrap/`.
- Retrieval must always filter by `tenant_id` from the authenticated context.
