# Stack

Seed at architecture authoring (2026-09-18). **Installed** = lockfile/compose today. **Intended** = add when the slice needs it; code then owns the pin. Do not introduce technologies outside this table unless a later architecture decision changes it.

| Name | Version |
| --- | --- |
| Python | >=3.12 (installed) |
| FastAPI | 0.115.12 (installed) |
| uvicorn | 0.34.2 (installed) |
| pydantic | 2.11.7 (installed) |
| pydantic-settings | 2.8.1 (installed) |
| Celery | 5.4.0 (installed) |
| redis (Python) | 5.2.1 (installed) |
| httpx | 0.28.1 (installed) |
| SQLAlchemy | 2.0.54 (intended) |
| Alembic | 1.20.0 (intended) |
| qdrant-client | 1.13.3 (intended; match compose Qdrant 1.13) |
| openai | 3.14.0 (intended) |
| boto3 | 1.43.98 (intended) |
| PyJWT | 2.14.0 (intended) |
| React | 19.1.0 (installed) |
| react-dom | 19.1.0 (installed) |
| react-router-dom | 7.6.1 (installed) |
| TypeScript | 5.8.3 (installed) |
| Vite | 6.3.5 (installed) |
| PostgreSQL | 16-alpine (installed) |
| Redis | 7.4-alpine (installed) |
| Qdrant | v1.13.2 (installed) |
| Garage | dxflrs/garage:v2.4.1 (intended Compose add) |

Secrets from env / `.env`. Product env names (bootstrap, ingest limits, `RAG_TOP_K`, `RAG_SCORE_THRESHOLD`) are in `config.md`. FastAPI 0.141 / Qdrant 1.19 / Vite 8 bumps are not invariants. PDF extractor library is behind the extract port, chosen at the ingestion slice. Password hashing library is chosen at the identity slice. Chat model id is `OPENAI_CHAT_MODEL` at the first generate adapter. Product HTTP routes are under `/api/v1` and use the `{data, error}` envelope in `http-envelope.md`.
