- source_spec: '{project-root}/_bmad-output/implementation-artifacts/spec-1-1-bootstrap-a-tenant-and-sign-in.md'
  summary: Web sign-in screen that keeps the Bearer token in memory and sends it on product API calls.
  evidence: Split from story 1-1 so this spec stays on bootstrap, login, Actor, and the /api/v1 envelope. The screen depends on those routes and was the secondary shippable piece.

## Deferred from: code review of spec-1-1-bootstrap-a-tenant-and-sign-in (2026-09-21)

- `http-envelope.md` does not list `VALIDATION_ERROR`. Product handlers return that code on 422. Updating the shared envelope spec is outside this story's code.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-fix-ingestion-status-commit.md`
  summary: If the worker crashes after the early processing commit, the row stays processing and a later run skips it.
  evidence: ProcessDocument only ingests pending rows, and the Celery task retries only a deferred outcome. A raised error after mark_processing, including a failed final commit, leaves the concurrency slot occupied.
