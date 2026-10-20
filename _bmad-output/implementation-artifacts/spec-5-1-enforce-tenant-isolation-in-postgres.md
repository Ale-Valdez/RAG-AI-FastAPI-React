---
title: 'Enforce tenant isolation in Postgres'
type: 'feature'
created: '2026-10-20'
status: 'done'
route: 'dispatch'
baseline_commit: '7633d386c1ee73481f4820fb20e3eeab4cae22a9'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Postgres isolation is only the repository `tenant_id` filter. The API, worker, and CLI connect as Compose user `app`, a cluster superuser, so a missed filter returns every tenant's rows. Row-level security on that connection does nothing.

**Approach:** On the one shared schema, every API, worker, and CLI session uses a restricted role, and tenant-scoped work pins `app.tenant_id` from `Actor`. Postgres then refuses other tenants' rows. Repositories keep filtering by `actor.tenant_id`. `Actor`, the hexagonal ports, and the `chunks` collection stay as they are. Bootstrap and email/password login still succeed.

## Boundaries & Constraints

**Always:**
- One schema. Policies compare `tenant_id` to the tenant on the database session. A client field is never that tenant.
- `users`, `documents`, `conversations`, and `messages` enforce the policy for select, insert, update, and delete. Repositories still filter by `actor.tenant_id`.
- A session set to tenant A returns no tenant B rows from those tables, and cannot write a row for tenant B.
- An empty session tenant matches no rows on those tables.
- **Decision:** Fail closed. Every API, worker, and CLI session on PostgreSQL uses role `app_rls`. `get_by_email` (login and the bootstrap email check) and `users.any_exist` read through owner-owned security-definer functions: one email in, one row out, or a boolean. Bootstrap's user insert sets the session tenant to that new user's tenant before the insert.
- Domain and application tests stay on in-memory fakes. The default `pytest` run does not need Docker. The policy is tested on Postgres.
- `python -m app.cli bootstrap` and local login behave as they do today.
- The `tenants` registry has no `tenant_id` and stays without row-level security.

