# Adversary review — ARCHITECTURE-SPINE.md

- **Target:** `_bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md`
- **Altitude:** feature (units one level down = slices/epics: identity-and-tenancy, documents, ingestion, retrieval, chat, …)
- **Stance:** two independent implementers, each obeying every AD *to the letter*, shipping on the same composition root
- **Spine not modified.** Every pair below is a hole: new AD or a tightened Rule (Prevents that the Rule does not actually stop is an open hole)

## Verdict

**Fail — not yet a consistency contract.** Hexagonal layering, Actor-as-isolation-key, sync use cases, worker-as-adapter, one-bucket S3, one filtered Qdrant collection, and domain-error HTTP mapping are named. Their Rules still leave shared *shapes*, *owners*, and *mutation paths* unbound. Independently built **documents** and **ingestion**, or **ingestion** and **retrieval/chat**, can be fully AD-compliant and not interoperate.

The Capability map makes this worse: it withholds ADs from slices that must share the store those ADs describe (documents unbound from AD-7; ingestion unbound from AD-2/AD-9; chat unbound from AD-7/AD-9; retrieval unbound from AD-2). A builder who uses that map as the auditor's checklist will miss constraints the AD `Binds` lines only imply.

---

## Method

For each pair: construct Unit A and Unit B (real next-slice names). Quote the AD text they satisfy. Show the incompatible artifact (data shape, entity owner, or write path). Name the AD to add or tighten. Brownfield (`apps/api/src/app/domain/*`, Celery queue, HTTP error handlers) is cited only when it shows the spine failed to ratify an already-visible call — it is not a free pass to leave the contract open.

---

## Worked attack 1 — documents vs ingestion

Two slices, sequential in AGENTS.md, sharing Document bytes, Document status, and the job record.

### Unit D — documents (obeys AD-1, AD-2, AD-3, AD-6, AD-8, AD-9, AD-10; uses AD-4 only to "enqueue")

Upload use case `UploadDocument.execute(actor: Actor, filename: str, data: bytes) -> Document`:

- UUID id in application; `Document` PENDING; SQL row with `tenant_id`; bytes via a domain port.
- S3 adapter, one bucket, key `f"{actor.tenant_id}/{document.id}/{filename}"` (the `...` in AD-6).
- Enqueues Celery with JSON `{"tenant_id": actor.tenant_id, "user_id": actor.user_id, "document_id": document.id}`.
- Calls `document.mark_processing()` **before** commit so the UI leaves PENDING immediately (status machine lives on the entity; HTTP is a use-case caller; AD-4 does not say who fires PENDING→PROCESSING).
- Blob port named `BlobStore.put/get` in `domain/documents`.
- Table `document` (singular), status stored as `"PENDING"` to match the convention spelling.
- Delete: SQL row + S3 keys under prefix. Qdrant is not this slice (Capability map: documents governed by AD-2, AD-6, AD-9, AD-10 — not AD-7).

### Unit I — ingestion (obeys AD-1, AD-3, AD-4, AD-5, AD-6, AD-7)

`ProcessDocument.execute(actor: Actor, document_id: str) -> None` invoked from the worker:

- Builds `Actor` from the job record as `{actor: {tenant_id, user_id}, document_id}` (AD-4: "the job payload carries the enqueuing Actor"; AD-8: not the JWT).
- Blob port named `DocumentBytes.fetch(tenant_id, document_id)` looking up key `f"{tenant_id}/{document_id}/bytes"` (also matches `tenant_id/document_id/...`).
- Loads SQL `documents` (plural). Status values `"pending"` (brownfield `DocumentStatus` is lowercase; spine convention is uppercase — neither AD binds the wire value).
- `mark_processing()` at job start, then extract/chunk/embed/upsert, then `mark_ready()` / `mark_failed()`.
- Qdrant collection `chunks`; point ids = fresh UUIDs; Cosine, dim 1536; payload fields exactly AD-7; **no `text`**; `page` as 0-based int; `tenant_id` as the `TenantId` VO `repr`.
- On failure writes `IngestRun` (new domain type — AD-1) with its own status, because Capability map says ingestion does not own `Document` + SQL (not AD-9).

