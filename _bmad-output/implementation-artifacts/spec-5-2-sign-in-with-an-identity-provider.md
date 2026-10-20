---
title: 'Sign in with an identity provider'
type: 'feature'
created: '2026-10-20'
status: 'done'
route: 'dispatch'
baseline_commit: '5aab52bc42fc9d35a578656c9776f570eaf1330c'
review_loop_iteration: 2
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Product routes accept only a Bearer JWT this API signs with `jwt_secret`. Production needs the same `Actor` from an organization identity provider, without a second identity model.

**Approach:** When OIDC settings are present, a product route under `/api/v1` also accepts that provider's access token, verifies it, and builds `Actor` from `user_id` and `tenant_id`. The use case still receives `Actor`. Local login, bootstrap, and worker jobs stay as they are.

## Boundaries & Constraints

**Always:**
- `Actor` stays `tenant_id` and `user_id` strings. No roles. The HTTP adapter builds it from the verified token. A client field is never the tenant.
- **Decision:** OIDC is off unless `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL` are all non-empty. Off means product routes accept only the local HS256 JWT.
- **Decision:** The caller sends `Authorization: Bearer`. No redirect, cookie, session, refresh, revocation, or new login route. The web app is unchanged.
- **Decision:** The provider token is RS256. Verification checks the signature, `iss`, and `aud`. `exp` is checked only when that claim is present: a past `exp` is an invalid token, and a token that omits `exp` stays valid. The local verifier still accepts only HS256 with `jwt_secret`. A token is tried against one algorithm, taken from its header only to choose the verifier.
- **Decision:** `Actor` comes from claims `user_id` and `tenant_id`. Each must be a non-empty string of at most 36 characters. A token that only has `sub`, or a blank or longer claim, is an invalid token. No migration.
- **Decision:** The token check does not read `users`. A product route that only needs `Actor` runs when that `user_id` is not stored. `GET /api/v1/me` still returns 401 when the user row is missing.
- A missing or invalid token on a product route is HTTP 401 `{ "data": null, "error": { "code": "UNAUTHENTICATED", "message": "<human>" } }`. Login failure stays `INVALID_CREDENTIALS`.
- `python -m app.cli bootstrap` and `POST /api/v1/auth/login` keep issuing the local JWT. Jobs stay flat `tenant_id`, `user_id`, and `document_id` with no token.
- Domain and application tests stay on in-memory fakes. The default `pytest` run does not need Docker or a live provider. Secrets stay in the environment.

