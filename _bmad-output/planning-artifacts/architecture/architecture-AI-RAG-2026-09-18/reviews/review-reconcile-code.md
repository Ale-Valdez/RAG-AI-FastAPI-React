# Reconcile-code review — Architecture Spine vs brownfield

- **Spine:** `_bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md`
- **Lens:** brownfield codebase (do not invent; ratify or contradict)
- **Date:** 2026-09-18
- **Spine not modified.**

## Verdict

**Mostly ratifies, with present-tense seed overclaims.**

The hexagonal layout, domain model, document status machine, HTTP error envelope, installed Python/React pins, and Compose services that *actually exist* match the spine. Several Structural Seed / Stack statements read as already true in the repo when they are **decided but not applied**. The load-bearing contradiction is Garage listed as a Compose service. Secondary: AD-3 quarantines async to the HTTP adapter, while `GetReadiness` is already an async application use case; `jwt_secret` is already on `Settings`; the web client has no auth.

This is a consistency contract for upcoming slices, not a snapshot of a finished product. The ADs are the right rules. The seed sections should not be readable as “this is what `compose.yaml` / `pyproject.toml` / `apps/web` already contain.”

---

## What the code actually is (scan)

| Area | Present |
| --- | --- |
| API layers | `domain/`, `application/health/`, `infrastructure/{http,health,config,worker}`, `bootstrap/` — no empty persistence/s3/qdrant/openai folders |
| Domain | `Tenant`/`TenantId`, `User`/`UserId`, `Document` + status machine, `Conversation`/`Message`/`SourceRef`, `DomainError`/`TenantIsolationError`/`InvalidDocumentTransition`, `assert_same_tenant` |
| **Not in domain** | `Actor`, ports (blob/extract/chunk/embed/upsert/retrieve/generate), JWT types |
| Application | `GetHealth` (sync `execute`), `GetReadiness` (async `execute` + `ReadinessProbe` Protocol) |
| HTTP | `/api/health` sync `def`; `/api/ready` `async def`; `TenantIsolationError` → 403, `DomainError` → 409, `{"detail": ...}`; **no 404 handler**, **no auth adapter** |
| Settings | `app_name`, CORS, `database_url`, `redis_url`, `qdrant_url`, `openai_api_key`, **`jwt_secret` (default `"change-me"`)** |
| Worker | Celery app in `infrastructure/worker/celery_app.py`; broker/backend Redis; default queue `ai-rag-ingestion`; **does not share `create_app` composition root** |
| Compose | `postgres`, `redis`, `qdrant`, `api`, `worker`, `web` — **no `garage`**, no S3 env |
| pyproject | FastAPI 0.115.12, uvicorn 0.34.2, pydantic 2.11.7, pydantic-settings 2.8.1, redis 5.2.1, httpx 0.28.1, celery 5.4.0. **No** SQLAlchemy, Alembic, qdrant-client, openai, boto3, PyJWT |
| Web | React 19.1.0, RRD 7.6.1, Vite 6.3.5, TS 5.8.3. Routes: Health / Documents / Chat. `api/client.ts` `fetch` with **no `Authorization`**. Documents and Chat are empty states. |

---

## Findings

### 1. CRITICAL — Garage presented as already in Compose

**Spine:** Structural Seed mermaid includes `garage[(Garage S3)]`; prose: “Local environment is Docker Compose: `postgres`, `redis`, `qdrant`, `garage`, `api`, `worker`, `web`.” Stack table pins `dxflrs/garage:v2.4.1`. AD-6: “Compose seed is Garage.”

**Code (`compose.yaml`):** services are `postgres`, `redis`, `qdrant`, `api`, `worker`, `web` only. No Garage image, volume, port, healthcheck, or S3 endpoint/credential env on `api`/`worker`. README still lists those six services. `Settings` has no S3 fields.

