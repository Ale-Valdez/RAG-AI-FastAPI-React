# Input reconciliation — architecture spine vs load-bearing docs

- **Spine:** `_bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md`
- **Inputs:** `AGENTS.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/domain.md`, `docs/rag.md`
- **Date:** 2026-09-18
- **Stance:** Do not change the spine. Report what in the inputs did not land, landed weaker, or is implied-contradicted.
- **Verdict:** `gaps`

No input *requires* a behavior the spine forbids. Several load-bearing constraints are listed, ordered, or softened rather than stated as enforceable rules. One source (`AGENTS.md`) still frames LangChain as a peer of in-use infrastructure frameworks while AD-5 rejects it as the engine.

---

## Method

Walked each input requirement, constraint, and tone against the spine (paradigm, ADs, dependency rule, conventions table, capability map, Deferred). A item **lands** when a later slice reading only the spine would be forced into the same call. Order-in-a-table, a “may”, or a capability-map row is not enough when the input states a rule.

---

## What landed

| Input constraint | Where it lives in the spine |
| --- | --- |
| Hexagonal ports-and-adapters; layout `domain` / `application` / `infrastructure` / `bootstrap`; web `features` + `api` | Design Paradigm, Structural Seed |
| Domain independent of FastAPI, SQLAlchemy, Celery, Qdrant; application does not take those either | Dependency rule; AD-1 |
| Use cases never take Request/Response; HTTP maps domain errors | AD-2, AD-10 |
| `tenant_id` from authenticated context, never an untrusted client field as the only filter | AD-2, AD-8 (JWT claims → Actor), AD-4 (job carries enqueuing Actor) |
| Retrieval always filtered by tenant; cross-tenant retrieval prohibited | AD-7 |
| Qdrant payload: `tenant_id`, `document_id`, `filename`, `page`, `chunk_index` | AD-7 |
| Page-aware chunks | Consistency Conventions → Chunks |
| Document lifecycle PENDING → PROCESSING → READY \| FAILED | Consistency Conventions → Documents |
| Tenant→User→Conversation→Message; Tenant→Document | Structural Seed erDiagram |
| Conversations persist | erDiagram + AD-9 binds chat persistence |
| Async document processing via worker sharing use cases | AD-3, AD-4 |
| Redis/Celery, Postgres, Qdrant, OpenAI, React | Stack + Structural Seed |
| One vertical slice at a time; no empty layer folders | AD-1 Rule |
| Tests with each use case; in-memory fakes; no Docker | Consistency Conventions → Tests |
| Config from env; never commit secrets | Consistency Conventions → Config |
| Do not invent backend behavior; loading / empty / error states | Dependency rule, AD-10, Web row |
| Later RAG: hybrid, rerank, query rewrite | Deferred → rag-engineering |
| Composition root in bootstrap | Paradigm table, mermaid |

Substance of tenant isolation, hexagonal layering, document status machine, and RAG payload **did** land. The gaps below are sequencing, product constraints, and tone that a slice agent can still miss.

---

## Findings

### G1 — Slice order is catalogued, not binding

- **Severity:** high
- **Sources:** `AGENTS.md` “Slice order”; spine `binds`, Capability → Architecture Map
- **Input:** implement `identity-and-tenancy → documents → ingestion → retrieval → chat → rag-engineering → evaluation → production-hardening`.
- **Spine:** the same names appear, in that order, as `binds` and map rows. AD-1 says “one vertical slice at a time” but not *which* slice. Nothing says the sequence is a prerequisite chain.
- **Miss:** a later agent can start at chat or rag-engineering without identity, documents, or retrieval. The order is a quiet process invariant, not an AD or convention rule.
- **Fix (later, not this pass):** one convention row or a one-line rule under AD-1 / Capability map: “Slice sequence in `binds` is the implementation order; do not skip ahead.”

### G2 — Answers *must* cite sources; spine says Message *may* carry SourceRef

- **Severity:** high
- **Sources:** `docs/domain.md` (“Answers include source and page references”); `docs/rag.md` (`answer + sources`); spine Structural Seed (“`Message` may carry `SourceRef`”)
- **Input:** citations are part of the product, not optional metadata.
- **Spine:** `may` lets the chat slice ship answers with no `SourceRef`. Capability map for chat lists generate + HTTP/web, not a citation invariant.
- **Miss:** chat vs retrieval can disagree on whether sources are required, and on which fields (domain: source + page; rag/spine SourceRef: document, filename, page, chunk_index).
- **Fix (later):** “Answers include `SourceRef` (document, filename, page, chunk_index)” — required on assistant messages, not optional.

### G3 — PDF is the document type in the inputs; spine never binds format