**Never:**
- Changing `Actor`, hexagonal ports, Qdrant collection `chunks`, repository filters, or row-level security.
- Putting either token on the Celery job. Forwarding the provider token to the worker.
- A schema change, a user-provisioning use case, cookies, or a second `Actor` type.
- Domain or application imports of FastAPI, PyJWT, or an HTTP client.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Provider token | OIDC settings set; Bearer access token verifies; `user_id` and `tenant_id` are non-empty and at most 36 characters | Product route runs the use case with that `Actor`; body is `{data, error}` | N/A |
| No exp | OIDC on; signature, `iss`, and `aud` verify; the `exp` claim is absent | Product route runs with that `Actor` | N/A |
| Expired exp | OIDC on; signature, `iss`, and `aud` verify; `exp` is in the past | 401 `UNAUTHENTICATED` | N/A |
| No local user | Same verified provider token; `users` has no row for that `user_id` | A route that only needs `Actor` still runs | `GET /api/v1/me` stays 401 `UNAUTHENTICATED` |
| Local JWT | OIDC on or off; Bearer is a current HS256 access token | Same `Actor` as today; login still returns `access_token` | N/A |
| OIDC off | The three OIDC variables empty; Bearer is a provider token | Treated as an invalid token | 401 `UNAUTHENTICATED` |
| Missing token | Product route; no Bearer | 401 envelope, code `UNAUTHENTICATED` | Same code for a bad signature, wrong `iss` or `aud`, expired token, only `sub`, or a blank or longer `user_id` or `tenant_id` |
| Worker | Document enqueued after a provider-token request | Job kwargs are `tenant_id`, `user_id`, `document_id` only | N/A |
| Bootstrap | Three `BOOTSTRAP_*` variables set | Unchanged command result | N/A |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/infrastructure/http/dependencies/auth.py` — `build_require_actor` (line 16) takes `JwtService`, reads `HTTPBearer`, and returns `Actor` from `user_id` and `tenant_id`. Add an optional provider verifier. Callers that omit it stay HS256-only, so current HTTP tests keep passing.
- `apps/api/src/app/infrastructure/auth/jwt.py` — `JwtService.verify_access_token` (line 32) allows only HS256. Reuse it. Do not accept RS256 here.
- `apps/api/src/app/infrastructure/config/settings.py` — `jwt_secret` (line 17) via `JWT_SECRET`. Add three empty-string OIDC fields. `load_settings` (line 40) already reads the environment.
- `apps/api/src/app/bootstrap/create_app.py` — `_default_auth` (line 261) builds `JwtService`. `create_app` passes that service into `build_auth_router`, `build_documents_router`, and `build_conversations_router` (lines 384–407). Pass the verifier only when all three settings are set.
- `apps/api/src/app/infrastructure/http/auth_router.py` — login (line 39) still signs with `JwtService`. `GET /me` (line 53) still calls `GetCurrentMember`.
- `apps/api/src/app/infrastructure/http/documents_router.py` and `conversations_router.py` — `build_require_actor(jwt_service)` at lines 49 and 71. Thread the same optional verifier. Do not change use-case calls.
- `apps/api/src/app/infrastructure/worker/document_job_queue.py` — `enqueue` (line 7) kwargs are the three ids. `tasks.py` `process_document` (line 12) builds `Actor` from those kwargs. Do not change.
- `apps/api/src/app/cli.py` — bootstrap. Do not change.
- `apps/api/src/app/domain/actor.py` — `Actor` (line 6). Do not change.
- `apps/api/src/app/infrastructure/ingestion/qdrant_chunk_store.py` — `_COLLECTION = "chunks"` (line 22). Do not change.
- `apps/api/src/app/infrastructure/persistence/models.py` — `UserRow.id` and `ConversationRow.user_id` are `String(36)` (lines 21 and 42). No foreign key from conversations to users.
- `apps/api/pyproject.toml` — `PyJWT==2.14.0` has no crypto extra. RS256 needs it.
- `apps/api/tests/test_auth_http.py` — local login, 401 `UNAUTHENTICATED`, and expired HS256. Keep green.
- `.env.example` — document the three OIDC variables as empty. Do not commit secrets.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/pyproject.toml` — Depend on `PyJWT[crypto]==2.14.0` so RS256 verification can run. — The local HS256 path already uses PyJWT.
- [x] `apps/api/src/app/infrastructure/config/settings.py` — Add `oidc_issuer`, `oidc_audience`, and `oidc_jwks_url`, default `""`. — Unset keeps Compose and tests on the local JWT.
- [x] `apps/api/src/app/infrastructure/auth/oidc.py` — Verify an RS256 access token against issuer, audience, and JWKS. Check `exp` only when it is present; do not require the claim. Require `user_id` and `tenant_id` as non-empty strings of at most 36 characters. Any `Exception` from `jwt.decode` or from fetching and reading the JWKS, including a non-UTF-8 body and a dropped connection, becomes `UnauthenticatedError`. A null `exp` and a non-JSON JWKS body are that failure. Tests supply key material and perform no HTTP. — Domain stays free of this module.
- [x] `apps/api/src/app/infrastructure/http/dependencies/auth.py` — If the header `alg` is HS256, verify with `JwtService`. If it is RS256 and a verifier was provided, verify with that. Otherwise raise `UnauthenticatedError`. Return `Actor` from those claims. Do not open a database session. — One dependency for auth, documents, and conversations.
- [x] `apps/api/src/app/bootstrap/create_app.py` — Build the verifier when all three settings are non-empty and pass it into the three routers. — OIDC stays off in the default test app.
- [x] `apps/api/src/app/infrastructure/http/auth_router.py` — Accept the optional verifier and pass it to `build_require_actor`. Leave login and `/me` use cases as they are. — `/me` still loads the member after `Actor` exists.
- [x] `apps/api/src/app/infrastructure/http/documents_router.py` — Same optional verifier argument. — Upload and list receive `Actor` from the provider token.
- [x] `apps/api/src/app/infrastructure/http/conversations_router.py` — Same optional verifier argument. — Ask still enqueues no token.
- [x] `apps/api/tests/test_oidc_http.py` — Cover the matrix: verified provider token yields `Actor` on one product route even when `users` has no matching row; a token that omits `exp` and otherwise verifies does too; local HS256 still works with OIDC on; OIDC off rejects a provider token; missing, bad signature, wrong issuer, wrong audience, expired `exp`, null `exp`, `sub`-only, and over-long claims are 401 `UNAUTHENTICATED` and not 500. A non-JSON JWKS body is 401. A JWKS body that is not UTF-8 is 401. `GET /api/v1/me` with a provider token for a stored user returns 200 and that user's email. The verifier built from settings accepts a token only for that issuer, audience, and JWKS URL. One or two OIDC settings still start the app, accept HS256, and reject RS256. An HS256 token with a 37-character `tenant_id` is 401. The enqueued job has the three ids and no token. No Docker and no socket. — Default `pytest` runs these without a provider.
- [x] `.env.example` — Add the three variables, empty. — Names match `Settings`.

