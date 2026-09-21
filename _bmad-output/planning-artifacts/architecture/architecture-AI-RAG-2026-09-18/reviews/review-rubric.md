# Rubric walk — Architecture Spine (AI-RAG)

- **Spine:** `ARCHITECTURE-SPINE.md` (feature altitude, hexagonal, build-substrate, status: draft)
- **Walker:** good-spine checklist (`bmad-architecture` Reviewer Gate)
- **Date:** 2026-09-18
- **Mechanical lint:** `lint_spine.py` — 0 findings (placeholders, AD ids, Binds/Prevents/Rule, stack pins)
- **Spine not modified**

## Verdict

**Needs revision before epics.** The tenant/hexagon/worker/JWT/S3-port core is the right feature-altitude contract, and the operational envelope is named rather than silent. It is not yet a safe substrate: one Qdrant collection is unbound (name + embedding space), Deferred still hides a now-divergence, AD-10’s Rule does not uniquely map missing resources, and Structural Seed describes a Garage topology `compose.yaml` does not have.

## Checklist

| Check | Result |
| --- | --- |
| Fixes real divergence points for the level below (epics/slices); misses none | **Fail** — collection identity + shared embedding space unfixed; in-tenant document ACL unspoken |
| Every AD Rule is enforceable and prevents its stated divergence | **Fail** — AD-10 404/409 collision; AD-7 “one collection” with no name; AD-6 mixes Garage seed into the Rule; AD-3 overclaims vs existing async `GetReadiness` |
| Nothing under Deferred could let two units diverge *now* | **Fail** — “LLM/embedding model IDs” deferred while ingestion, retrieval, and chat must share one vector space |
| Named tech verified-current or honestly labeled as installed seed | **Pass with nits** — installed vs intended is stated in prose, not per row; a few intended-add pins trail current-stable |
| Ratifies rather than contradicts the brownfield FastAPI+React RAG codebase | **Fail** — Garage listed as current Compose topology; AD-3 “async at HTTP adapter only” contradicts `application/health/get_readiness.py` |
| No parent spine; no SPEC.md — capability map from AGENTS.md slice order is OK | **Pass** |
| Every owned dimension decided, deferred, or an open question — especially operational/environmental envelope | **Pass** — Compose is the named environment; k8s / managed Postgres / Amazon S3 topology / logging-tracing deferred to production-hardening. Remaining gaps are missing *items*, not a silent dimension |

---

## What holds

These ADs do the job a feature spine is for. Two later slices following them cannot invent a second architecture.

- **AD-1 + dependency diagram** — layers map to the real tree (`domain` / `application` / `infrastructure` / `bootstrap`, web `features` + `api`). Matches `AGENTS.md` and existing packages.
- **AD-2** — `Actor` as the isolation key is the non-obvious call. It blocks `contextvars`, loose `tenant_id` primitives, and client-supplied tenant as the only filter. Aligns with `assert_same_tenant` and `TenantIsolationError` already in domain.
- **AD-4** — worker is an adapter; HTTP and worker share use cases; jobs carry the enqueuing Actor, not a JWT. Matches `infrastructure/worker/celery_app.py` as an adapter stub and closes Celery-owned ingest vs HTTP drift.
- **AD-5** — extract/chunk/embed/upsert/retrieve/generate as ports; LangChain is not the engine. Correctly overrides the `docs/architecture.md` “RAG Engine” box without fighting the code (there is no engine).
- **AD-8** — this API issues Bearer JWTs from local `User` rows; web holds the token in memory. `jwt_secret` already exists on `Settings`. Prevents cookie vs bearer and Auth0 vs local splits across HTTP features.
- **AD-9** — shared schema, `tenant_id` column, SQLAlchemy 2.x + Alembic in infrastructure. RLS correctly deferred.
- Capability map uses AGENTS.md slice order (`identity-and-tenancy` → `production-hardening`). No `Inherited Invariants`. No fake parent. No `SPEC.md` required.

---

## Findings

### High

#### H1 — AD-7 does not bind collection identity or vector schema

- **Checklist:** divergence miss; Rule does not prevent the stated split
- **Location:** AD-7; Deferred “LLM/embedding model IDs”
- **Problem:** The Rule says “one shared collection” and lists payload fields, then stops. It does not name the collection, pin distance, or pin embedding dimensionality. Ingestion, retrieval, and chat are three slices that can each “ensure” a collection. Independently they will pick `chunks` vs `documents` vs `ai_rag`, Cosine vs Dot, 1536 vs 3072.
- **Deferred leak:** “LLM/embedding model IDs | Config, not architecture | first embed/generate adapter” treats generate and embed as the same postponement. Generate model *is* config. Embed model + dimension *are* the collection schema. The first embed adapter and the first retrieve adapter are different slices. Config-only is not enough unless the spine also says: one embedding model/dimension from env, used by ingest *and* query-embed, written into that one collection.
- **Code:** no Qdrant writes exist yet — this cannot be read off compliant code.
- **Disposition:** **autofix** the collection name + “ingestion ensures, others consume” + shared embed space; **discuss** only the actual name/distance if the team cares. Do not leave embed IDs solely under Deferred.