**Judgment:** AD-6 as a *forward* invariant (S3 API, one bucket, `tenant_id/document_id/...` keys, Garage as the *intended* local seed) is fine and does not contradict code — there is no MinIO/Garage client in domain. The **Structural Seed is supposed to be true at cold-start**. Naming `garage` as a current Compose service is false. Memlog records the Garage decision; the seed has not been applied.

**Action:** Treat as seed-not-yet-applied. Distill should say Compose *will* add Garage (or “intended seed”), not list it beside postgres/redis/qdrant as if `compose.yaml` already has it. Do not leave a builder thinking `docker compose up` starts S3.

### 2. HIGH — Mixed sync `GetHealth` vs async `GetReadiness` vs AD-3

**Spine AD-3:** Product `execute()` and ports are sync. FastAPI product routes are `def`. SQLAlchemy sync `Session`. “`/ready` probes may remain async at the HTTP adapter only — they are not the template for product use cases.”

**Code:**

| Piece | Sync? |
| --- | --- |
| `GetHealth.execute()` | sync |
| `health()` route | `def` |
| `GetReadiness.execute()` | **async** |
| `ReadinessProbe.check()` | **async** Protocol in `application/health/get_readiness.py` |
| `ready()` route | `async def` |
| Probe adapters (`PostgresProbe`, `RedisProbe`, `QdrantProbe`) | async |

AD-3 correctly protects Celery-callable product use cases. It does **not** describe the brownfield: async already lives in an **application** use case and an **application** port, not “HTTP adapter only.” Tests lock this in (`async def test_get_readiness_use_case`).

**Risk:** A later slice copies `GetReadiness` (`async def execute`, Protocol next to the use case) as the house style and fights AD-3.

**Action:** Name the exception in the spine: existing `GetReadiness` / probes stay async; they are not the product template. Do not imply all application `execute()` methods in this repo are already sync.

### 3. HIGH — Web has no auth; AD-8 reads as current client behavior

**Spine AD-8:** “Web sends `Authorization: Bearer` and keeps the token in memory, not `localStorage`.” Conventions table: “Auth | Bearer JWT; token in memory (AD-8).” Capability map places identity-and-tenancy in “HTTP auth adapter + SQL User/Tenant.”

**Code:**

- `apps/web/src/api/client.ts` — `fetch(`${baseUrl}${path}`)` with no headers, no token argument, no in-memory store.
- No login/register feature folder; App nav is Health / Documents / Chat only.
- Documents and Chat pages are empty states (do not invent APIs) — that part ratifies AD-10 / Web convention.
- CORS `allow_credentials=True` with no cookie auth in the client.

AD-8 is the right *contract* for identity-and-tenancy and every later HTTP feature. It is **not** what the web already does. Identity is slice 1 and unimplemented (no JWT issue/verify routes, no PyJWT dependency).

**Action:** Keep the rule. Do not phrase it as present web behavior. Identity slice must add Bearer on the shared client; documents/chat must not grow a second auth scheme.

### 4. MEDIUM — `jwt_secret` already in settings (not a future add)

**Spine AD-8:** “signed with `jwt_secret` from env.” Stack lists PyJWT 2.13.0 as if with other seed pins. Config convention: environment only.

**Code (`infrastructure/config/settings.py`):**

```python
jwt_secret: str = "change-me"
openai_api_key: str = ""
```

`load_settings()` already reads env / `.env`. Compose does not set `JWT_SECRET`; the committed default is `"change-me"`. **PyJWT is not in `pyproject.toml`.** No issuer, no verifier, no HTTP auth adapter.

**Action:** Ratify the existing settings field as the secret hook. Identity should not add a second config name. Flag the default `"change-me"` as a placeholder, not a production secret. PyJWT is an intended add, not an installed pin.

### 5. MEDIUM — Stack table mixes installed pins with intended adds

**Spine:** “Seed at authoring (2026-09-18). Installed pins stay until a slice changes them. Intended adds are current-stable, not yet in lockfiles.” Then one table lists both.