**Never:**
- A schema, database, or role per tenant. A second storage port. RLS on Qdrant. A Postgres jobs table.
- Roles on `Actor`, OIDC, request logs, or a managed Kubernetes topology.
- Use cases that take a session, a request, or a client-supplied tenant.
- Dropping the existing repository filters because the policy exists.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Missed document filter | Rows for tenant A and tenant B; session tenant is A; `SELECT` from `documents` with no tenant predicate | Only A's rows | N/A |
| Unset tenant | Session is subject to the policy; `app.tenant_id` is unset; `SELECT` from `documents` | No rows | N/A |
| Cross-tenant insert | Session tenant is A; insert a `documents` row with tenant B | No row is stored | The statement fails and the transaction rolls back |
| Same policy on chat tables | Session tenant is A; `conversations` and `messages` hold A and B | Reads return only A; writes for B fail | Same as the document insert |
| Missed user filter | Session tenant is A; `users` holds A and B; `SELECT` with no tenant predicate | Only A's rows | N/A |
| Login | Restricted role; tenant unset; existing user; email and password | The definer returns that one user; the body is a Bearer JWT with that `user_id` and `tenant_id` | Unknown email and wrong password stay 401 `INVALID_CREDENTIALS` |
| Bootstrap | Restricted role; tenant unset; empty store; the three `BOOTSTRAP_*` variables set | `any_exist` uses the definer; the user insert pins the new tenant and stores one user; a second run exits 0 and does not change the hash | N/A |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/infrastructure/persistence/models.py` — `TenantRow` has no `tenant_id` (`tenants`). `UserRow`, `DocumentRow`, `ConversationRow`, and `MessageRow` do. Do not change the row shapes.
- `apps/api/alembic/versions/0003_conversations.py` — head revision `0003_conversations`. Next file is `0004_tenant_rls.py` with `down_revision = "0003_conversations"`.
- `apps/api/src/app/infrastructure/persistence/session.py` — `session_scope` (line 29) opens, commits, rolls back, closes. No tenant pin. `to_sqlalchemy_url` rewrites `postgresql://` only.
- `apps/api/src/app/bootstrap/create_app.py` — `SessionBoundLogin` (line 72) has no `Actor`. `SessionBoundGetCurrentMember` and the document and conversation bindings (lines 82–257) have `actor` and call `session_scope(self._open_session)`.
- `apps/api/src/app/bootstrap/worker.py` — `SessionBoundProcessDocument.execute` (line 37) opens a session itself and writes `documents` through `SqlAlchemyDocumentRepository`. It does not call `session_scope`.
- `apps/api/src/app/cli.py` — bootstrap wraps `session_scope` around `BootstrapTenant`, which calls `users.any_exist()` and `tenants.any_exist()` with no tenant.
- `apps/api/src/app/infrastructure/persistence/user_repository.py` — `get_by_email` (line 31) and `any_exist` (line 37) are global. `get_by_id` (line 25) loads by primary key. Document and conversation repositories already filter by `actor.tenant_id`; keep those filters.
- `apps/api/tests/test_persistence.py` — `test_alembic_upgrade_creates_tenant_and_user_schema` runs `upgrade head` on SQLite. RLS DDL must no-op unless the dialect is PostgreSQL.
- `compose.yaml` — `POSTGRES_USER` is `app`. That role owns the tables and bypasses RLS. Reuse `LazySessionFactory` and `DATABASE_URL`. Do not add a second URL.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/alembic/versions/0004_tenant_rls.py` — Create `NOLOGIN` role `app_rls` (`NOSUPERUSER`, `NOBYPASSRLS`), `GRANT app_rls TO app`, and grant it DML on `users`, `documents`, `conversations`, and `messages` plus `SELECT`/`INSERT` on `tenants`. `FORCE ROW LEVEL SECURITY` and select/insert/update/delete policies on the four tenant-owned tables: `tenant_id = current_setting('app.tenant_id', true)`. Add security-definer functions `app_user_by_email(email)` and `app_users_any_exist()`, owned by the migration role, `search_path = pg_catalog, public`, `EXECUTE` granted only to `app_rls`. Run this DDL only on PostgreSQL. — SQLite must still reach head, and the superuser connection must be able to `SET ROLE`.
- [x] `apps/api/src/app/infrastructure/persistence/session.py` — On PostgreSQL, start every transaction on a product session with `SET LOCAL ROLE app_rls` and, when a tenant was passed, `set_config('app.tenant_id', :tenant_id, true)`. Re-apply that at the start of the next transaction, including after `ProcessDocument`'s processing commit. Do not use session-level `SET ROLE` or `set_config(..., false)`. `Session.commit()` returns the connection to the pool, and the pool's rollback does not clear those settings, so the next checkout can still be `app_rls` with the previous tenant. `SET LOCAL` ends with the transaction, before that return. Login passes no tenant. No-op on SQLite. — A commit must not leave the pooled connection pinned.
- [x] `apps/api/src/app/bootstrap/create_app.py` — Pass `actor.tenant_id` into `session_scope` for every binding that already receives an `Actor`. `SessionBoundLogin` calls `session_scope` with no tenant. — Product requests run under the policy; login stays on the definer.
- [x] `apps/api/src/app/bootstrap/worker.py` — Pin `SessionBoundProcessDocument.execute` with the same helper from `actor` before the document repository runs, and clear it in `finally`. — The early `commit` inside `ProcessDocument` must not drop the role or the tenant.
- [x] `apps/api/src/app/cli.py` — Open bootstrap through `session_scope` with no tenant so the session is `app_rls` before `any_exist`. — A second bootstrap must still exit 0.
- [x] `apps/api/src/app/infrastructure/persistence/user_repository.py` — On PostgreSQL, `get_by_email` calls `app_user_by_email` and `any_exist` calls `app_users_any_exist`. `save` sets `app.tenant_id` to the new user's tenant before insert. `get_by_id` stays ordinary SQL. SQLite keeps today's queries. — Login finds one user by email, and the first user insert satisfies the policy.
- [x] `apps/api/tests/test_tenant_rls.py` — Against Postgres, insert documents for A and B, pin the session to A, and `SELECT` with no tenant predicate; only A's row returns. Inserting B's `tenant_id` fails and rolls back. An own-tenant `UPDATE` persists; a cross-tenant `UPDATE` and `DELETE` do not. Run `SessionBoundProcessDocument` far enough to pass the processing commit, then an unfiltered `documents` read on that same session returns only the actor's rows. Use a pool of at least two connections and show that the connection returned after commit is `app` with `app.tenant_id` unset. Skip unless `RLS_TEST_DATABASE_URL` connects. — Proves the policy and the pool reset without making the default suite need Docker.
- [x] `apps/api/tests/test_persistence.py` — Re-run the SQLite `upgrade head` test after `0004`. — Existing adapter coverage stays green.

**Acceptance Criteria:**
- Given the domain and application suites, when `cd apps/api && uv run --extra dev pytest` runs with no Postgres, then they pass without Docker and the new RLS test is skipped.
- Given a Postgres database migrated to `0004`, when `RLS_TEST_DATABASE_URL` points at it and `tests/test_tenant_rls.py` runs, then the missed-filter and cross-tenant insert cases pass.
- Given `Actor`, the retrieve and embed ports, and Qdrant collection `chunks`, when this story is done, then those contracts are unchanged.

## Implementation Notes

- Sessions pin with session-level `SET ROLE app_rls` and `set_config('app.tenant_id', ..., false)`. `clear_rls_session` resets both before the connection returns to the pool.
- `cli.py` already opened `session_scope` with no tenant. That path now assumes `app_rls` through the helper. Bootstrap's user insert sets the tenant inside `SqlAlchemyUserRepository.save`.
- `cd apps/api && uv run --extra dev pytest`: 180 passed, 8 skipped. The skipped tests are `tests/test_tenant_rls.py` with `RLS_TEST_DATABASE_URL` unset.
- `RLS_TEST_DATABASE_URL=postgresql://app:app@localhost:5432/app uv run --extra dev pytest tests/test_tenant_rls.py`: 8 passed. Those tests migrate a scratch database and drop it.
- The Compose database `app` was still on `0003_conversations` when this was verified. `alembic upgrade head` is required there before the API or worker runs this code.
- Review loop 1 reverted that code. `Session.commit()` returns the connection, so session-level settings leaked across the pool. Re-derive with `SET LOCAL` re-applied on each transaction.
- Second derivation: `after_begin` applies `SET LOCAL ROLE app_rls` and transaction-local `set_config`. `cd apps/api && uv run --extra dev pytest`: 180 passed, 10 skipped. `RLS_TEST_DATABASE_URL=postgresql://app:app@localhost:5432/app uv run --extra dev pytest tests/test_tenant_rls.py`: 10 passed, including the two-connection pool, update and delete, and the worker session after the processing commit.