### What collides

| Shared thing | D | I | Result |
| --- | --- | --- | --- |
| S3 key | `{tenant}/{id}/{filename}` | `{tenant}/{id}/bytes` | Worker never sees the object |
| Job envelope | flat `tenant_id, user_id` | nested `actor: {…}` | Worker cannot build Actor |
| PENDING→PROCESSING | HTTP, at enqueue | worker, at start | Second `mark_processing()` raises `InvalidDocumentTransition` (brownfield already requires PENDING) |
| Document row | table `document`, status `PENDING` | table `documents`, status `pending` | Repo miss / unreadable status |
| Lifecycle owner | `Document` is source of truth | `IngestRun` is source of truth | Two entities for one document |
| Delete | SQL + S3 | upsert-only Qdrant | Chat retrieves ghosts |

Every cell is legal under the current Rules.

---

## Worked attack 2 — ingestion vs retrieval (+ chat as the consumer)

AD-5 lists six ports and no signatures. AD-7 lists five payload *names* and no collection identity, vector space, point id, value types, or body text. Capability map: retrieval = AD-5, AD-7 (not AD-2); chat = AD-2, AD-5, AD-8, AD-10 (not AD-7, not AD-9).

### Unit I — ingestion (same as above, plus)

`EmbedPort.embed_passages(texts: list[str]) -> list[list[float]]` using env `OPENAI_EMBED_MODEL=text-embedding-3-small` (Deferred: "LLM/embedding model IDs — Config, not architecture"). Upsert into collection `chunks`, unnamed vector, dim 1536, Cosine. Payload:

```json
{"tenant_id": "TenantId(value='…')", "document_id": "…", "filename": "a.pdf", "page": 0, "chunk_index": 0}
```