**Matches lockfiles / Compose (ratified):**

| Name | Where |
| --- | --- |
| Python >=3.12 | `pyproject.toml` |
| FastAPI 0.115.12, uvicorn 0.34.2, pydantic 2.11.7, pydantic-settings 2.8.1 | `pyproject.toml` |
| Celery 5.4.0, redis 5.2.1, httpx 0.28.1 | `pyproject.toml` |
| React / react-dom 19.1.0, react-router-dom 7.6.1, TypeScript 5.8.3, Vite 6.3.5 | `apps/web/package.json` |
| PostgreSQL 16-alpine, Redis 7.4-alpine, Qdrant v1.13.2 | `compose.yaml` |

**Not in lockfiles / Compose (intended, presented in the same table):** SQLAlchemy 2.0.52, Alembic 1.19.2, qdrant-client 1.13.2, openai 3.13.0, boto3 1.43.79, PyJWT 2.13.0, Garage `dxflrs/garage:v2.4.1`.

Memlog already splits “installed seed” vs “intended adds.” The distilled table does not.

**Action:** Split the table or mark intended rows. Otherwise identity/documents slices will assume those packages are already pinned.

### 6. MEDIUM — `Actor` is adopted, not present in domain

**Spine AD-2:** “Domain defines `Actor` (`tenant_id` + `user_id`).”

**Code:** `User` has `id` + `tenant_id` + `email`. `assert_same_tenant(resource_tenant, actor_tenant)` takes `TenantId`, not an Actor type. **No `Actor` class** anywhere under `apps/`. No tenant-touching product use case yet (health is global).

Not a runtime contradiction — there is nothing for Actor to bind yet. A builder reading AD-2 as “open `domain/identity.py` and use `Actor`” will not find it.

**Action:** Keep the AD (this is exactly the divergence identity must close). Phrase as the type to add in identity-and-tenancy, not as an existing VO.

### 7. LOW — Ports live in application for readiness; domain has none

**Spine:** “Ports are protocols in `domain`.” AD-5 lists extract/chunk/embed/upsert/retrieve/generate as domain ports. Structural seed comments `infrastructure/` with persistence, s3, qdrant, openai.

**Code:** The only Protocol is `ReadinessProbe` in application. Domain files are flat modules (`documents.py`, `chat.py`, …), not `domain/documents/` packages. Infrastructure has http/health/config/worker only. **Correct per AGENTS.md** (“Do not add empty layer folders”).

**Action:** Target layout comments are OK if read as future. Do not add empty folders to “match” the spine comment. Product ports belong in domain when those slices land; do not treat `ReadinessProbe` as the port template (see finding 2).

### 8. LOW — AD-4 composition root not shared yet; AD-10 404 not wired

**AD-4:** “HTTP and the worker share the composition root.” Worker `celery_app.py` only constructs Celery from `load_settings()`. `create_app()` is HTTP-only. Acceptable until ingestion exists; do not read as already wired.

**AD-10:** “missing resource → 404.” `error_handlers.py` maps 403 and 409 only. No `NotFound` / missing-resource type. Envelope `{"detail": "<message>"}` **does** match. Web `ApiError` uses status codes; HealthPage handles loading/error. 404 is a rule for later HTTP adapters, not current code.

**Worker diagram:** spine shows worker → qdrant/garage/openai. Compose `worker` depends on redis + postgres only (not qdrant). True today; ingestion will need those links.

---

## AD-by-AD vs code

