# Slice map — MVP vs later

Implementation order is binding. Do not skip ahead of `identity-and-tenancy`. Later slices assume `Actor` and JWT already exist.

## MVP (CAP-1 .. CAP-8)

| Slice | Capabilities | Lives in | Governed by |
| --- | --- | --- | --- |
| identity-and-tenancy | CAP-1 | `domain` identity/tenancy + HTTP auth adapter + bootstrap CLI adapter + SQL User/Tenant | AD-2, AD-8, AD-9, AD-10 |
| documents | CAP-2, CAP-3, CAP-8 (HTTP enqueue + delete/re-ingest entry) | `domain` Document + `DocumentBytes` + SQL | AD-2, AD-4, AD-6, AD-9, AD-10, AD-11, AD-12 |
| ingestion | CAP-3 (status writer), CAP-4, CAP-8 (delete points then upsert) | `ProcessDocument` + Celery adapter + extract/chunk/embed/upsert | AD-2, AD-3, AD-4, AD-5, AD-6, AD-7, AD-9, AD-12 |
| retrieval | CAP-5 | retrieve port + Qdrant adapter (`RAG_TOP_K`, `RAG_SCORE_THRESHOLD`) | AD-2, AD-5, AD-7, AD-11 |
| chat | CAP-6, CAP-7 | Conversation/Message + retrieve (optional `document_id`) + context assembly + generate + HTTP/web under `/api/v1` `{data, error}` | AD-2, AD-5, AD-7, AD-8, AD-9, AD-10, AD-11 |

Garage Compose service and S3 env land with **documents**. SQLAlchemy/Alembic land with **identity** (first tenant-owned tables), along with bootstrap CLI and password hash. qdrant-client + embed model land with **ingestion**; retrieval/chat consume the same collection. openai chat client lands with **chat**. PyJWT lands with **identity**. Env names live in `config.md`.

## Later (CAP-9 .. CAP-11)

| Slice | Capabilities | Governed by | Revisit when |
| --- | --- | --- | --- |
| rag-engineering | CAP-9 | AD-5, AD-7; hybrid/rerank/query-rewrite deferred | quality work behind the same ports |
| evaluation | CAP-10 | AD-4 (same worker rule) | eval jobs are needed |
| production-hardening | CAP-11 | env, RLS, OIDC, observability | production topology |

## Deferred (not MVP; do not invent in earlier slices)

| Item | Why it can wait | Revisit when |
| --- | --- | --- |
| Postgres RLS | Actor + column filter + Qdrant filter + key prefix are the isolation boundary | production-hardening |
| OIDC / cookies / refresh / revocation | Local JWT is enough for first slices | production-hardening, or identity needs an IdP |
| Roles / in-tenant ACL | AD-11: all tenant members share the corpus | a slice needs more than tenant membership |
| FastAPI 0.141 / Qdrant 1.19 / Vite 8 bumps | Installed seed; qdrant-client tracks compose 1.13 | a slice that needs a current feature |
| Hybrid retrieval, rerank, query rewrite | Sequenced later in `docs/rag.md` | rag-engineering |
| Chat/generate model id | Config (`OPENAI_CHAT_MODEL`); not the vector schema | first generate adapter |
| PDF extractor library | Behind the extract port; format is PDF | ingestion slice |
| Kafka / domain events | Celery covers async jobs | a slice needs fan-out beyond one worker |
| k8s, managed Postgres, Amazon S3 topology | Compose is the named environment | production-hardening |
| Structured logging / tracing | `/health` and `/ready` exist | production-hardening |
| LangChain | Explicitly not the engine | only if a later AD changes AD-5 |

## Epic decomposition hint

Independently reviewable MVP slices match the five rows in the MVP table. CAP-8 spans documents + ingestion + retrieval stores and should not be scheduled before those ports exist. CAP-9..CAP-11 are separate later epics.
