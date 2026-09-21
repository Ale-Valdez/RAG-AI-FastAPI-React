# Version / reality check — ARCHITECTURE-SPINE.md

- **Lens:** versions / live-stack reality (not adversarial, not editorial)
- **Content:** `_bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md`
- **Lockfiles checked:** `apps/api/pyproject.toml`, `apps/web/package.json`, `compose.yaml`
- **Checked:** 2026-09-18
- **Spine not modified.**

## Verdict

**Does not hold as a fully reality-checked current-stable stack.**

Installed Python/JS pins in the Stack table match the lockfiles. Several authoring claims about *current* upstream versions are true (FastAPI 0.141.1, Qdrant v1.19.1, Garage `v2.4.1`, MinIO CE archived, `qdrant-client==1.13.2` exists). The spine still overstates “current-stable” for intended adds, and one committed environment decision is false in the repo: **Garage is named as the Compose seed and is not in `compose.yaml`.**

## Authoring checks — confirm or refute

These were the known authoring claims. Rechecked against PyPI, GitHub, Docker Hub, and npm on 2026-09-18.

| Claim | Result | Evidence |
| --- | --- | --- |
| FastAPI current ~0.141.1 vs repo 0.115.12 | **Confirm** | PyPI `fastapi` 0.141.1 (2026-07-29); GitHub `fastapi/fastapi` tag `0.141.1`. Repo: `fastapi==0.115.12`. |
| Qdrant current ~v1.19.1 vs compose v1.13.2 | **Confirm** | Docker Hub `qdrant/qdrant:v1.19.1`; Helm chart 1.19.1 dated 2026-09-04. Compose: `qdrant/qdrant:v1.13.2` (tag still exists; GitHub server release 2025-01-28). |
| SQLAlchemy 2.0.52 | **Refute as current.** Version **exists**; it is **not** latest 2.0. | GitHub `rel_2_0_52` 2026-08-11. PyPI / GitHub latest 2.0 patch is **2.0.54** (2026-09-15). 2.1 remains prerelease (`2.1.0rc1` / `2.1.0b3`). Official download page still lists 2.0.51 — that site is stale, not a reason to keep 2.0.52. |
| Garage `dxflrs/garage:v2.4.1` | **Confirm** | Deuxfleurs release 2026-09-08; Docker Hub tag `dxflrs/garage:v2.4.1` (multi-arch). Current stable as of this check. |
| MinIO CE source-only / archived | **Confirm** (archive date was slightly sloppy in memlog) | `minio/minio` README: source-only, no community binaries. Repo archived; GitHub tree note **2026-02-13**; Docker blog same date; one third-party post says 2026-04-25. Substance is correct. Last official Docker Hub CE image frozen ~`RELEASE.2025-09-07`. |
| openai ~3.13.0 | **Exists; not current** | 3.13.0 released 2026-09-10. PyPI / changelog latest **3.14.0** (2026-09-14). |
| boto3 ~1.43.79 | **Exists; not current** | 1.43.79 exists (Sonatype: 2026-08-24). PyPI latest **1.43.98**. |
| PyJWT ~2.13.0 | **Exists; not current** | 2.13.0 exists (2026-05-21, security release). PyPI JSON latest **2.14.0** (Snyk: 2026-09-11). |
| Alembic ~1.19.2 | **Exists; not current** | 1.19.2 exists on PyPI. PyPI latest **1.20.0**. Docs site still titles 1.19.1 — stale, same class of error as SQLAlchemy.org. |
| qdrant-client 1.13.2 exists and matches server pin | **Confirm existence + match policy; patch is not latest 1.13** | PyPI 1.13.2 exists (2025-01-22). Qdrant docs: SDK major.minor should match server. Compose server is v1.13.2, so a 1.13.x client is the right *line*. Latest 1.13 client patch is **1.13.3** (2025-03-05). Current client overall is **1.19.1**. Authoring correctly avoided client 1.19 against server 1.13. |

## Lockfile vs spine Stack table

Spine text: “Seed at authoring (2026-09-18). Installed pins stay until a slice changes them. Intended adds are current-stable, not yet in lockfiles.”

The table does **not** mark which rows are installed vs intended. That makes the “current-stable” claim look like a lockfile.

### Present in lockfiles — match