**Acceptance Criteria:**
- Given `cd apps/api && uv run --extra dev pytest` with no OIDC variables and no Postgres, when it runs, then existing tests pass and `tests/test_oidc_http.py` passes without Docker.
- Given `Actor`, the ports, and Qdrant collection `chunks`, when this story is done, then those contracts are unchanged.
- Given `python -m app.cli bootstrap` and `POST /api/v1/auth/login`, when OIDC settings are empty, then both behave as they do today.

## Implementation Notes

- First derivation: `cd apps/api && uv run --extra dev pytest` was 201 passed, 10 skipped. `tests/test_oidc_http.py` passed with sockets blocked. That code was reverted after review loop 1 for an intent gap on tokens that omit `exp`.
- Second derivation: `cd apps/api && uv run --extra dev pytest` was 204 passed, 10 skipped. The skips are `tests/test_tenant_rls.py`. `tests/test_oidc_http.py` is 24 passed, including a token that omits `exp`, a past `exp`, a null `exp`, a non-JSON JWKS body, partial OIDC settings, the settings-built issuer and audience, and an HS256 `tenant_id` of 37 characters. That code was reverted after review loop 2 so JWKS read failures become 401.
- Third derivation: `cd apps/api && uv run --extra dev pytest` was 197 passed, 10 skipped. `tests/test_oidc_http.py` covers a missing `exp`, a past and null `exp`, non-JSON and non-UTF-8 JWKS bodies, a truncated JWKS read, `/me` for a stored user, partial settings, and the three-id job.
- Review patches added an HS256 37-character `user_id`, numeric provider ids, and a bad signature on the settings-built verifier. The same command was 197 passed, 10 skipped.
- Third derivation: `cd apps/api && uv run --extra dev pytest` was 197 passed, 10 skipped. The skips are `tests/test_tenant_rls.py`. `tests/test_oidc_http.py` is 17 passed. JWKS reads that are not JSON, not UTF-8, or stop early are 401. Sockets stay blocked in that file.

## Review Triage Log