#### H2 — Structural Seed states Garage as current Compose topology

- **Checklist:** brownfield ratification
- **Location:** Structural Seed (Compose list + container diagram); AD-6 Rule last sentence
- **Problem:** Spine: “Local environment is Docker Compose: `postgres`, `redis`, `qdrant`, `garage`, `api`, `worker`, `web`.” Actual `compose.yaml` has postgres, redis, qdrant, api, worker, web — no Garage, no S3 env, api/worker do not depend on an object store. The S3 *port* + one-bucket + `tenant_id/document_id/...` keys belong in AD-6. Garage as the local image is seed *to add*, not seed that already exists.
- **Why it matters now:** documents and ingestion will either follow the spine (add Garage) or the repo (local disk / skip bytes). That is the exact split AD-6 claims to prevent.
- **Disposition:** **autofix** — label Garage as intended Compose add for the documents slice; keep the S3 adapter Rule; drop Garage from the AD Rule body.

#### H3 — AD-10 Rule does not uniquely map missing resources

- **Checklist:** Rule not enforceable / does not prevent its divergence
- **Location:** AD-10
- **Problem:** “HTTP maps `TenantIsolationError` → 403, other `DomainError` → 409, missing resource → 404.” Existing handlers (`error_handlers.py`) implement the first two only. There is no not-found type. If `DocumentNotFound` subclasses `DomainError`, “other DomainError → 409” wins and 404 never fires. Documents vs chat vs identity will split 404 vs 409 vs FastAPI default.
- **Disposition:** **autofix** — name a domain not-found type (or say missing is *not* a `DomainError`) and order the mapping: isolation 403, not-found 404, other `DomainError` 409. Envelope `{"detail": "<message>"}` can stay.

### Medium

#### M1 — In-tenant document visibility is neither decided nor deferred

- **Checklist:** divergence miss; dimension silent
- **Location:** Capability map (documents, retrieval, chat); Deferred “Roles on Actor”; `docs/domain.md` “permitted documents”
- **Problem:** Tenant isolation is bound. Who inside the tenant may see a document is not. Roles are deferred, which implies “tenant membership is enough” — but that default is not written. Chat, retrieval, and documents can invent owner-only vs all-members vs READY-only independently. READY-only for Q&A is implied by the status machine but not tied to retrieval.
- **Disposition:** **autofix** a one-line convention (all tenant members; retrieval only `READY`) or **defer** explicitly: “no in-tenant ACL until a slice needs it; until then all members see all tenant docs.”

#### M2 — AD-3 overclaims against the only existing use-case pair

- **Checklist:** brownfield; Rule vs stated exception
- **Location:** AD-3; `apps/api/src/app/application/health/get_readiness.py` (`async def execute`); `ReadinessProbe.check` is async in application
- **Problem:** Sync product `execute()` for Celery is the right invariant. The exception is written as “`/ready` probes may remain async at the HTTP adapter only.” In the repo, async lives in the application use case and its port, not only the router. Builders copy `GetReadiness`, not the spine footnote.
- **Disposition:** **autofix** — grandfather `GetReadiness` / probe ports as the allowed async exception; product use cases stay sync.

#### M3 — Citation shape is weakened relative to domain

- **Checklist:** ratification; slice divergence (retrieval vs chat)
- **Location:** Structural Seed ERD (“`Message` may carry `SourceRef`”); domain `SourceRef`; `docs/domain.md` “Answers include source and page references”
- **Problem:** `SourceRef` already exists (`document_id`, `filename`, `page`, `chunk_index`) and matches AD-7 payload. “May carry” lets chat invent a second DTO. Retrieval vs chat will drift on citation JSON.
- **Disposition:** **autofix** — answers use existing `SourceRef`; do not add a parallel citation type.

#### M4 — Job Actor payload shape unbound

- **Checklist:** AD-4 Prevents worker vs HTTP drift
- **Location:** AD-4 Rule “The job payload carries the enqueuing `Actor`”
- **Problem:** Two enqueue sites (documents HTTP vs evaluation vs reindex) can serialize `tenant_id`/`user_id` as nested object vs flat claims vs different key names. The worker “builds Actor from the job record” then disagrees with HTTP.
- **Disposition:** **autofix** — one job record shape, e.g. `tenant_id` + `user_id` strings mirroring JWT claims; not the JWT.

### Low

#### L1 — Stack table mixes installed pins and intended adds on equal rows

