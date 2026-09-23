---
title: 'Fix ingestion status commit'
type: 'bugfix'
created: '2026-09-22'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After a PDF is embedded and written to Qdrant, the worker reports success but the document stays `processing`. The same gap leaves a failed ingest on `processing` instead of `failed`. Those rows keep occupying the per-tenant concurrency slots, so later uploads stay `pending`.

**Approach:** Commit the final `ready` or `failed` status on the success path of the worker session. Keep the early commit that publishes `processing` before extraction. Do not change document rows that are already stuck.

## Implementation Notes

- Decision: code fix only. Do not update or requeue the rows already left in `processing` or `pending`.
- `SessionBoundProcessDocument.execute` calls `session.commit()` in the `try` block after `ProcessDocument.execute` returns its outcome and before the Python `return`. An `else` clause does not run when `try` returns, which is why the previous final commit never happened. The early `processing` commit inside the use case is unchanged.
- Files: `apps/api/src/app/bootstrap/worker.py`, `apps/api/tests/test_document_adapters.py`.

## Review Triage Log

- `defer` — A commit or other exception after the early `processing` commit leaves the row `processing`; a later run returns `SKIPPED` and Celery retries only `DEFERRED`. Pre-existing crash window, not the missing success-path commit. Recorded in deferred-work.
- `false` — Existing stuck rows were left in place on purpose. Implementation Notes already say not to update or requeue them.
- `false` — `delete_by_document` raising inside `_ready` is the same pre-existing escape after the `processing` commit, grouped with the deferred item above.
- `false` — The session tests read status at `commit()` time. The bug was that the second commit never ran; they fail if it is skipped. They are not a SQLAlchemy flush test.
- `low` rejected — Call order of `rollback` and `close` is not asserted. Normal success already requires the second commit to observe `ready` or `failed`.
- `false` — Any `FAILED` return takes the same final commit. Extract failure is enough to prove that commit; later failure stages stay in the use-case tests.
- `low` patched — Implementation Notes now say the commit is inside `try` before `return`, because `else` does not run on `return`.
- `low` rejected — Duplicated test setup is not worth a shared helper for two tests.