| Spine | Lockfile | Match |
| --- | --- | --- |
| Python >=3.12 | `requires-python = ">=3.12"` | Yes. Current CPython feature series is 3.14.7; 3.12 is security-only until 2028-10. Floor is valid, not “current Python”. |
| FastAPI 0.115.12 | `fastapi==0.115.12` | Yes |
| uvicorn 0.34.2 | `uvicorn[standard]==0.34.2` | Yes |
| pydantic 2.11.7 | `pydantic==2.11.7` | Yes |
| pydantic-settings 2.8.1 | `pydantic-settings==2.8.1` | Yes |
| Celery 5.4.0 | `celery==5.4.0` | Yes |
| redis (Python) 5.2.1 | `redis==5.2.1` | Yes |
| httpx 0.28.1 | `httpx==0.28.1` | Yes — and PyPI latest is still **0.28.1** |
| React / react-dom 19.1.0 | `package.json` 19.1.0 | Yes |
| react-router-dom 7.6.1 | 7.6.1 | Yes |
| TypeScript 5.8.3 | 5.8.3 | Yes |
| Vite 6.3.5 | 6.3.5 | Yes |
| PostgreSQL 16-alpine | `postgres:16-alpine` | Yes |
| Redis 7.4-alpine | `redis:7.4-alpine` | Yes |
| Qdrant v1.13.2 | `qdrant/qdrant:v1.13.2` | Yes |

Web lockfile extras **not** in the Stack table (not a lie, just omitted): `@types/react` 19.1.4, `@types/react-dom` 19.1.5, `@vitejs/plugin-react` 4.5.2. API extras omitted: `pytest==8.3.5`, `pytest-asyncio==0.25.3`.

### Named in spine, **absent** from lockfiles (intended adds)

| Spine | In `pyproject.toml` / `compose.yaml`? |
| --- | --- |
| SQLAlchemy 2.0.52 | No |
| Alembic 1.19.2 | No |
| qdrant-client 1.13.2 | No |
| openai 3.13.0 | No |
| boto3 1.43.79 | No |
| PyJWT 2.13.0 | No |
| Garage `dxflrs/garage:v2.4.1` | **No compose service, no volume, no env** |

Also missing from both spine and lockfiles, but required the moment SQLAlchemy talks to Postgres: a DBAPI driver (`psycopg` / `psycopg2`). SQLAlchemy 2 extras document `postgresql-psycopg` (`psycopg>=3.0.7`). Unnamed intended add.

## Findings

### 1. Garage is a committed Compose seed and is not in Compose

- **Location:** Stack; Structural Seed (“Local environment is Docker Compose: `postgres`, `redis`, `qdrant`, `garage`, …”); AD-6
- **Trigger:** Spine binds local object storage to `dxflrs/garage:v2.4.1`. `compose.yaml` has `postgres`, `redis`, `qdrant`, `api`, `worker`, `web` only. README still lists those six. No Garage image, ports, or S3 env.
- **Guard:** Treat Garage as an *intended* compose add, or add the service before slices that need bytes. Do not describe it as the live seed until `compose.yaml` matches.
- **Consequence:** Documents/ingestion implementers will look for a Garage endpoint that does not exist. AD-6’s S3-port idea still fits; the named environment does not.

Garage **as a product** still fits: Deuxfleurs documents S3 signature v4, path-style URLs, and boto3. AD-6’s “endpoint, region, path-style, credentials from env” matches current Garage client guidance. The miss is repo reality, not technology fit.

Older Garage cookbook text still says DNS-style buckets are unsupported; the current compatibility matrix marks vhost-style implemented. Path-style remains the safe default the spine already chose.

### 2. “Intended adds are current-stable” is already false on the authoring day

Checked 2026-09-18 against PyPI:

| Spine pin | Live latest | Drift |
| --- | --- | --- |
| SQLAlchemy 2.0.52 | **2.0.54** (2026-09-15) | 3 days; still 2.0.x |
| Alembic 1.19.2 | **1.20.0** | minor bump |
| openai 3.13.0 | **3.14.0** (2026-09-14) | 4 days |
| boto3 1.43.79 | **1.43.98** | ~3 weeks of 1.43 patches |
| PyJWT 2.13.0 | **2.14.0** (2026-09-11) | minor bump |
| qdrant-client 1.13.2 | line-latest **1.13.3**; overall **1.19.1** | patch within chosen minor |

These packages exist and are appropriate choices. They were not re-read from PyPI at freeze, or the freeze copied slightly stale “current” numbers. boto3 in particular moves almost daily; pinning a patch as “current-stable” in an architecture spine will rot immediately.

### 3. Installed seed is internally consistent, and several majors behind live defaults

Not a lockfile lie — the spine says installed pins stay. It is still the live default of the *ecosystem*, which this lens must flag.