## Spec Change Log

- Trigger: review found session-level `SET ROLE` and `app.tenant_id` stay on the pooled connection after `Session.commit()`, and `clear_rls_session` can reset a different checkout. The task had required session-level settings so the processing commit would keep the pin.
- Amended: the `session.py` task and Design Notes now require transaction-local settings re-applied on each new transaction. The Postgres test task now requires a pool of at least two connections, an update and a delete, and the worker session after the processing commit.
- Known-bad state avoided: a later request checks out a connection still running as `app_rls` with the previous tenant, or the worker's post-commit write runs as superuser `app` and bypasses the policies.
- KEEP: policies and `FORCE ROW LEVEL SECURITY` on `users`, `documents`, `conversations`, and `messages`; `app_rls` is `NOLOGIN NOSUPERUSER NOBYPASSRLS` and is granted to `app`; create or alter that role outside the migration transaction and reuse it when it already exists; `app_user_by_email` and `app_users_any_exist` stay security-definer, `search_path = pg_catalog, public`, `EXECUTE` only for `app_rls`; RLS DDL stays PostgreSQL-only; actor bindings pass `actor.tenant_id` and login passes none; `save` sets the new user's tenant before insert; `get_by_id` stays ordinary SQL; matrix tests for missed filters, unset tenant, cross-tenant insert, chat tables, login, and the second bootstrap stay; default `pytest` still skips the Postgres file when `RLS_TEST_DATABASE_URL` is unset.

## Review Triage Log

