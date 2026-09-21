---
title: 'Bootstrap a tenant and sign in'
type: 'feature'
created: '2026-09-21'
status: 'done'
route: 'dispatch'
baseline_commit: 'fc111746bb33610fe3d97db5e6659b1c6b041a19'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/specs/spec-AI-RAG/http-envelope.md'
  - '{project-root}/_bmad-output/specs/spec-AI-RAG/config.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The API can report health, but nobody can create the first tenant or prove who they are. Later slices have no Actor and no `/api/v1` `{data, error}` contract.

**Approach:** A bootstrap command creates one Tenant and one password-authenticated User. Login issues a Bearer JWT. Product routes under `/api/v1` build Actor only from verified claims and use the envelope.

## Boundaries & Constraints

**Always:**
- `tenant_id` on Actor comes from the verified JWT, never from a client field as the only filter.
- Actor is `tenant_id` + `user_id` strings. No Role. "Admin" is the bootstrap account name.
- Password is stored only as a hash. Domain and application stay free of FastAPI, SQLAlchemy, and PyJWT. Product `execute()` and product routes are sync.
- Product JSON is `{data, error}` (`data` is an object, never a top-level array; `error.code` is uppercase snake_case). Map unauthenticated to 401, `TenantIsolationError` to 403, `NotFoundError` to 404, other `DomainError` to 409.
- Login is email + password with no tenant field. Unknown email and wrong password return the same 401 `INVALID_CREDENTIALS`. A signature that verifies but does not match a stored user is 401 `UNAUTHENTICATED`.
- Email is unique across users. IDs are UUID strings created in application code. Tenant-owned rows include `tenant_id`.
- Tests of domain and application use in-memory fakes and do not need Docker.
- **Decision:** If the bootstrap email already belongs to a user, `python -m app.cli bootstrap` exits 0, creates nothing, and leaves the password hash unchanged. If that email is new and a tenant or user already exists, the command exits non-zero and writes nothing.
- **Decision:** Access tokens expire 15 days after they are issued. There is no refresh token.

