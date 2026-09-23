---
title: 'Ask a question and keep the thread'
type: 'feature'
created: '2026-09-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '921be9b993c811459a773fa141451b255d75d4dc'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Ready chunks can be retrieved, but a member still cannot ask a question, receive a cited answer, or reopen that exchange later.

**Approach:** An authenticated ask uses the existing retrieve use case, generates only when chunks clear the score threshold, and stores the user and assistant messages on a conversation owned by that user in that tenant. The same user can append another question and reload the thread.

## Boundaries & Constraints

**Always:**
- `Actor` comes from the verified JWT. A client tenant is never the filter.
- Ask calls `RetrieveChunks` and passes that ask's optional `document_id`. It does not embed or query Qdrant itself.
- The generator sees the current question and the retrieved chunk texts. Stored messages are returned on reload and are not sent to the model as facts.
- When retrieval returns no chunks, the assistant content is exactly `I don't know based on the ready documents.`, `sources` is empty, and the generator is not called. The turn is still saved.
- Each source is a `SourceRef` (`document_id`, `filename`, `page`, `chunk_index`) copied from the hit. No second citation type. `score` and chunk `text` are not sources.
- `conversations` and `messages` both store `tenant_id`. Load and list keep rows whose `tenant_id` and `user_id` match the actor. A missing id, another user, or another tenant raises `NotFoundError` and does not generate or write.
- A `document_id` that is missing, in another tenant, or not `ready` raises `NotFoundError` before any conversation row is written.
- A blank or whitespace question raises `DomainError` before retrieve. Nothing is saved.
- A question on an existing id appends one user message and one assistant message. Prior messages stay.
- Use cases are synchronous and take `Actor`. Domain and application do not import FastAPI, SQLAlchemy, Qdrant, LangChain, or OpenAI.
- Product JSON is `{data, error}`. Conversation ids are UUID strings. Chat model id is `OPENAI_CHAT_MODEL` (default `gpt-4o-mini`). Embedding stays `OPENAI_EMBED_MODEL`. `RAG_TOP_K` and `RAG_SCORE_THRESHOLD` are the retrieve settings.
- Domain and application tests use in-memory fakes. No Docker.

**Never:**
- Changes to `apps/web`. Browser sign-in stays deferred.
- A second Qdrant collection, creating `chunks` on ask, or changes to upsert, delete, `ProcessDocument`, document HTTP, or auth.
- Hybrid search, rerank, query rewrite, roles, LangChain, or a Celery chat job.
- Ungrounded generation when retrieval is empty.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Grounded ask | Actor A; qualifying ready chunks | New conversation: user question, assistant answer, `SourceRef`s from those chunks. Generator called with those texts | N/A |
| Empty retrieval | No ready documents, or none score at or above the threshold | Turn saved. Assistant content is the refusal sentence. `sources` empty. Generator not called | N/A |
| Continue | A's conversation and a second question | One user message and one assistant message appended. Earlier messages unchanged | N/A |
| Reload | Same user and tenant | Messages and sources in write order | N/A |
| List | A's threads | Ids and `created_at` only, newest first. No other user's rows | N/A |
| Other owner | Id owned by another user or tenant | No generate and no write | `NotFoundError` |
| Bad document | `document_id` missing, other tenant, or not `ready` | No row written | `NotFoundError` |
| Blank question | Whitespace question | No retrieve | `DomainError` |
| No token | Product route without a Bearer token | Use case not called | 401 |

Routes: `POST /api/v1/conversations` (201), `POST /api/v1/conversations/{id}/messages` (200), `GET /api/v1/conversations/{id}` (200), `GET /api/v1/conversations` (200). Body is `{question, document_id?}`. A conversation payload is `{id, messages: [{role, content, sources}]}`. List payload is `{conversations: [{id, created_at}]}`.

</frozen-after-approval>

## Code Map