- **Severity:** medium
- **Sources:** `docs/domain.md` (“Tenant users upload PDFs”); `docs/rag.md` (`PDF -> extraction`); spine AD-5/AD-6 and Deferred “PDF extractor library”
- **Input:** the corpus is PDFs. The pipeline starts at PDF.
- **Spine:** blob port + extract port; extractor *library* is deferred. MIME/type is unset. Documents vs ingestion can accept DOCX/HTML/markdown independently.
- **Miss:** first documents slice can invent a generic blob API that ingestion then cannot extract.
- **Fix (later):** convention or AD-6/AD-5 note: first slices accept PDF only; other formats are a later AD.

### G4 — AGENTS.md still lists LangChain as a peer infra framework; AD-5 rejects it as engine

- **Severity:** medium (source drift / implication; not a logical forbid/require clash)
- **Sources:** `AGENTS.md` rule 2; `docs/architecture.md` (no LangChain; draws a “RAG Engine” box); spine dependency rule, AD-5, Deferred “LangChain”
- **Input:** LangChain sits in the same forbid-in-domain list as FastAPI, SQLAlchemy, Celery, Qdrant — frameworks that *are* used in infrastructure. That tone allows LangChain in adapters. `architecture.md`’s “RAG Engine” box is unnamed tech, compatible with either a fat engine or thin ports.
- **Spine:** AD-5: extract/chunk/embed/upsert/retrieve/generate are domain ports; infra is `qdrant-client` + official `openai` SDK + owned extract/chunk. “LangChain is not the engine and is not imported from domain or application.” Deferred: only a later AD may change that.
- **Not a contradiction:** AGENTS.md never requires using LangChain. Domain-not-importing-LangChain *did* land (dependency rule + AD-5).
- **Miss:** an agent that obeys AGENTS.md and only skims AD-5 can still put LCEL in `infrastructure`. The architecture diagram’s “RAG Engine” label also pulls toward a single engine object, which AD-5 exists to prevent.
- **Fix (later, source-side at finalize):** tighten AGENTS.md rule 2 to match AD-5 (LangChain is not the engine; still forbidden in domain/application). Optionally relabel the architecture.md box to the port list so it does not revive a fat `RagEngine`.

### G5 — “Tenant isolation is a security boundary” landed as filters, not as that frame

- **Severity:** medium
- **Sources:** `AGENTS.md` rule 1; `docs/architecture.md` opening; spine AD-2, AD-7, AD-9
- **Input:** isolation is a **security boundary**, not a query convenience. `tenant_id` comes from authenticated context.
- **Spine:** Actor + `assert_same_tenant` + Qdrant filter + SQL column + S3 key prefix. The words “security boundary” never appear. AD-2’s title is “Actor is the isolation key.”
- **Landed:** the mechanism. Untrusted-client-field-as-only-filter is prevented.
- **Miss:** a slice can treat `actor.tenant_id` as a default search hint and add an optional client `tenant_id` “for admin.” The input’s tone forbids that class of design; the spine’s tone is quieter.
- **Fix (later):** one clause in AD-2 Rule: “Tenant isolation is a security boundary.” Keep the Actor mechanics.

### G6 — Chat is not bound to AD-7 even though chat is where retrieval is used

- **Severity:** medium
- **Sources:** `docs/architecture.md` (“Retrieval must always filter by `tenant_id`…”); `docs/rag.md` (filtered retrieval; cross-tenant prohibited); spine Capability map
- **Spine:** retrieval → AD-5, AD-7. chat → AD-2, AD-5, AD-8, AD-10. Chat is the “users ask questions over permitted documents” slice and will call retrieve/generate.
- **Miss:** a chat implementer can embed search in the generate adapter and skip the Qdrant filter, while still claiming to follow the chat row.
- **Fix (later):** add AD-7 (and AD-4 if chat enqueue ever appears) to chat’s “Governed by.”

### G7 — RAG pipeline step “context assembly” has no port and no owner

- **Severity:** medium
- **Sources:** `docs/rag.md` (`filtered retrieval -> context assembly -> LLM -> answer + sources`); spine AD-5 port list
- **Spine:** extract, chunk, embed, upsert, retrieve, generate. Assembly is unnamed. Chat vs retrieval vs generate adapter can each concatenate context differently (token budget, citation packing, drop-low-score chunks).
- **Fix (later):** name assembly as an application-use-case step (not necessarily a new port) in AD-5 or the chat/retrieval map row.

### G8 — Quiet conventions.md rules that never appear

- **Severity:** low
- **Sources:** `docs/conventions.md`
- **Did not land:**
  - Validate external inputs at boundaries (vs env-only config, which did land).
  - Python type hints required.
  - TypeScript strict mode (stack names TypeScript 5.8.3, not `strict`).
  - Tone: “Prefer explicit, maintainable designs. Keep responsibilities separated.” — operationalized by hexagonal AD-1, not restated.
- **Risk:** HTTP-layer vs domain-VO validation split; untyped Python modules; `strict: false` in the web app. Unlikely to fork tenant/vector contracts, but they are standing project rules.
- **Fix (later):** two convention rows (validation at adapters; Python types + TS `strict`) if the spine is meant to replace reading `docs/conventions.md`.