Section intro is honest (“Installed pins stay… Intended adds are current-stable, not yet in lockfiles”). The table is not. Installed (in `pyproject.toml` / `package.json` / `compose.yaml`): FastAPI 0.115.12, uvicorn 0.34.2, pydantic 2.11.7, pydantic-settings 2.8.1, Celery 5.4.0, redis 5.2.1, httpx 0.28.1, React 19.1.0, react-dom 19.1.0, react-router-dom 7.6.1, TypeScript 5.8.3, Vite 6.3.5, PostgreSQL 16-alpine, Redis 7.4-alpine, Qdrant v1.13.2. Not in lockfiles: SQLAlchemy 2.0.52, Alembic 1.19.2, qdrant-client 1.13.2, openai 3.13.0, boto3 1.43.79, PyJWT 2.13.0, Garage.

Re-checked 2026-09-18: FastAPI current 0.141.1 (correctly treated as seed, bump deferred). Qdrant current v1.19.1 / client 1.19.0 (correctly matched to compose v1.13.2). SQLAlchemy 2.0.52 is current 2.0 stable. Alembic 1.19.2 exists. PyJWT 2.13.0 is current. Garage `dxflrs/garage:v2.4.1` is current. Intended-add drift: openai 3.13.0 vs 3.16.0; boto3 1.43.79 vs 1.43.96. React 19.1.0 vs 19.2.x is installed seed — fine if the row says so.

**Disposition:** **autofix** a third column or suffix (`installed` / `intended add`); **defer** openai/boto3 point bumps (not invariants).

#### L2 — HTTP prefix `/api` is in the code, not in conventions

Health is `/api/health`, `/api/ready`; Vite proxies `/api`. Readable from the repo, so brownfield does not require restating it — but documents/chat can still mint `/v1/...`. One conventions row would close it.

**Disposition:** **autofix** or **ignore** (code is the seed).

#### L3 — AD-1 Prevents vs Rule are slightly misaligned

Prevents “per-feature mini-apps with incompatible tenant or vector contracts.” Rule is “domain type + port + use case + adapter; no empty folders; one slice at a time.” Mini-app/tenant drift is actually AD-2/5/7. Harmless if those stay; do not treat AD-1 as the tenant contract.

**Disposition:** **ignore** or tighten Prevents to layering only.

#### L4 — PDF-only is in docs/UI, not in the spine

`docs/domain.md` and `DocumentsPage` say PDF upload. Spine defers the extractor library but not accepted MIME/types. Documents vs ingestion can accept `docx` vs PDF-only.

**Disposition:** **defer** to the documents slice with that revisit named, or one conventions row “PDF only until a later slice.”

#### L5 — Session / unit-of-work unstated

AD-9 requires tenant filters on repositories, not request-scoped vs per-task `Session`. Identity vs documents vs worker can each invent a different UoW. Coexistence is possible; it is not a hard fork.

**Disposition:** **defer** to first SQL slice (identity) with “that slice’s session policy is the template.”

---

## Dimensions this altitude owns

| Dimension | State |
| --- | --- |
| Paradigm / layers / dependency direction | Decided (hexagonal, AD-1, diagram) |
| Isolation / authn | Decided (AD-2, AD-8, AD-9); roles deferred |
| Sync vs worker | Decided (AD-3, AD-4) |
| RAG engine / ports | Decided (AD-5); hybrid/rerank deferred |
| Blob storage | Decided (S3 port, one bucket, key prefix); Garage seed **mislabeled** |
| Vector store | Partial — payload + tenant filter decided; collection name / metric / dim **silent** |
| Persistence / IDs / errors / dates | Decided (conventions + AD-9, AD-10 with H3) |
| In-tenant ACL / “permitted documents” | **Silent** (M1) |
| Deployment & environments | Decided: Compose is the named environment |
| Infra / provider | Decided as S3-compatible + env credentials; cloud providers unnamed; Amazon S3 topology deferred |
| Operations | `/health` `/ready` exist; structured logging/tracing deferred to production-hardening |
| CI/CD, TLS, backups | Unstated; acceptable under production-hardening if not claimed as in-scope |

No open-questions section. Remaining holes are silent, not tagged. That is the failure mode for H1 and M1, not for the ops envelope as a whole.

---

## Suggested gate actions

| ID | Action |
| --- | --- |
| H1 | Add collection name + shared embed space to AD-7 (or a sibling AD). Tighten the Deferred row so only *generate* model IDs wait. |
| H2 | Describe Garage as an intended Compose service for documents, not as current topology. Pull Garage out of the AD-6 Rule. |
| H3 | Order AD-10: 403 / 404 / 409 with a named not-found type. |
| M1–M4 | Short convention or Rule lines; do not reopen coaching. |
| L1 | Label stack rows installed vs intended. |

Do not add ADs for RLS, OIDC, k8s, hybrid retrieval, or LangChain — those Deferred rows are correctly later.

## Compact summary (for parent)

Needs revision. Top findings: (1) AD-7 leaves collection name and embedding space unbound while deferring embed model IDs; (2) Garage is written as current Compose though `compose.yaml` has none; (3) AD-10 404 collides with DomainError→409; (4) in-tenant document ACL is silent while roles are deferred; (5) AD-3’s async exception does not match existing `GetReadiness`. File: `_bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/reviews/review-rubric.md`