- medium — `verify_rs256_access_token` calls `jwt.decode` with `require: []`. A signed token that has `iss` and `aud` and no `exp` decodes. Confirmed against PyJWT 2.14: that token is accepted. The frozen line says verification checks `exp`, and the matrix only lists an expired `exp` as 401, so the spec does not pick one reading.
- false — An `iat` a few seconds ahead raises `ImmatureSignatureError`, which is a `PyJWTError` and becomes 401. A token that is not yet valid is rejected. The spec does not require leeway.
- medium — `PyJWKClient.fetch_data` lets `json.JSONDecodeError` out of `json.load`. `_signing_key` catches only `jwt.PyJWTError`, so a non-JSON JWKS body becomes HTTP 500. The `oidc.py` task says to raise `UnauthenticatedError` on failure.
- low — rejected. A failed JWKS fetch uses the library timeout of 30 seconds and is not cached. A healthy set is cached for 300 seconds. Everyday traffic does not hit the timeout, and choosing another timeout adds a setting.
- false — `PyJWKClient` allows an `http` JWKS URL. The URL is operator configuration, and the spec does not require `https`.
- low — rejected. `get_signing_key_from_jwt` looks up `kid`. A token without `kid` is 401 even when the set has one key. The design notes specify `PyJWKClient`, and everyday providers send `kid`. A custom matcher would be a new branch.
- false — One or two OIDC variables leave OIDC off, and a provider token is 401. That is the frozen rule that all three must be set. The task asks `.env.example` to list the names empty, not a README change.
- false — `user_id` and `tenant_id` are not checked against `users` or against each other. The frozen decision says the token check does not read `users`.
- false — A claim of `" abc"` is a non-empty string of at most 36 characters, which is the frozen rule. Whitespace-only claims are already rejected.
- false — PyJWT accepts an `aud` list that includes the configured audience. That is an audience check. The spec does not mention `azp` or `strict_aud`.
- low — `sprint-status.yaml` says `in-progress` while this review was running. Developers reading the tracker see the story as still being implemented.
- medium — same missing-`exp` claim at `oidc.py` decode. A signed token that omits `exp` never expires.
- medium — `exp` set to `null` raises `TypeError` inside `jwt.decode`, which is not a `PyJWTError`, so the product route returns 500. Confirmed: `int()` fails on `None`.
- medium — same non-JSON JWKS claim. `JSONDecodeError` is not caught, so the route returns 500.
- false — A JWKS URL whose scheme is not `http` or `https` raises `PyJWKClientError` in `PyJWKClient.__init__` and the app does not boot. That refuses `file:` and other schemes before any token is accepted.
- medium — same missing-`exp` claim, filed again against the frozen "checks `exp`" line. `jwt.decode` still accepts a token that omits `exp`.
- medium — `JSONDecodeError`, `TypeError`, and `OverflowError` leave `verify_rs256_access_token` because the `except` names only `jwt.PyJWTError`. A null `exp` raises `TypeError` before that handler, and a non-JSON JWKS body raises `JSONDecodeError` in `fetch_data`. Both become HTTP 500. The task says to raise `UnauthenticatedError` on failure.
- medium — verification gap, pre-verified. `test_jwks_client_is_built_only_for_settings_and_fetch_failure_is_401` only asserts 401 after a stub that raises before `jwt.decode`. Dropping `_oidc_verifier_from_settings` still passes. Issuer, audience, and JWKS URL are not what the test observes.
- medium — verification gap, pre-verified. No test sets one or two of the three OIDC settings. Changing `_oidc_enabled` to a single non-empty issuer makes `create_app` raise `ValueError`, and the suite still passes.
- medium — verification gap, pre-verified. `test_overlong_local_jwt_is_unauthenticated` uses a 37-character `user_id` only. Removing the `tenant_id` length check in `_actor_from_claims` stays green, and an HS256 token can carry a 37-character `tenant_id`.
- carried false — `jwt.decode` still uses leeway 0. An `iat` or `nbf` in the future is `ImmatureSignatureError` and 401. Same claim as the first review.
- carried low — rejected. A dead JWKS endpoint still uses the library timeout, cache, and unknown-`kid` cooldown. Not patched again.
- carried false — an `http` JWKS URL is still accepted. The spec does not require `https`.
- carried low — rejected. A token without `kid` is still 401 through `PyJWKClient`. Not patched again.
- carried low — `sprint-status.yaml` still says `in-progress` while this spec is in review. Not patched again.
- false — A 5000-deep JSON object loads on this runtime. PyJWT turns a payload `ValueError` into `DecodeError`, which is a `PyJWTError` and becomes 401. `RecursionError` did not occur.
- false — The frozen rule builds `Actor` from `user_id` and `tenant_id` after signature, `iss`, and `aud`. It does not check `typ`.
- low — rejected. `Settings` still reads `OIDC_*` from the environment. The acceptance command runs with those variables unset.
- false — `PyJWKClient(" ")` raises `PyJWKClientError` during startup and accepts no token. A padded issuer fails the `iss` check.
- false — `.env.example` lists the three names empty, which is the task.
- medium — `json.loads` of a non-UTF-8 JWKS body raises `UnicodeDecodeError`. That is a `ValueError`, not `JSONDecodeError`, and `_DECODE_FAILURES` does not name it, so the route returns 500.
- medium — `HTTPResponse.read` raises `http.client.IncompleteRead` when the body stops early. `fetch_data` catches `URLError` and `TimeoutError` only, so that exception returns 500.
- medium — verification gap, pre-verified. `GET /api/v1/me` with a provider token is only asserted as 401 when no user is stored. That is the same code as a rejected token. Removing `oidc_verifier` from `build_auth_router` stays green, so a stored member can get 401 for a valid provider token.
- low — A signed HS256 token with `exp` set to null raises `TypeError` in `JwtService.verify_access_token`, which catches only `PyJWTError`. `jwt.py` is unchanged in this diff. The signer needs `jwt_secret`.
- carried low — A signed HS256 token with a null or non-finite time claim still leaves `JwtService.verify_access_token` as `TypeError` and can become HTTP 500. Same claim. Not patched again.
- medium — verification gap, pre-verified. An HS256 token with a 37-character `user_id` is not asserted. Removing that length check in `_actor_from_claims` stays green because the RS256 case fails earlier in `oidc.py` and the HS256 test only uses a long `tenant_id`.
- medium — verification gap, pre-verified. A provider token with a numeric `user_id` or `tenant_id` is not asserted. Deleting the `isinstance(str)` check then calls `.strip()` on an int outside `except Exception` and the route returns 500.
- medium — `test_settings_verifier_binds_issuer_audience_and_jwks_url` never sends a bad signature. A settings-built verifier that skips the signature check still returns 200 for a valid-looking token and 401 for a wrong issuer.
- false — `verify_rs256_access_token` catches `Exception`. A non-UTF-8 JWKS body and a truncated read are 401 in `test_jwks_body_failures_are_unauthenticated`. The design notes are older than that task.
- false — The `oidc.py` task says tests supply key material and perform no HTTP. Success cases inject a key or stub `get_signing_key_from_jwt` on purpose.
- carried false — A whitespace JWKS URL still raises `PyJWKClientError` at startup. Same claim.
- carried false — One or two OIDC variables still leave the feature off. That is the frozen rule.
- low — rejected. The spec notes repeat "Third derivation" and the frontmatter still says review loop 2. The fix is editing this spec.
- carried low — `sprint-status.yaml` still says `in-progress` while the spec is `in-review`. Not patched again.
- low — `GET /api/v1/me` with a stored user and a different `tenant_id` is 403 in memory and 401 under Postgres row-level security. `GetCurrentMember` and `get_by_id` are unchanged from story 5.1.
- low — rejected. `apps/api/Dockerfile` runs `pip install .`, which installs `PyJWT[crypto]` from `pyproject.toml`. The image never used `uv.lock`. RS256 still gets `cryptography`.