### G9 — “Permitted documents” and “context evaluation” are underspecified, not contradicted

- **Severity:** low
- **Sources:** `docs/domain.md` (“questions over permitted documents”); `docs/rag.md` later stage “context evaluation”
- **Permitted:** most naturally means tenant membership (AD-2/AD-7). It could also mean a user-selected document subset or per-document ACL. The spine only guarantees tenant filter. Two chat slices could add or skip `document_id in …` filters.
- **Context evaluation:** Deferred lists hybrid / rerank / query rewrite for rag-engineering; `evaluation` is a separate bind under AD-4. The later-stage name from rag.md is not in the Deferred row. Low risk if evaluation owns that work.
- **Fix (later):** one sentence that “permitted” = tenant scope until a slice adds an allow-list; add “context evaluation” to Deferred or to the evaluation map row.

---

## Per-source notes

### AGENTS.md

| Item | Result |
| --- | --- |
| Tenant isolation / authenticated context | Lands in AD-2/AD-8/AD-4; “security boundary” wording does not (G5) |
| Domain independent of FastAPI, SQLAlchemy, Celery, Qdrant, LangChain | Lands as import ban; LangChain-as-engine rejected extra (G4) |
| Use cases / HTTP error mapping | Lands (AD-2, AD-10) |
| React must not invent backend behavior; loading/empty/error | Lands |
| Secrets / env config | Lands |
| Tests + in-memory fakes, no Docker | Lands (spine also names application tests) |
| One slice at a time; no empty folders | Lands (AD-1) |
| Directory layout | Lands |
| Slice **order** | Names listed; sequence not a rule (G1) |
| Blueprint `ai-rag-fastapi-react` 1.0 | In `sources:` frontmatter only; not in the body. Acceptable for a build-substrate. |
| Product line “grounded in organization documents” | Not restated. Low; `docs/architecture.md` “knowledge assistant” is enough. |

Infrastructure blurb in AGENTS.md (“HTTP, persistence, queues, vector store”) is expanded in the spine (S3, OpenAI, worker, config). Compatible.

### docs/architecture.md

| Item | Result |
| --- | --- |
| Multi-tenant knowledge assistant; isolation is a security boundary | Mechanism yes; phrase no (G5) |
| Hexagonal; composition root | Lands |
| Domain **and application** do not import FastAPI/SQLAlchemy/Celery/Qdrant | Lands; spine is stricter (`application` imports `domain` only). LangChain omitted here — consistent with AD-5 more than AGENTS.md is. |
| Retrieval always filtered by authenticated `tenant_id` | Lands in AD-7; not bound onto chat (G6) |
| Diagram “RAG Engine” | Spine decomposes it (AD-5). Compatible if Engine = use-case orchestration; harmful if read as a fat LCEL object (G4). |

### docs/conventions.md

Layering, tests-with-features, feature folders, API vs UI, loading/empty/error, env config, no secrets: landed. Validation-at-boundaries, Python type hints, TS strict: not landed (G8). Explicit/maintainable tone: carried by the paradigm, not quoted.

### docs/domain.md

Graph, lifecycle, authenticate-and-belong, async processing, persist conversations: landed. PDF uploads: not bound (G3). Required source+page on answers: softened to `may` (G2). “Permitted documents”: tenant-only (G9).

### docs/rag.md

Payload fields, page-aware chunks, cross-tenant prohibition, later hybrid/rerank/rewrite: landed. Full pipeline including **context assembly** and required **answer + sources**: assembly unnamed (G7), sources optional (G2). PDF as the start of the pipeline: not bound (G3). Context evaluation: only loosely via the evaluation bind (G9).

---

## Conflicts

None that reverse a stated requirement.

Closest approaches (classified as gaps, not `conflict`):

1. **SourceRef `may` vs answers *include* sources** — weakening, not an opposite rule.
2. **LangChain in AGENTS.md forbid-list vs AD-5 “not the engine”** — spine is a strict subset of the import ban; it does not violate AGENTS.md. It *does* outrun the implication that LangChain belongs in infrastructure like FastAPI. Update the source at finalize; do not relax AD-5.

---

## Recommendations for the parent (do not edit the spine in this pass)

1. Keep AD-5. Offer to align `AGENTS.md` (and the “RAG Engine” box in `docs/architecture.md`) so agents do not reintroduce LangChain in adapters.
2. When the spine is next distilled: bind slice sequence; require `SourceRef` on answers; PDF-only for first document slices; put AD-7 on chat; say isolation is a security boundary; name context assembly as a use-case step.
3. Optional convention rows: validate at boundaries; Python type hints; TypeScript `strict`.

---

## Verdict

`gaps` — tenant isolation, hexagonal layout, payload shape, and lifecycle are in the spine; slice order, required citations, PDF-only corpus, LangChain source-framing, and several quiet conventions.md rules are not fully enforceable from the spine alone.