| Installed | Live (2026-09-18) | Note |
| --- | --- | --- |
| FastAPI 0.115.12 | 0.141.1 | Spine Deferred already names “FastAPI 0.141 / Qdrant 1.19 bumps”. Good. |
| uvicorn 0.34.2 | **0.53.0** (2026-09-14) | Large gap; still valid ASGI server. |
| pydantic 2.11.7 | **2.13.5** | Still Pydantic v2. |
| pydantic-settings 2.8.1 | **2.15.0** | |
| Celery 5.4.0 | **5.6.3** | 5.x still the line; 5.6.3 has a redis-py <5.3 reconnect regression. Seed `redis==5.2.1` would be on the wrong side of that if Celery were bumped without the client. |
| redis (Python) 5.2.1 | **8.1.0** | redis-py 6+ is current; 5.2.1 still talks to Redis 7.4. Live redis-py docs default Docker to Redis 8. |
| React 19.1.0 | **19.3.0** (`registry.npmjs.org/react/latest`) | Still React 19. |
| react-router-dom 7.6.1 | **7.18.4** (npm 2026-09-15) | Package is now a re-export of `react-router`; live default import is `react-router`. |
| TypeScript 5.8.3 | **7.0.2** (npm `latest`) | 5.8 is far from current; TS 5.9 and 6.x also shipped. |
| Vite 6.3.5 | **8.3.0** (npm, 2026-09-10) | Vite support policy: regular patches on 8.2; security on **6.4** and 8.0 — **6.3.5 is past the supported 6.x line**. |
| postgres:16-alpine | latest official `postgres:18` / `18.6-alpine` | 16-alpine still published (~16.15). PG 18 changed `PGDATA` volume path; staying on 16 avoids that. |
| redis:7.4-alpine | **8.10.1** (`latest`) | 7.4-alpine still published (7.4.11). Redis 8 license is RSALv2/SSPLv1/AGPLv3; 7.4 is RSALv2/SSPLv1. Seed choice still exists; it is not the live default. |

httpx 0.28.1 is the rare installed pin that **is** still current.

### 4. Stack table mixes three different kinds of version without labels

- Installed lockfile pins
- Intended first-add pins (claimed current-stable)
- Image tags that are rolling minors (`16-alpine`, `7.4-alpine`) not digest/patch pins

A later slice can “change the pin” in the table and think it changed architecture. Deferred already says FastAPI/Qdrant bumps are not invariants — the table still reads like a bill of materials.

### 5. qdrant-client 1.13.2 vs 1.13.3, and client/server pairing

Authoring was right **not** to take client 1.19 against server 1.13. Qdrant’s own upgrade skill: major.minor of SDK and server should match; adjacent minors are tested; storage compatibility is one minor at a time.

If the intended add is “match compose server 1.13.2”, the current client on that minor is **1.13.3**, not 1.13.2. Jumping client to 1.19.1 without the server is the pairing the spine correctly deferred.

Compose Qdrant exposes 6333 only. Client defaults also speak gRPC on 6334. Fine for REST; not a version error.

### 6. Live framework defaults vs adopted rules (still fit)

These are architecture choices, not pins. Rechecked against current docs so they are not training-data leftovers.

| Decision | Live default / docs | Fit |
| --- | --- | --- |
| FastAPI product routes as `def` (AD-3) | FastAPI docs: if the library has no `await`, use `def`; if unsure, use `def`. Sync handlers run in a threadpool. Official skill: default to `def`. | **Fits.** Sync SQLAlchemy + Celery `execute()` is a documented FastAPI pattern, not a 0.115 quirk. |
| SQLAlchemy 2.x sync `Session` | 2.0 is still the current *release* line; 2.1 is beta/rc. Sync Session remains first-class. Async is `AsyncSession` + greenlet extra. | **Fits** AD-3. Driver still unnamed (`psycopg`). |
| Celery calling sync `execute()` | Celery 5.6 still defaults to sync tasks. | **Fits** AD-4. |
| Official `openai` SDK (not LangChain engine) | Package is current (3.14.0), sync + async clients, Python >=3.10. LangChain still exists (memlog 1.3.15) and is correctly deferred. | **Fits** AD-5. |
| boto3 + S3 API for Garage or Amazon S3 | boto3 1.43.x current; Garage documents boto3 + path-style + region. | **Fits** AD-6. |
| One Qdrant collection + payload filter | Current Qdrant filter API unchanged in kind; client `query_points` is the live search entry (older `search` deprecated in 1.19 client). | **Fits** AD-7. When the server *is* bumped to 1.19, adapters should use `query_points`, not 1.13 `search`. |
| PyJWT HS* local issuer | 2.13+ is a security line; 2.14 is current. Empty HMAC keys now error. | **Fits** AD-8 if `jwt_secret` is non-empty. |
| Bearer in memory, not `localStorage` | Still a SPA convention, not a library default. `react-router-dom` 7 re-exports `react-router`; no auth implication. | Fine. |