## Spec Change Log

- Trigger: the human kept the library `exp` check. Review also found `JSONDecodeError` and `TypeError` leaving the verifier as HTTP 500, and tests that did not lock the settings-built verifier, partial OIDC settings, or an over-long HS256 `tenant_id`.
- Amended: the frozen decision and matrix now say a missing `exp` stays valid and a past `exp` is 401. The `oidc.py` and test tasks now require that, and they require decode and JWKS failures that are not `PyJWTError` to become `UnauthenticatedError`.
- Known-bad state avoided: a re-derivation that rejects every token without `exp`, or that returns 500 for a null `exp` or a non-JSON JWKS body.
- KEEP: claim names `user_id` and `tenant_id` at most 36 characters; no `users` lookup on the token check; OIDC off unless all three settings are set; HS256 and RS256 chosen from the header `alg` and then pinned; jobs stay the three ids; local login and bootstrap unchanged; tests inject a public key and open no socket.
- Trigger: a JWKS body that is not UTF-8 raises `UnicodeDecodeError`, and a JWKS read that stops early raises `http.client.IncompleteRead`. Neither is `JSONDecodeError` or `URLError`, so both leave the named exception tuple and the route returns 500.
- Amended: the `oidc.py` task now turns any `Exception` from `jwt.decode` or the JWKS fetch into `UnauthenticatedError`. The test task now requires a non-UTF-8 JWKS body to be 401, and `GET /api/v1/me` with a provider token for a stored user to return 200 and that email.
- Known-bad state avoided: HTTP 500 for a binary JWKS body or a truncated JWKS read, and an auth router that can drop the provider verifier while `/me` still looks like a 401.
- KEEP: a missing `exp` stays valid; a past `exp`, a null `exp`, and a non-JSON JWKS body stay 401; the settings-built verifier is checked for issuer, audience, and JWKS URL; partial OIDC settings still serve local HS256; an HS256 `tenant_id` of 37 characters stays 401.

## Design Notes

Choose the verifier from the unverified header `alg` and then pin the algorithm in the library call. HS256 never reaches the JWKS client. RS256 never reaches `jwt_secret`. `alg` of `none` or anything else is 401. That keeps a local token from being checked as a provider token.

`jwt.decode` keeps `require` empty. `verify_exp` then rejects a past `exp` and accepts a token that omits `exp`. Catch `TypeError` and `OverflowError` around that call so a null `exp` is 401. Catch `json.JSONDecodeError` and `AttributeError` around the JWKS fetch for the same reason.

`PyJWKClient` fetches `OIDC_JWKS_URL` only when the verifier is constructed for real settings. Tests pass a public key into the same verify function so pytest does not open a socket. One test stubs `get_signing_key_from_jwt` to return that public key and asserts the issuer, audience, and JWKS URL from settings.

`GetCurrentMember` still returns 401 when the user row is missing. That path is not the token check.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` — expected: existing tests pass, and `tests/test_oidc_http.py` passes with OIDC variables unset and without Docker