**Never:**
- Public self-register, roles, OIDC, cookies, sessions, refresh, revocation, or Postgres RLS.
- A web sign-in screen, token storage in the browser, or sending the JWT to Celery. The in-memory web session is deferred.
- Changing `GET /api/health` and `GET /api/ready` paths or bodies, document/chat domain behavior, or the Celery worker.
- Treating `GetReadiness` (async) as the product use-case template.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Bootstrap | Three `BOOTSTRAP_*` vars set; store empty | One Tenant and one User; password column is a hash, not the plaintext | Missing or blank var: non-zero exit, no rows |
| Bootstrap again | That same email already stored | Exit 0; no new rows; hash unchanged | New email while a tenant or user exists: non-zero exit, no writes |
| Login success | Matching email and password | `POST /api/v1/auth/login` → 200 `{ "data": { "access_token": "<jwt>" }, "error": null }`. Claims include `user_id` and `tenant_id` strings. `exp` is 15 days out | N/A |
| Login failure | Unknown email or wrong password | 401 `{ "data": null, "error": { "code": "INVALID_CREDENTIALS", "message": "<human>" } }` | Identical code and status for both |
| No / bad token | `GET /api/v1/me` with missing, malformed, or bad-signature Bearer | 401 envelope, code `UNAUTHENTICATED` | Expired token is the same 401 |
| Current member | Valid Bearer for a stored user | 200 `data`: `user_id`, `tenant_id`, `email`. Actor comes only from claims; the use case takes that Actor | Verified token whose user is gone → 401 `UNAUTHENTICATED` |
| Domain map | Product route raises `TenantIsolationError`, `NotFoundError`, or another `DomainError` | 403 `TENANT_ISOLATION`, 404 `NOT_FOUND`, 409 `DOMAIN_RULE_VIOLATION` | Replaces FastAPI `detail` for `/api/v1` only |
| Health | `GET /api/health`, `GET /api/ready` | Existing status JSON, no envelope | Unchanged |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/domain/tenancy.py` — reuse `TenantId`, `Tenant`, `assert_same_tenant` (lines 8–25).
- `apps/api/src/app/domain/identity.py` — reuse `UserId`, `User` (lines 8–21). The stored user carries a password hash; domain does not import a hash library.
- `apps/api/src/app/domain/errors.py` — add `NotFoundError` and `UnauthenticatedError`. Leave `InvalidDocumentTransition`.
- `apps/api/src/app/domain/documents.py`, `apps/api/src/app/domain/chat.py` — do not change.
- `apps/api/src/app/application/health/get_health.py` — copy the sync `execute()` shape (lines 12–17). Do not copy async `GetReadiness`.
- `apps/api/src/app/infrastructure/config/settings.py` — `jwt_secret` is already loaded (line 13). Add the three bootstrap fields.
- `apps/api/src/app/infrastructure/http/error_handlers.py` — `detail` bodies (lines 9–16) are wrong for `/api/v1`. Health routes must not start returning the envelope.
- `apps/api/src/app/infrastructure/http/health_router.py` — `/api/health`, `/api/ready` (lines 10–26). Do not change.
- `apps/api/src/app/bootstrap/create_app.py` — wires settings, CORS, handlers, health (lines 23–42). Add auth routes and a fake-use-case seam like `readiness_probes`.
- `apps/api/tests/test_health.py` — must keep passing, including `create_app(readiness_probes=[])`.
- `apps/web/` — do not change in this story.
- `apps/api/pyproject.toml` — add PyJWT 2.14.0, SQLAlchemy 2.0.54, Alembic 1.20.0.
- `.env.example` — document `BOOTSTRAP_*`. Do not commit real secrets.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/actor.py` — add Actor (`tenant_id`, `user_id` strings) — isolation key for later tenant use cases
- [x] `apps/api/src/app/domain/errors.py` — add `NotFoundError` and `UnauthenticatedError` — status map
- [x] `apps/api/src/app/domain/ports/auth.py` — sync ports to insert and look up tenants and users, and to hash or verify passwords — domain stays storage-agnostic
- [x] `apps/api/src/app/application/auth/models.py` — bootstrap and login inputs and results — no Request or Response
- [x] `apps/api/src/app/application/auth/bootstrap_tenant.py` — `execute` creates one tenant and one hashed user, or ignores an existing email — CLI and tests share it
- [x] `apps/api/src/app/application/auth/login.py` — `execute` checks email and password — same failure for unknown email and bad password
- [x] `apps/api/src/app/application/auth/get_current_member.py` — `execute(actor)` returns that member — a tenant use case takes Actor
- [x] `apps/api/tests/test_auth.py` — in-memory fakes for bootstrap, repeat bootstrap, login, current member, and isolation — no Docker
- [x] `apps/api/src/app/infrastructure/auth/passwords.py` — Argon2id via `argon2-cffi` — plaintext is never stored
- [x] `apps/api/src/app/infrastructure/auth/jwt.py` — PyJWT HS256 with `jwt_secret`; claims `user_id`, `tenant_id`, and `exp` 15 days out — verify rejects a bad signature and an expired token
- [x] `apps/api/src/app/infrastructure/persistence/` — SQLAlchemy models and repos for `tenants` and `users` (unique email, `tenant_id`, password hash) — first tenant-owned tables
- [x] `apps/api/alembic/` — initial migration for those tables — schema owned by Alembic
- [x] `apps/api/pyproject.toml` — pin PyJWT 2.14.0, SQLAlchemy 2.0.54, Alembic 1.20.0, `argon2-cffi`, and psycopg v3 — this slice owns the pins
- [x] `apps/api/src/app/infrastructure/http/responses/api_response.py` — `{data, error}` helpers — one envelope for `/api/v1`
- [x] `apps/api/src/app/infrastructure/http/dependencies/auth.py` — read Bearer, verify JWT, build Actor — no client-supplied tenant
- [x] `apps/api/src/app/infrastructure/http/auth_router.py` — `POST /api/v1/auth/login` and `GET /api/v1/me` — login and member routes
- [x] `apps/api/src/app/infrastructure/http/error_handlers.py` — envelope status map for `/api/v1` — drop `detail` on product routes
- [x] `apps/api/src/app/infrastructure/config/settings.py` — read `BOOTSTRAP_TENANT_NAME`, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` — secrets stay in env
- [x] `apps/api/src/app/cli.py` — `python -m app.cli bootstrap` calls the use case through the composition root — only MVP provision path
- [x] `apps/api/src/app/bootstrap/create_app.py` — register the v1 router and let tests inject fake use cases — health seam stays
- [x] `apps/api/tests/test_auth_http.py` — TestClient covers login, `/me`, 401, expiry, and domain status codes — envelope is the contract
- [x] `.env.example` — document `BOOTSTRAP_*` — operators can run bootstrap

**Acceptance Criteria:**
- Given the three `BOOTSTRAP_*` variables and an empty store, when `python -m app.cli bootstrap` runs, then one Tenant and one User exist and the stored password is a hash.
- Given that user already exists, when bootstrap runs again, then it exits 0 and does not create another user or change the hash.
- Given that user, when they log in with email and password, then the body is `{data, error}` with a Bearer JWT whose claims include `user_id` and `tenant_id` as strings and an `exp` 15 days out.
- Given a `/api/v1` route, when the Bearer token is missing, invalid, or expired, then the status is 401 and the body is the error envelope.
- Given a valid token, when `GET /api/v1/me` runs, then Actor is built only from the verified claims and the use case receives that Actor.
- Given a domain error on a product route, when the adapter maps it, then 401 / 403 / 404 / 409 follow the matrix and `/api/health` and `/api/ready` stay outside the envelope.

## Implementation Notes

- Bootstrap, login, `GET /api/v1/me`, the `{data, error}` map, Alembic `tenants`/`users`, and `python -m app.cli bootstrap` are in place. The web app was not changed.
- CLI exit codes are covered in `apps/api/tests/test_cli_bootstrap.py` with in-memory repositories behind the CLI seam. `uv run pytest` in `apps/api`: 23 passed, no Docker.
- Migrations are not applied by Compose. A real database needs `alembic upgrade head` before bootstrap.

## Spec Change Log

## Review Triage Log

- high — `README.md` still says SQLAlchemy starts at documents, while this slice already migrates `tenants`/`users`. An operator following the README will not run `alembic upgrade head` or bootstrap. Patch the run notes.
- low — rejected. Concurrent bootstraps can both pass `any_exist` and insert two tenants. Everyday use is one operator command. Closing the race needs locking or a singleton constraint, not a direct correction.
- low — rejected. `users.tenant_id` has no foreign key. The CLI writes tenant and user in one transaction, so the app path does not create orphans. A constraint would guard a state the product path does not reach.
- false — Case-variant emails can both be stored. The spec's uniqueness rule is implemented as an exact unique `email` column. It does not require casefold, so this does not break the written rule.
- medium — `POST /api/v1/auth/login` with an invalid body hits FastAPI's `RequestValidationError` and returns `detail`, not `{data, error}`. The product envelope rule is missed on that path. Patch the handler.
- low — rejected. `Argon2PasswordHasher.verify` only catches `VerifyMismatchError`. A corrupt hash would 500. Stored hashes come from `hash()` and fit the column. The fix is an extra guard for a hash the app does not write.
- low — rejected. Login skips Argon2 when the email is missing, so the two 401s differ in timing. The spec requires the same status and code, which the handler already returns. Equalizing timing adds a branch.
- false — `GetCurrentMember` loads by user id, then `assert_same_tenant` before returning. A cross-tenant actor does not receive the member. The query is not the filter; the assertion is.
- low — `create_app` builds a SQLAlchemy engine whenever login, member, or JWT is omitted, so health tests construct an engine they never use. Patch: open the engine on first auth use.
- low — rejected. Login passwords have no max length. A huge password is not an everyday client. A max length is an extra parameter.
- false — Spec status is `in-review` while sprint status is `in-progress`. Review sets the spec status at its start; the sprint key was set to `in-progress` when implementation began. That is not a product defect.
- false — No Compose Postgres test. The spec requires in-memory tests and excludes Docker. A live database run is outside that intent.
- low — rejected. Same corrupt-hash 500 as the Argon2 finding above, cited at `passwords.py`.
- medium — Same missing login envelope, cited at `auth_router.py`. Grouped with the validation-handler finding.
- low — rejected. Concurrent same-email bootstrap can raise an uncaught `IntegrityError`. One operator is the everyday path. Catching it is an extra guard.
- low — rejected. Same empty-check race as the two-tenant finding, cited at `bootstrap_tenant.py`.
- false — `postgres://` is not rewritten. Compose and settings use `postgresql://`, which `to_sqlalchemy_url` already rewrites. The cited failure does not happen for this project's URL.
- low — rejected. Same missing foreign key, cited on the migration.
- false — A blank `BootstrapCommand` can be saved if a caller skips the CLI. `python -m app.cli bootstrap` rejects blank env before `execute`. The provision path does not persist empty fields.
- low — rejected. A login email with surrounding spaces fails the lookup. Bootstrap stores the stripped env value, and there is no sign-in form in this story. Stripping is an extra branch.
- low — rejected. Same unbounded password, cited on `LoginBody`.
- medium — claim confirmed. Validation failures on `/api/v1` still use FastAPI `detail`. Grouped with the envelope handler.
- medium — `Argon2PasswordHasher.verify` is never called. Login tests use `FakePasswordHasher`. A verify that always returns false would still pass. Patch a round-trip test. Pre-verified.
- medium — SQLAlchemy repositories and `to_sqlalchemy_url` never run under pytest. CLI tests replace them and HTTP tests inject fakes. Patch a SQLite round-trip and a URL rewrite assertion. Pre-verified.
- medium — Bootstrap conflict tests always seed both a tenant and a user, so either `any_exist` arm can be deleted without a failure. Patch tenant-only and user-only cases. Pre-verified.
- low — Same health-test engine construction, from the verification layer. Grouped with the `create_app` finding.
- low — rejected. Same corrupt-hash gap, from the verification layer's other findings.

## Design Notes

Hash with Argon2id (`argon2-cffi`). Sign with PyJWT HS256. Login body is `{ "email", "password" }`. `GET /api/v1/me` is the protected route that forces a use case to take Actor.

`users.email` is unique. `users` stores `tenant_id`, `email`, and `password_hash`. Member reads filter by `actor.tenant_id`.

Map `UnauthenticatedError` to 401 before the generic `DomainError` handler. Login uses `INVALID_CREDENTIALS`. A missing, invalid, or expired Bearer uses `UNAUTHENTICATED`.

HTTP tests inject fakes through `create_app`, as health tests inject probes. Persistence is a sync SQLAlchemy session plus Alembic. psycopg v3 is the driver; pin it in `pyproject.toml`. Domain tests must not open Postgres. New packages need `__init__.py` files beside the modules above.

## Verification

**Commands:**
- `cd apps/api && python -m pytest` — expected: existing health tests pass; auth use-case and HTTP tests pass without Docker