## Technology still exists and still fits

All named technologies still exist on 2026-09-18: FastAPI, uvicorn, Pydantic, Celery, Redis, httpx, SQLAlchemy, Alembic, Qdrant, qdrant-client, OpenAI Python SDK, boto3, PyJWT, React 19, Vite, TypeScript, PostgreSQL, Garage. LangChain exists and is correctly *not* the engine.

MinIO Community Edition still exists as **source**, not as a maintained compose image. Replacing it with Garage is still the defensible call. Community forks (e.g. `pgsty/minio`) also exist; the spine did not need them once Garage is the seed — except the seed never landed in Compose.

## What was actually confirmed (do not “bump for freshness”)

- Repo FastAPI 0.115.12 and Qdrant v1.13.2 are real installed pins; current upstream is 0.141.1 / v1.19.1; Deferred already records that.
- `qdrant-client==1.13.2` exists; pairing it to server v1.13.2 is the documented Qdrant policy.
- Garage `v2.4.1` is the current Docker tag and is S3-compatible enough for a boto3 path-style adapter.
- MinIO CE is not a responsible compose pin in 2026.
- httpx 0.28.1 is still the PyPI latest.
- Python >=3.12 remains a valid floor.
- Sync FastAPI + sync SQLAlchemy Session + Celery worker is consistent with *current* framework docs, not a 2024 habit.

## Sources (fetched 2026-09-18)

- PyPI project pages / JSON: fastapi 0.141.1; openai 3.14.0; boto3 1.43.98; PyJWT 2.14.0; alembic 1.20.0; qdrant-client 1.19.1 and 1.13.2/1.13.3; SQLAlchemy 2.0.54; pydantic 2.13.5; pydantic-settings 2.15.0; httpx 0.28.1; redis 8.1.0; celery 5.6.3; uvicorn 0.53.0
- GitHub: `fastapi/fastapi` 0.141.1; `sqlalchemy/sqlalchemy` 2.0.54 (2026-09-15) and 2.0.52 (2026-08-11); `qdrant/qdrant` v1.13.2; `minio/minio` archived; openai-python changelog 3.13.0 → 3.14.0
- Docker Hub / official-images: `qdrant/qdrant:v1.19.1` and `:v1.13.2`; `dxflrs/garage:v2.4.1`; `postgres` 18.6 / 16.15 alpine; `redis` 8.10.1 / 7.4.11 alpine
- npm registry: react 19.3.0; typescript 7.0.2; vite 8.3.0; react-router-dom 7.18.4
- Docs: FastAPI concurrency page; Qdrant version-upgrade skill; Garage S3 compatibility / clients; Vite releases support policy; python.org 3.14.7

## Compact finding list (canonical)

1. **location:** Structural Seed / AD-6 / Stack Garage row — **trigger:** Garage named as Compose seed but absent from `compose.yaml` — **guard:** add the service or stop calling it the seed — **consequence:** documents/ingestion have no local S3 endpoint.
2. **location:** Stack intended adds — **trigger:** SQLAlchemy 2.0.52, Alembic 1.19.2, openai 3.13.0, boto3 1.43.79, PyJWT 2.13.0 claimed current-stable — **guard:** re-read PyPI at add time; 2.0.54 / 1.20.0 / 3.14.0 / 1.43.98 / 2.14.0 — **consequence:** first persistence/auth/S3 slice pins yesterday’s patch as if it were architecture.
3. **location:** Stack qdrant-client 1.13.2 — **trigger:** 1.13.2 exists and matches server *minor*; 1.13.3 is the last 1.13 client patch — **guard:** pin 1.13.3 if staying on server 1.13; do not take 1.19.1 until the image moves — **consequence:** skip a same-minor client fix for no reason, or later mismatch client/server.
4. **location:** Stack Vite 6.3.5 — **trigger:** Vite security backports are on 6.4, not 6.3; live is 8.3.0 — **guard:** treat 6.3.5 as an unsupported 6.x line if the web app stays on Vite 6 — **consequence:** no security patches on the installed Vite minor.
5. **location:** Stack table presentation — **trigger:** installed vs intended vs rolling image tags unlabeled — **guard:** split the table or mark rows — **consequence:** implementers bump lockfiles thinking they are changing architecture, or assume SQLAlchemy is already installed.