Point id = random UUID. Chunker: 800 chars, overlap 0, `page=0` for the whole PDF if the extractor returns one blob. Does not persist chunk text (not in AD-7's list).

### Unit R — retrieval

`RetrievePort.search(query_vector, tenant_id: str, k: int)` — a port, not a use case, so AD-2's "every use case takes Actor" does not apply. HTTP `GET /search?q=` still builds Actor from JWT (AD-2/AD-8) and passes `actor.tenant_id` into the filter (AD-7).

- Collection `ai_rag` (AD-7 says *one* collection, not its name).
- Named vector `dense`, dim 3072, Dot product.
- Query embed via `EmbedPort.embed_query(q: str)` and `text-embedding-3-large` (Deferred allows it).
- Filter `{ tenant_id: actor.tenant_id }` where `Actor.tenant_id` is a `TenantId` VO — compared to ingestion's stringified repr, never matches.
- Expects payload `text` to return hits; AD-7 does not require it.
- Point id treated as `{document_id}:{chunk_index}` for later delete-by-id.

### Unit C — chat

`AskQuestion.execute(actor, conversation_id, question)` orchestrates retrieve + generate (AD-5: use cases orchestrate ports). Because the Capability map does not put AD-7 on chat, C may:

- Define a second `RetrievePort` in `domain/chat` and a second Qdrant adapter (still one collection *per adapter config* — two names).
- Persist `Conversation` / `Message` in process memory or as JSON on the conversation row, skipping a `messages` table with `tenant_id` (AD-9 binds "chat persistence" but the map that chat's builder is told to follow does not list AD-9).
- Cite with `SourceRef(document, filename, page, chunk_index)` as the seed ERD prose literally says — not AD-7's `document_id`.
- `GeneratePort.complete(prompt: str) -> str` while evaluation later wants `GeneratePort.chat(messages) -> Answer`.

### What collides

Retrieval cannot read ingestion's points (wrong collection, wrong dim/metric/vector name, wrong `tenant_id` filter value). Even on a lucky shared collection, hits have no chunk text, so generate hallucinates or C re-chunks S3 bytes with a different splitter and emits `chunk_index` values that do not exist in Qdrant. Stored `SourceRef.document` does not join to payload `document_id`. Compliant, and dead.

---

## Pair catalog

Each pair: both units AD-legal; clash; closure.

### P1 — S3 object key and blob port (documents × ingestion)

- **Shape:** AD-6 Rule: "Object keys are `tenant_id/document_id/...`". The suffix is a wildcard. Two `...` expansions do not meet. Two port names (`BlobStore` vs `DocumentBytes`) are both "a domain port".
- **Obeys:** AD-6 one bucket, S3 API, tenant-prefixed keys; AD-1 one port+adapter per slice.
- **Clash:** worker 404s on get; documents delete by a prefix ingestion never wrote.
- **Close:** Tighten **AD-6**. Bind the key template (e.g. `{tenant_id}/{document_id}/source`), where `filename` / content-type live (Postgres vs object metadata), and **one** bytes port both slices import.

### P2 — Two writers of Document status (documents × ingestion)

- **Mutation:** Convention: `PENDING → PROCESSING → READY or FAILED`. AD-4 Prevents "worker vs HTTP drift on … document status". AD-4 Rule only requires shared composition root, shared *use cases*, Actor on the job, no Celery in domain. It does not name the single writer of each edge, enqueue-vs-start, retry (`FAILED → …`), or replace (`READY → PROCESSING`).
- **Obeys:** both mutate via domain methods inside use cases; worker does not bypass application.
- **Clash:** D marks PROCESSING at enqueue; I marks PROCESSING at start. Brownfield `Document.mark_processing` already requires PENDING — the second writer explodes. Retry: D requires re-upload (new id); I adds `mark_retry()` on the same entity. Capability map gives Document to documents and withholds AD-9 from ingestion, so I is invited to invent `IngestRun`.
- **Close:** New **AD-11 (Document lifecycle)**. One entity, one table. HTTP `Upload` creates PENDING and enqueues; worker `Process` is the only PROCESSING/READY/FAILED writer; name the retry/reindex edges; forbid a parallel ingest-status entity.

### P3 — Two owners of Document (documents × ingestion)

- **Owner:** Map: documents = "`domain` Document + blob port + SQL". Ingestion = "use case + Celery adapter + extract/chunk/embed/upsert ports". AD-1: "New behavior is a domain type, a port, a use case, and an adapter."
- **Obeys:** I adds `IngestRun` / `PipelineState` because ingest *is* new behavior and Document is "owned" by the other slice.
- **Clash:** READY in SQL vs FAILED on `IngestRun`; chat and UI disagree; `assert_same_tenant` on the wrong record.
- **Close:** Same **AD-11**: Document is the only lifecycle record; ingestion *uses* it, does not fork it. Capability map must list AD-2 and AD-9 on ingestion.

### P4 — Job Actor envelope and queue (documents × ingestion × evaluation)

- **Shape:** AD-4 "the job payload carries the enqueuing Actor"; AD-2 worker "builds Actor from the job record"; AD-8 "Jobs do not carry the JWT". No schema, serializer, task name, or queue.
- **Obeys:** D flat JSON; I nested `actor`; evaluation pickles the dataclass onto `celery` default queue. Seed worker already sets `task_default_queue = "ai-rag-ingestion"` — evaluation either starves or lands on the ingest worker with an unknown payload.
- **Clash:** Actor reconstruction fails; tasks never run.
- **Close:** Tighten **AD-4**. JSON envelope `{tenant_id, user_id, …ids}` (UUID strings); named queues (`ai-rag-ingestion`, `ai-rag-evaluation`); task names; both adapters deserialize into the same `Actor`.

### P5 — Qdrant point contract (ingestion × retrieval)

- **Shape:** AD-7 Prevents "mismatched payload shapes". Rule binds five field *names*, one collection, and `actor.tenant_id` on every query. Silent: collection **name**, vector name, dimension, distance, point-id scheme, payload **types**, extra fields, whether chunk **text** is stored.
- **Obeys:** both write/read those five keys and filter tenant.
- **Clash:** collection `chunks` vs `ai_rag`; unnamed 1536 Cosine vs named `dense` 3072 Dot; UUID point ids vs `{document_id}:{chunk_index}`; `page` 0-based int vs 1-based vs string; `tenant_id` VO repr vs UUID string. Zero hits, or hits that cannot be deleted by document.
- **Close:** Tighten **AD-7**. Bind collection name, single unnamed (or named) vector, distance, point id, payload types (`tenant_id`/`document_id` UUID strings, `filename` str, `page` int 1-based, `chunk_index` int 0-based, **`text` str required**). Dimension follows the one embedding model (see P6) — do not leave it as "whatever the first adapter picked".

### P6 — Deferred model IDs split the vector space (ingestion × retrieval/chat)

- **Deferred row:** "LLM/embedding model IDs | Config, not architecture | first embed/generate adapter".
- **Obeys:** both read config; both put model choice in an infrastructure adapter (AD-5).
- **Clash:** ingest embeds with model A (dim 1536); query embeds with model B (dim 3072). Qdrant rejects or returns noise. This is two units at this altitude (ingestion *and* retrieval/chat both ship an embed adapter). Deferring it **explicitly authorizes divergence**.
- **Close:** Promote out of Deferred into **AD-5 or AD-7**: one `Embeddings` port; ingest and query use the same env model; generate model may differ. Library/model *names* can stay config; **sameness** is architecture.

### P7 — Retrieve/Embed/Generate port signatures (ingestion × retrieval × chat)

- **Shape:** AD-5 names six ports; no methods, args, or return types. "Application use cases orchestrate them" allows chat to inline retrieve+generate and skip a retrieval use case, and allows a second `RetrievePort` in `domain/chat`.
- **Obeys:** AD-1/AD-5 letter.
- **Clash:** `embed_passages` vs `embed_query` as different ports/models; `search(query_vector, tenant_id: str)` vs `search(actor, query: str)` (retrieval map omits AD-2); `complete(prompt)` vs `chat(messages)`; retrieve returns raw Qdrant points vs domain hits. Chat cannot call ingestion's ports without an anti-corruption layer the spine never required — and will instead duplicate adapters.
- **Close:** Tighten **AD-5**. One protocol per operation, living under `domain/` (not per-feature packages that re-declare them). Bind `Actor` on retrieve (map currently skips AD-2). Return a domain `RetrievedChunk` (text + AD-7 identity fields + score). Chat's `AskQuestion` *calls* that port; it does not own a second Qdrant adapter.

### P8 — Chunk identity vs SourceRef (ingestion × chat)

- **Shape:** Seed: "`Message` may carry `SourceRef` (document, filename, page, chunk_index)". AD-7 payload uses `document_id`. Convention: "Page-aware chunks. Payload fields per AD-7." No chunk size, overlap, tokenizer, or stable id. No rule that citation fields ≡ payload fields.
- **Obeys:** both include page + chunk_index; chat is not bound by AD-7 on the map.
- **Clash:** `SourceRef.document` vs `payload.document_id`; 0- vs 1-based `page`; chat re-chunks at query time so stored `chunk_index` does not name a Qdrant point. Evaluation later cites a third scheme.
- **Close:** New **AD-12 (citation = payload)**. `SourceRef` fields **are** `document_id, filename, page, chunk_index` (ratify brownfield `domain/chat.py`, which already uses `document_id` — the ERD prose contradicts it). Chunker parameters are a single config consumed only by the ingest `ChunkPort`; query path must not re-split.

### P9 — Delete/replace across SQL, S3, Qdrant (documents × ingestion × retrieval)

- **Mutation:** No AD names a use case that deletes or replaces a document in all three stores. Documents not bound by AD-7; ingestion not bound by AD-9; retrieval has no write path.
- **Obeys:** D deletes SQL+S3; I only upserts; R only searches.
- **Clash:** replaced PDF keeps old points (random UUIDs cannot be overwritten in place); deleted SQL row still answers in chat. Tenant isolation holds; **document isolation** does not.
- **Close:** Fold into **AD-11**. Process/replace: delete-by-filter `{tenant_id, document_id}` then upsert. Document delete: same filter + S3 prefix + SQL, one use case both HTTP and worker can run.

### P10 — Missing resource is 404 and 409 (documents × chat × web)

- **Shape:** AD-10 Rule: "HTTP maps `TenantIsolationError` → 403, **other `DomainError` → 409**, **missing resource → 404**." If `NotFound` is a `DomainError`, both bullets apply. Brownfield `error_handlers.py` maps all `DomainError` to 409 and has **no 404**.
- **Obeys:** D raises `NotFoundError(DomainError)` → 409 (handler + "other DomainError"). C treats missing as *not* a domain error and sets 404 in the adapter. Web (AD-10) keys empty vs error off status.
- **Clash:** the same "no such document" is empty-state in chat and a conflict error on documents; web cannot implement one empty/error policy.
- **Close:** Tighten **AD-10**. Missing is 404 and is **not** a `DomainError` 409 (name `NotFound` as a distinct class or an adapter-only translation). Unauthenticated 401 (today unnamed — identity vs documents will split 401/403). Keep 403 isolation, 409 rule violation. Ratify or replace the existing handler.

### P11 — Chat persistence vs AD-9 (chat × identity/documents)

- **Owner/shape:** AD-9 Binds "identity, documents, **chat persistence**". Capability map chat **omits AD-9**. ERD: `User ||--o{ Conversation`; seed does not put `tenant_id` on `Message`. Rule: "Every tenant-owned table has `tenant_id`. Repositories always filter by `actor.tenant_id`."
- **Obeys:** C stores messages as a JSON column on `conversations` (only parent has `tenant_id`) **or** a `messages` table without `tenant_id` (child "not tenant-owned"). Identity/documents put `tenant_id` on every row they own.
- **Clash:** list-by-`user_id` without tenant predicate; cross-tenant conversation id leak if UUID is known; Alembic heads: three slices ship `001_initial.py` with `users` vs `user`, `conversations` vs `thread`.
- **Close:** Tighten **AD-9**. Table names; `tenant_id` on **every** row including `messages`; filter `actor.tenant_id` **and** (for conversations) `actor.user_id` if threads are user-private — that visibility rule is currently silent and will split "tenant inbox" vs "private threads". One Alembic chain, linear revisions, identity goes first.

### P12 — Actor / tenant_id wire type (identity × ingestion × retrieval)

- **Shape:** AD-2: `Actor (tenant_id + user_id)`. Brownfield already has `TenantId` / `UserId` VOs; `Document.tenant_id: TenantId`; `assert_same_tenant`. No rule that Actor uses those VOs, or that JSON/JWT/Qdrant/SQL store `tenant_id` as the UUID **string**.
- **Obeys:** identity JWT claims `user_id`/`tenant_id` strings (AD-8). Ingestion payload writes `str(tenant_id_vo)`. Retrieval filters with the VO object or `.value`.
- **Clash:** filters never match; SQL UUID vs VARCHAR vs VO-repr. Isolation code looks correct and is not.
- **Close:** Tighten **AD-2**. `Actor` holds `TenantId` + `UserId`; JWT, job JSON, SQL columns, S3 prefix, and Qdrant payload all use `.value` (UUID string). Map retrieval as AD-2.

### P13 — Web token and success envelopes (identity-web × documents-web × chat-web)

- **Shape:** AD-8: Bearer, token in memory not `localStorage`. AD-10: error envelope `{"detail": "<message>"}` only. Success list/detail DTOs, auth module owner, and 401 handling are free.
- **Obeys:** each feature folder keeps its own in-memory token and its own `{items}` vs `{data}` vs `{conversations}` list shape. `apps/web/src/api/client.ts` today has **no Authorization header** — slices will patch it differently.
- **Clash:** documents logged in, chat 401; error parsing OK, list parsing not shareable.
- **Close:** Tighten **AD-8** (single in-memory session owned by identity feature) and **AD-10** or a convention row: success resources named, dates UTC ISO-8601 with `Z`, document `status` wire values (`pending|processing|ready|failed` — ratify the enum, drop the uppercase convention that already contradicts code).

---

## ADs whose Prevents the Rule does not enforce

These look closed on a skim. They are the reason the pairs above are legal.

| AD | Prevents (claimed) | Rule actually binds | Residual |
| --- | --- | --- | --- |
| AD-4 | worker vs HTTP drift on document status | share use cases + Actor on job | who writes which edge; job JSON shape |
| AD-5 | chat vs ingestion different chain styles | six port *names*; no LangChain in domain/app | signatures, one vs two adapters, embed sameness |
| AD-6 | bucket-per-tenant vs key-prefix splits | one bucket + prefix `tenant_id/document_id/...` | the `...`; port name; metadata |
| AD-7 | mismatched payload shapes | five names + tenant filter | types, text, collection name, vector space, point id |
| AD-10 | React inventing error semantics | 403/409/404 + `detail` string | 404 vs DomainError; 401; success DTO |
| AD-9 | unscoped queries | tenant_id column + filter | messages; table names; user vs tenant visibility |

---

## Capability map holes (amplifiers, not extra pairs)

If the map is the "consistency auditor's checklist", it currently **un-binds** the stores slices must share:

| Slice | Map omits | Effect |
| --- | --- | --- |
| documents | AD-4, AD-7 | enqueue/job shape and Qdrant delete are "someone else's problem" |
| ingestion | AD-2, AD-9, AD-10 | Actor/SQL/status feel optional; `IngestRun` fork |
| retrieval | AD-2 | `tenant_id: str` port vs Actor |
| chat | AD-7, AD-9 | second retrieve adapter; persistence without tenant columns |
| evaluation | AD-2, AD-3, AD-5 | new job/port style |

Closing the pairs without fixing this map will still fork implementers who only read the table.

---

## Deferred items that let two in-scope units diverge

At feature altitude, Deferred may not authorize a split between slices this spine already binds.

| Item | Why it is a hole now |
| --- | --- |
| LLM/embedding model IDs | Ingest and query adapters are two units in scope (P6) |
| PDF extractor library / "documents/ingestion slice" | Two slices named as revisit; documents may pre-extract, ingestion extract again |
| Roles on Actor | Fine until a slice needs them — leave |
| Hybrid / rerank | Fine if they stay behind the **same** retrieve port and collection (named vectors). Say that, or rag-engineering will add a second collection and violate AD-7 "in spirit" while arguing AD-7 only forbids collection-per-tenant |
| Kafka / domain events | Fine |
| RLS / OIDC / k8s / logging | Fine for production-hardening |

Silent (not even Deferred): chunk size/overlap; conversation visibility (tenant vs user); HTTP path prefix; success JSON; Qdrant collection name; S3 key suffix; job envelope.

---

## Brownfield the spine should have ratified (so slices do not "lawfully" contradict code)

These are not extra pairs; they are evidence the contract is thinner than the repo:

- `DocumentStatus` values are `pending|processing|ready|failed`; convention writes `PENDING → …`
- `mark_processing` only from PENDING — P2 is already a runtime exception
- `SourceRef.document_id` exists; ERD prose says `document`
- Celery `task_default_queue = "ai-rag-ingestion"`
- HTTP handlers: isolation 403, any `DomainError` 409, **no 404**
- `TenantId` / `UserId` VOs; no `Actor` type yet
- `compose.yaml` has no Garage service while the spine names Garage as compose seed

---

## Closures (spine still unchanged — suggested only)

Minimum set that actually kills the pairs:

1. **Tighten AD-6** — key template + one bytes port (P1).
2. **Tighten AD-4** — job JSON + queues; **new AD-11** lifecycle + cross-store delete/replace (P2, P3, P4, P9).
3. **Tighten AD-7** — collection name, vector, point id, payload *types*, required `text` (P5).
4. **Tighten AD-5** — one Embeddings port / same model for ingest+query; one retrieve return type; no second Qdrant adapter in chat (P6, P7). Move embed *sameness* out of Deferred.
5. **New AD-12** — SourceRef ≡ payload identity; chunker only at ingest (P8).
6. **Tighten AD-2 / AD-9 / AD-10** — VO vs UUID string; messages+table names; 404 vs 409 vs 401 (P10–P13).
7. **Fix the Capability map** so every slice that touches a store is listed under that store's ADs.

Without those, "obey the spine" is not enough to build the next two slices in parallel.
