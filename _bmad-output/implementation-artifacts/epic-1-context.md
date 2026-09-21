# Epic 1 Context: Sign in to your organization

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A person can authenticate as a member of a tenant so every later action is scoped to that tenant. This epic also establishes the product `/api/v1` `{data, error}` contract that later slices inherit. The repo is brownfield: extend the existing API and web seed; do not scaffold a new repository. `/health` and `/ready` already exist and stay outside the envelope. No separate PRD, product brief, or UX design artifact was present in planning artifacts; requirements below are distilled from the epics inventory and architecture spine.

## Stories

- Story 1.1: Bootstrap a tenant and sign in

## Requirements & Constraints

- Bootstrap CLI (`python -m app.cli bootstrap`) creates one Tenant and one password-authenticated User from `BOOTSTRAP_TENANT_NAME`, `BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD`. Store the password only as a hash. "Admin" means that account, not a Role on Actor.
- Login issues a Bearer JWT whose claims include `user_id` and `tenant_id` as strings. HTTP builds Actor only from verified claims. There is no public self-register in MVP and no Role on Actor.
- Missing or invalid token on a product route returns HTTP 401 with the `{data, error}` envelope.
- Product `/api/v1` JSON is always `{data, error}`: success has a data object and `"error": null`; failure has `"data": null` and `error: {"code": "<STABLE_CODE>", "message": "<human>"}`. `data` is never a top-level array. `error.code` is uppercase snake_case. Map domain outcomes to 401, 403, 404, 409. `/health` and `/ready` stay on current paths and outside the envelope. The web client reads status plus `error.code` / `error.message` and does not invent codes.
- Tenant isolation is a security boundary: `tenant_id` comes from the authenticated Actor, never from an untrusted client field as the only filter. Authenticated-but-not-allowed, including `TenantIsolationError`, is HTTP 403.
- The web app sends `Authorization: Bearer` and keeps the token in memory, not `localStorage`. Secrets and bootstrap values come from the environment only.
- Domain and application tests use in-memory fakes (no Docker). Python type hints required; TypeScript is `strict`. Untrusted input is validated at HTTP adapters.

## Technical Decisions

- Hexagonal layout is binding: domain imports none of FastAPI/SQLAlchemy/Celery/etc.; application imports domain only; use cases do not take Request/Response. One vertical slice at a time; identity-and-tenancy is first.
- Actor (`tenant_id` + `user_id` as strings) is the isolation key. Every use case that touches a tenant resource takes Actor. Roles stay off Actor.
- Product `execute()` methods and ports are sync; FastAPI product routes are `def`.
- This API issues JWTs for local User rows, signed with `jwt_secret` from env. HTTP verifies the signature and builds Actor from claims. Jobs never carry the JWT.
- One Postgres schema; tenant-owned tables include `tenant_id`. IDs are UUID strings created in application/domain. JSON dates are UTC ISO-8601.
- Domain raises `DomainError` subclasses; add `NotFoundError`. HTTP maps: unauthenticated/missing/invalid token → 401, `TenantIsolationError` → 403, `NotFoundError` → 404, other `DomainError` → 409. Replace existing FastAPI `detail` handlers for `/api/v1`.
- Bootstrap CLI is another adapter on the shared composition root. Password-hashing library is chosen in this identity slice. PyJWT is the intended JWT library.
- OIDC, cookies, sessions, refresh, revocation, and Postgres RLS are deferred; local Bearer JWT is enough for this epic.

## Cross-Story Dependencies

- This epic has a single story; it establishes Actor, Bearer JWT auth, and the `/api/v1` envelope that every later epic and story inherits.
- Later epics assume identity-and-tenancy is done before documents, ingestion, retrieval, and chat.