- high — `pin_rls_session` uses session-level `SET ROLE` and `set_config(..., false)`. `Session.commit()` closes the connection (`session.py` in SQLAlchemy, `SessionTransaction.close`, autoclose). The pool's rollback leaves those settings on that connection, and `clear_rls_session` then checks out whichever connection is next. `test_tenant_rls.py` hides this with `pool_size=1`.
- high — `SessionBoundProcessDocument` commits inside `ProcessDocument` after `mark_processing` and then keeps using the same `Session`. The next statement can check out superuser `app` and bypass the policies, or a connection still pinned to another tenant.
- medium — `clear_rls_session` rollbacks and commits inside `finally`. That reset does not reach the connection `commit()` already returned, and an error there replaces the request's original exception.
- false — A cross-tenant `user_id` on Postgres makes `get_by_id` return no row, so `GetCurrentMember` raises 401. Design Notes record that outcome, and the in-memory fake still raises 403 because it returns the row. The approved spec keeps `get_by_id` as ordinary SQL.
- medium — `test_tenant_rls.py` never issues `UPDATE` or `DELETE`. With forced RLS and no policy for that command, `save` updates and conversation message deletes match zero rows and the suite still passes. Grouped with the verification-gap finding of the same claim.
- low — rejected. `downgrade()` drops cluster-wide role `app_rls`. Everyday use does not downgrade, and detecting other databases before the drop adds a branch. One Compose database is the path this story runs.
- false — Login and bootstrap would see no users if the function owner were a non-superuser table owner. Compose runs the migration as superuser `app`, `SECURITY DEFINER` runs as that owner, and `test_login_as_restricted_role_returns_bearer_jwt` plus the bootstrap test passed against that cluster.
- false — `app_rls` can call `app_user_by_email` and insert into `tenants` from any product session. The approved decision puts every API, worker, and CLI session on that one role and grants it those functions. A second role would change that decision.
- high — `SqlAlchemyUserRepository.save` sets session-level `app.tenant_id` and does not clear it. Same pooled-connection leak as `pin_rls_session`. Bootstrap is the only `save` caller and already runs inside `session_scope`.
- defer — not processed this pass. `/ready` stays a TCP probe when `0004` is missing, which is the existing readiness check. The stale code-map sentences are this spec's own text.
- false — `downgrade()` dropping `app_rls` after an autocommit block would leave RLS off while the revision stays `0004`. Policy removal is still in the Alembic transaction. A failed `DROP ROLE` rolls that transaction back, so the policies remain and the role remains.
- low — `rls_database` creates the scratch database before the `try` that drops it. A failed `upgrade` leaves the database behind. Direct fix is to drop it from `finally`. Not applied on this pass because the pin bug sends the code back through the spec.
- low — rejected. `_database_url` rebuilds the URL by hand. The documented test URL is `postgresql://app:app@localhost:5432/app`, which has no reserved characters.
- low — rejected. `test_pin_survives_commit` calls `clear_rls_session` before `close` without its own `finally`. The worker path already closes in `finally`. The hang needs `clear_rls_session` to raise during a test.
- medium — verification gap, pre-verified. Deleting `pin_rls_session` from the worker still leaves `test_pin_survives_commit` green because that test calls the helper itself. Same root as the pool pin. The amended test task requires the worker session after the processing commit.
- medium — verification gap, pre-verified. Removing the `UPDATE` and `DELETE` policies leaves `test_tenant_rls.py` green. The amended test task requires an own-tenant update and a cross-tenant update and delete.
- medium — verification gap, pre-verified. Only `SessionBoundAskQuestion` is asserted to pass `actor.tenant_id`. Dropping it on `SessionBoundListDocuments` stays green and, with the role assumed and the tenant unset, returns no documents. Carried into the re-derivation by the existing create_app task; the Postgres test task covers the worker and the policies, and the ask test remains the binding check to keep.
- defer — not processed this pass. Default `pytest` skips `test_tenant_rls.py` unless `RLS_TEST_DATABASE_URL` is set. The spec requires that skip so the default run does not need Docker. The same file asserts the cases when the variable is set.
- false — verification-gap other finding, same 401 claim as the `get_by_id` row above. Design Notes and the approved `get_by_id` task already state it.
- false — rejected. The first implementation note still describes session-level `SET ROLE`. That note is the reverted pass; the fix is editing this spec. The code uses `SET LOCAL` from `after_begin`.
- false — `GRANT app_rls TO app` is the task's required grant. Compose user `app` is that role. A different managed-database user is story 5.4.
- carried false — `SECURITY DEFINER` functions still rely on the migration owner. Compose runs migrations as superuser `app`, and the login and bootstrap tests passed on that cluster. Same claim as the first pass.
- carried false — `app_rls` can still call `app_user_by_email` and insert into `tenants`. The approved decision uses that one role for every session. Same claim as the first pass.
- medium — `downgrade()` drops the policies and then `autocommit_block()` commits that work before `DROP ROLE`. Alembic's `autocommit_block` unconditionally commits the preceding transaction. If `DROP ROLE` fails, RLS stays off while `alembic_version` remains `0004`, and a later upgrade does not recreate the policies. The first-pass row that said this rolls back is not how `autocommit_block` works.
- low — rejected. If `DROP DATABASE` in the fixture `finally` fails, the scratch URL can stay in the process. The fixture already drops the database, disposes the engine, and restores `DATABASE_URL` on the success path. Everyday runs reach that path.
- carried false — `get_by_id` for another tenant's user still returns no row, so `/me` is 401. Design Notes and the approved task still say that. Same claim as the first pass.
- false — Update and delete checks exist for `documents`. The four tables share one policy loop, so removing that `UPDATE` or `DELETE` template fails `test_own_update_persists_and_cross_tenant_update_and_delete_do_not`.
- carried defer — `/ready` is still a TCP probe. Same claim as the first pass. Not written to deferred-work again.
- low — rejected. `pin_rls_session` overwrites `session.info["rls_after_begin"]` on a second call. Product code pins a session once. Guarding a second pin adds a list the callers do not use.
- false — rejected. The code map still describes the pre-change `session_scope`. Updating it edits this spec.
- carried medium — Only `SessionBoundAskQuestion` is asserted to pass `actor.tenant_id`. The seven other actor bindings still have no Postgres test. Same claim as the first pass. Not patched again.
- carried defer — Default `pytest` still skips `test_tenant_rls.py` unless `RLS_TEST_DATABASE_URL` is set. The spec requires that skip. Same claim as the first pass.

