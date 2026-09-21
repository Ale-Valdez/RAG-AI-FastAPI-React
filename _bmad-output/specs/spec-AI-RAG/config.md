# Environment configuration

Product values that must be read from the environment (never committed). Names below are binding for MVP. Secrets stay in `.env` / env, not in source.

## Bootstrap (identity-and-tenancy)

Used by `python -m app.cli bootstrap`. Creates one `Tenant` and one password-authenticated `User`. Idempotence is an identity-slice detail; the command is the only MVP provision path.

| Variable | Purpose |
| --- | --- |
| `BOOTSTRAP_TENANT_NAME` | Tenant display name (example: `Demo Company`) |
| `BOOTSTRAP_ADMIN_EMAIL` | First user email (example: `admin@example.com`) |
| `BOOTSTRAP_ADMIN_PASSWORD` | First user password; store only a hash |

"Admin" names this bootstrap account. It is not a `Role` on `Actor`.

## Document / ingest limits (documents, ingestion)

| Variable | MVP default | Rule |
| --- | --- | --- |
| `MAX_DOCUMENT_SIZE_MB` | `20` | Reject upload over this size |
| `MAX_DOCUMENT_PAGES` | `100` | Fail ingest if the PDF has more pages |
| `MAX_CONCURRENT_INGESTIONS_PER_TENANT` | `2` | At most this many in-flight (`processing`) ingestions per tenant |

## Retrieval (retrieval, chat)

| Variable | MVP default | Rule |
| --- | --- | --- |
| `RAG_TOP_K` | `5` | Max chunks returned per query |
| `RAG_SCORE_THRESHOLD` | `0.70` | Chunks below this score do not ground; treat as empty retrieval |

## Already named by architecture

| Variable | Used by |
| --- | --- |
| `jwt_secret` | JWT sign/verify |
| `OPENAI_EMBED_MODEL` | Ingest and query embed (same model) |
| `OPENAI_CHAT_MODEL` | First generate adapter |