| AD | Ratify / contradict / not-yet |
| --- | --- |
| AD-1 Hexagonal layers | **Ratifies.** Directories and import direction match. Domain has no FastAPI/SQLAlchemy/Celery/Qdrant/LangChain. |
| AD-2 Actor | **Not-yet.** Isolation helper exists; `Actor` type does not. |
| AD-3 Sync use cases | **Mixed.** `GetHealth` ratifies; `GetReadiness` contradicts “adapter only.” |
| AD-4 Worker is adapter | **Ratifies direction.** Celery is in infrastructure; worker does not yet call use cases or share bootstrap. |
| AD-5 Thin RAG adapters | **Not-yet / consistent.** No LangChain; no qdrant-client/openai yet. |
| AD-6 Bytes behind S3 | **Decision not applied.** No blob port, no boto3, **no Garage in Compose** (finding 1). |
| AD-7 One Qdrant collection | **Docs + SourceRef ratify shape.** No collection/upsert/search yet. `/ready` only TCP/HTTP probes Qdrant. |
| AD-8 Bearer JWT | **Config hook ratifies (`jwt_secret`).** Issue/verify/web Bearer **not implemented** (findings 3–4). |
| AD-9 Shared schema | **Not-yet.** No SQLAlchemy/Alembic/models. Domain entities already carry `tenant_id`. |
| AD-10 Domain errors at HTTP | **Partially ratifies.** 403/409 + `detail` exist; 404 does not. Web does not invent extra error semantics. |

---

## Capability map vs slices in tree

| Spine area | Code |
| --- | --- |
| identity-and-tenancy | Domain `User`/`Tenant` only. No HTTP auth, no SQL. |
| documents | Domain `Document` + tests + empty React page. No blob/SQL/upload. |
| ingestion | Celery process exists; no tasks/use cases. |
| retrieval / chat / rag / eval | Domain chat types + empty Chat page; no generate/retrieve. |
| production-hardening | Deferred in spine **and** absent in code. `/health` + `/ready` exist (spine says so). |

Capability map is honest that later areas are future. Identity row slightly overstates “HTTP auth adapter + SQL User/Tenant” as where it “lives” today.

---

## What the spine ratifies well (do not churn)

- Paradigm and folder mapping vs `AGENTS.md` and the tree.
- Dependency rule; web talks HTTP only (`features/health/api.ts` → `api/client.ts`).
- Document lifecycle PENDING → PROCESSING → READY \| FAILED (`domain/documents.py` + tests).
- `SourceRef` fields vs AD-7 payload (minus `tenant_id`, which sits on `Document`/`Conversation`).
- Chunk as Qdrant point, not a Postgres table (no chunk table exists).
- ER shape Tenant–User–Conversation–Message / Tenant–Document.
- Installed FastAPI/Celery/React/Compose image pins.
- Use-case tests with in-memory fakes; no Docker required for domain tests.
- Deferred: RLS, OIDC, roles on Actor, LangChain-as-engine, hybrid/rerank, k8s.

---

## Suggested distill tweaks (spine unchanged this pass)

1. Structural Seed: Compose services that exist vs Garage as **intended, not in `compose.yaml` yet**.
2. AD-3: explicit exception — `GetReadiness` + probe Protocol are async in application; product use cases stay sync.
3. AD-8 / Stack: `jwt_secret` already on `Settings`; PyJWT not installed; web has no Bearer yet.
4. Split Stack “installed” vs “intended adds.”
5. AD-2: `Actor` is the type identity will add; `assert_same_tenant` already exists.

---

## Gate actions

| Finding | Action |
| --- | --- |
| 1 Garage as current Compose service | **Autofix** on distill (present vs intended). |
| 2 Async `GetReadiness` vs AD-3 | **Autofix** — name the brownfield exception. |
| 3 Web has no auth | **Autofix** phrasing; keep AD-8 as contract. |
| 4 `jwt_secret` already in settings | **Autofix** — ratify the field. |
| 5 Mixed stack table | **Autofix** — split installed / intended. |
| 6 Actor type missing | **Discuss / phrasing** — keep AD, don’t claim the VO exists. |
| 7–8 Ports / worker / 404 | **Defer** to the slices that add them; optional one-liners. |