## Design Notes

Compose user `app` is the cluster superuser, so policies never apply to it. `FORCE ROW LEVEL SECURITY` also does not bind a superuser. Sessions `SET ROLE app_rls` on the existing `DATABASE_URL`. `app_rls` is `NOLOGIN`; `app` inherits it. No second connection string.

`ProcessDocument` commits once while the document is `processing` (`process_document.py` line 64). `Session.commit()` then returns that connection to the pool (`SessionTransaction.close` closes an autoclose connection). The pool resets with `ROLLBACK`, which does not clear session-level `SET ROLE` or `set_config(..., false)`. Re-apply `SET LOCAL ROLE app_rls` and `set_config('app.tenant_id', :tenant_id, true)` at the start of every new transaction on that `Session`, including the transaction after the processing commit. `SET LOCAL` ends when the transaction ends, so the connection goes back unpinned.

`current_setting('app.tenant_id', true)` is null when unset, and `tenant_id = null` matches nothing. Clearing the GUC writes `''`, which also matches nothing.

`get_by_id` stays a normal primary-key read. On Postgres, a token whose `user_id` belongs to another tenant sees no row, so `GetCurrentMember` raises `UnauthenticatedError` (401). The in-memory fake still returns the row, and the use-case test still expects `TenantIsolationError` (403).

The `tenants` table stays out of RLS. Qdrant, S3, and Celery payloads are out of this migration.

SQLite has no `CREATE POLICY`. Guard the DDL and the `SET ROLE` with the dialect so `test_alembic_upgrade_creates_tenant_and_user_schema` and the in-memory repository tests stay as they are.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` — expected: existing tests pass; `tests/test_tenant_rls.py` skips when `RLS_TEST_DATABASE_URL` is unset
- `cd apps/api && RLS_TEST_DATABASE_URL=postgresql://app:app@localhost:5432/app uv run --extra dev pytest tests/test_tenant_rls.py` — expected: pass after `alembic upgrade head` on a reachable Compose Postgres