- `apps/api/src/app/domain/chat.py` — reuse `SourceRef`, `Message`, `Conversation.add_message`. Add `created_at` on `Conversation` for list ordering.
- `apps/api/src/app/application/retrieval/retrieve_chunks.py` — call `execute(actor, question, document_id)`. Do not change ready-id or `NotFoundError` rules.
- `apps/api/src/app/domain/ports/retrieval.py` — map `RetrievedChunk` cite fields onto `SourceRef`. Leave `text` and `score` off the citation.
- `apps/api/src/app/domain/errors.py` — `NotFoundError` for a bad thread or document; `DomainError` for a blank question (HTTP 409 via the existing handler).
- `apps/api/src/app/infrastructure/config/settings.py` and `.env.example` — add `OPENAI_CHAT_MODEL=gpt-4o-mini`. Keep `RAG_*` and `OPENAI_EMBED_MODEL`.
- `apps/api/src/app/infrastructure/ingestion/openai_embeddings.py` — copy the `OpenAI` client setup. Chat completions live in a new generator, not this class.
- `apps/api/src/app/infrastructure/persistence/models.py` and `alembic/versions/0002_documents.py` — next revision `0003`, `down_revision` `0002_documents`. Both new tables include `tenant_id`. Message `sources` is JSON.
- `apps/api/src/app/infrastructure/persistence/document_repository.py` — copy the session repository style. Filter list and get by the actor's tenant and user.
- `apps/api/src/app/bootstrap/create_app.py` — optional chat use cases, same injection style as documents. `LazySessionFactory` and `QdrantChunkStore` stay lazy so current `create_app(...)` tests stay offline. Pass `rag_top_k` and `rag_score_threshold` into `RetrieveChunks` here.
- `apps/api/src/app/infrastructure/http/documents_router.py` and `responses/api_response.py` — copy `build_*_router`, `build_require_actor`, and `success_body`.
- `apps/api/tests/fakes.py` and `tests/test_retrieve_chunks.py` — add an in-memory conversation store and a fake generator. Follow the retrieve matrix style.
- `apps/api/tests/test_documents_http.py` — HTTP tests inject use cases into `create_app` and assert the envelope. Do not change document cases.
- `apps/api/tests/test_persistence.py` — `test_alembic_upgrade_creates_tenant_and_user_schema` asserts table names after `upgrade head`. Extend it for the new tables.
- `apps/web/` — do not change. `ChatPage` stays the placeholder.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/ports/generation.py` and `domain/ports/conversations.py` — generator takes question and context texts; repository saves, loads, and lists for the actor
- [x] `apps/api/src/app/application/chat/ask_question.py` — retrieve, refuse or generate, append both messages, save — one turn
- [x] `apps/api/src/app/application/chat/get_conversation.py` and `list_conversations.py` — reload and list for the actor only
- [x] `apps/api/src/app/infrastructure/config/settings.py` and `.env.example` — add `OPENAI_CHAT_MODEL`
- [x] `apps/api/src/app/infrastructure/persistence/models.py` and `alembic/versions/0003_conversations.py` — `conversations` and `messages`, both with `tenant_id`
- [x] `apps/api/src/app/infrastructure/persistence/conversation_repository.py` — map rows to `Conversation` and `Message`
- [x] `apps/api/src/app/infrastructure/chat/openai_answer_generator.py` — chat completions via the official `openai` SDK and `OPENAI_CHAT_MODEL`
- [x] `apps/api/src/app/infrastructure/http/conversations_router.py` and `bootstrap/create_app.py` — four authenticated routes and session-bound wiring
- [x] `apps/api/tests/fakes.py`, `tests/test_ask_question.py`, and `tests/test_conversations_http.py` — matrix cases, including both tenants, with fakes and no Docker
- [x] `apps/api/tests/test_persistence.py` — Alembic head creates both new tables with `tenant_id`

**Acceptance Criteria:**
- Given chunks for tenants A and B, when A asks, then retrieval runs as A and every source on the answer belongs to A's ready chunks
- Given no chunk at or above the threshold, when A asks, then the stored answer is the refusal sentence and the generator is not called
- Given a saved thread, when that user reloads or continues it, then messages and sources return in order; another user or tenant gets `NotFoundError` and no write
- Given this story, when it is implemented, then `apps/web` is unchanged and `chunks` is still the only Qdrant collection

## Implementation Notes

Ask, reload, list, and continue are in place. Empty retrieval stores the refusal and does not call the generator. `cd apps/api && uv run --extra dev pytest` — 154 passed. The default ask path keeps the database session open across embed and chat completion. The OpenAI adapter was checked with a stub client.

## Spec Change Log

## Review Triage Log

- `low` — `SessionBoundAskQuestion` keeps the database session open across embed and chat completion. Postgres is not configured to abort idle transactions, and one ask holds one connection for that call. Rejected: closing the session around only the save is a restructure, and a single ask does not exhaust the pool.
- `low` — two continues that both loaded the same thread can overwrite each other in `save`, because messages are replaced without a row lock. Rejected: everyday use sends one question at a time, and the fix adds locking.
- `false` — `save` can reassign another tenant's conversation. `AskQuestion` loads with `get_for_actor` and raises `NotFoundError` before `save`, so a mismatched id is never written.
- `low` — the migration has no foreign key, no unique `(conversation_id, position)`, and no `(tenant_id, user_id)` index. Rejected: this story has no conversation delete, and the extra constraints are not a direct correction.
- `false` — SQL `list_for_actor` returns empty `messages`, unlike the fake. `GET /api/v1/conversations` serializes only `id` and `created_at`, so those messages are not in the response.
- `low` — the generator sends excerpts and the question in one user message, stores an empty completion with sources, and indexes `choices[0]` with no guard. Rejected: the spec only requires the question and chunk texts to be sent, and an empty completion already fails the request before `save`.
- `low` — a non-blank question has no maximum length. Rejected: the spec rejects only whitespace, and a length limit is a new rule.
- `medium` — `test_conversation_repository_round_trip_is_actor_scoped` uses `user_id` `u1` for both actors, so removing the SQL `user_id` predicate still passes. The same bullet notes that a follow-up with a bad `document_id` is not asserted. The `user_id` filter is in the repository; the test does not lock it. A bad `document_id` on an existing id raises `NotFoundError` before `add_message` and `save`.
- `false` — a partial `sources` JSON object fails reload, and a later delete can leave a stale `SourceRef`. `save` writes all four citation fields, and the spec forbids changes to delete and reingest.
- `low` — `Settings()` in `test_chat_model_setting_defaults_to_gpt_4o_mini` still reads the process environment, so an exported `OPENAI_CHAT_MODEL` changes the assertion. The sprint-status `in-progress` value is the workflow sync for this step, not a product defect.
- `low` — concurrent continues can lose a turn. Same race as the unlocked `save`. Rejected: one question at a time, and the fix adds locking.
- `low` — an idle-transaction timeout can discard an answer generated inside `session_scope`. No such timeout is configured. Rejected: same session-scope case as the first row.
- `false` — a completion with no choices crashes the ask and stores nothing. That request already fails before `save`; raising a different error does not change the stored result.
- `low` — a non-blank question has no maximum length. Same unbounded-question case. Rejected.
- `medium` — SQL `get_for_actor` and `list_for_actor` filter on `user_id`, and the only SQL test hides rows by `tenant_id` alone. Dropping `ConversationRow.user_id == actor.user_id` keeps that test green. Patch: assert a same-tenant other user.
- `medium` — SQL `list_for_actor` orders by `created_at` descending, and the SQL test lists one row, so oldest-first still passes. The newest-first test uses the in-memory fake. Patch: assert two SQL rows, newer first.
- `medium` — `_default_chat` passes `rag_top_k`, `rag_score_threshold`, and `openai_chat_model` into the ask object, and no test reads those fields. Route and HTTP tests inject their own `AskQuestion`. Patch: assert the stored settings without calling OpenAI or opening a database connection.
- `medium` — the default ask path holds the database transaction open across embed and chat completion. Same session-scope case as the first row. Rejected: one connection per ask, and the fix is a restructure.

## Design Notes

Empty retrieval is an answer, not a missing thread: the turn is stored so reload shows the refusal. A bad `document_id` fails before `save`, so a new id is not left empty. Follow-up turns retrieve again; the model does not read older assistant text.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` -- expected: existing tests pass; ask, HTTP, and Alembic tests pass; no Docker
