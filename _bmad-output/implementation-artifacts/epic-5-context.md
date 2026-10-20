# Epic 5 Context: Harden for production

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Production can add stronger isolation, identity, and operations without rewriting `Actor`, the hexagonal ports, or the one filtered `chunks` collection. Postgres row-level security, sign-in through an identity provider, structured request and job logs, and a managed Postgres, Amazon S3, and Kubernetes topology are additive. Earlier slices keep working: the tenant boundary, local bootstrap sign-in, and the Compose environment stay in place. Planning artifacts include the architecture spine and the epics inventory; no standalone PRD, product brief, or UX design contract was present.

## Stories

- Story 5.1: Enforce tenant isolation in Postgres
- Story 5.2: Sign in with an identity provider
- Story 5.3: See what the API and the worker did
- Story 5.4: Run on managed Postgres, Amazon S3, and Kubernetes

## Requirements & Constraints

- Tenant isolation stays a security boundary. `tenant_id` still comes from the authenticated `Actor` (verified token claims or the job record), never from an untrusted client field used as the only filter. Cross-tenant reads stay prohibited. Authenticated-but-not-allowed, including `TenantIsolationError`, stays HTTP 403.
- Row-level security is a second check on the one shared Postgres schema, not a schema per tenant. Each policy keys off the tenant in the database session. Repositories still filter by `actor.tenant_id`. Tenant-owned tables, including documents and messages, stay in that schema.
- An identity-provider token is another way to build the same `Actor` (`user_id` and `tenant_id`). A missing or invalid token on a product route is still HTTP 401, with `"data": null` and `error` carrying a stable code and a human message. Product `/api/v1` responses stay inside `{data, error}`. `python -m app.cli bootstrap` and the local Bearer JWT, signed with `jwt_secret`, keep working. Jobs still carry flat `tenant_id`, `user_id`, and `document_id` and do not carry a token.
- Cookies, sessions, refresh, and revocation stay out of this epic. Roles stay off `Actor`. Until a later slice adds roles, every member of a tenant may use every document in that tenant.
- Operators need a structured record of each product request and each finished ingestion job, without secrets. A request log includes the actor's `tenant_id`, the route, and the status code, and omits passwords, `jwt_secret`, tokens, and document bytes. A finished job log includes `tenant_id`, `document_id`, and `ready` or `failed`, and shares a correlation id with the request that enqueued the job. `/health` and `/ready` stay on their current paths and outside the `{data, error}` envelope.
- The same API and worker run against managed Postgres, Amazon S3, and Kubernetes using environment variables. Object bytes stay in one bucket at `tenant_id/document_id/filename`. Local Compose still uses Garage. Redis and Celery remain the only async fabric. Qdrant stays one collection, `chunks`, and every query filter still includes `actor.tenant_id`.
- Domain and application tests stay on in-memory fakes and do not require Docker. The row-level policy is tested at the Postgres adapter. Secrets and deployment settings come from the environment and are never committed.

## Technical Decisions

- `Actor`, the hexagonal ports, and the `chunks` collection stay stable. Isolation, identity, and operations land in infrastructure adapters and deployment config. Domain imports none of FastAPI, SQLAlchemy, Celery, Qdrant, or a logging SDK. Application imports domain only. Use cases stay sync, take `Actor`, and never take Request or Response.
- Persistence stays SQLAlchemy with Alembic, in infrastructure only. Row-level security does not replace repository filters.
- The HTTP adapter verifies the identity-provider token and builds `Actor` from `user_id` and `tenant_id`. The worker still builds `Actor` from the job record. Neither the identity-provider token nor the local JWT goes on the job.
- Document bytes stay behind the existing blob port. The object-storage adapter takes endpoint, region, and credentials from the environment, so Compose Garage and Amazon S3 are the same port. There is no second storage port and no bucket per tenant.
- A Kubernetes deployment runs `api` and `worker`. Both reach Postgres, Redis, Qdrant, and object storage. `compose.yaml` remains the local environment.
- Structured logging lives in the HTTP and worker adapters. Domain and application do not import a logging or tracing SDK.
- Product routes stay synchronous under `/api/v1`. Health probes are not a template for new product use cases.

## Cross-Story Dependencies

- Depends on Epic 1 for `Actor`, bootstrap, the local Bearer JWT, the 401 envelope, and `/health` and `/ready` outside that envelope.
- Depends on Epic 2 for tenant-owned documents, the object key `tenant_id/document_id/filename`, and ingestion jobs whose payload is flat `tenant_id`, `user_id`, and `document_id`.
- Depends on Epic 3 for tenant-owned messages, and on Epic 4 leaving retrieval on the single filtered `chunks` collection. This epic does not change citations, chunk payload, or search behavior.
- Story 5.4 assumes Story 5.1: managed Postgres keeps both repository filters and row-level policies keyed off the tenant. Story 5.3 assumes product routes and ingestion jobs already exist so a request and its job can share a correlation id.
- Evaluation jobs, retrieval-quality changes, roles, and in-tenant access control are outside this epic.
