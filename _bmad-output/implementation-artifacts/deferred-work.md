- source_spec: '{project-root}/_bmad-output/implementation-artifacts/spec-1-1-bootstrap-a-tenant-and-sign-in.md'
  summary: Web sign-in screen that keeps the Bearer token in memory and sends it on product API calls.
  evidence: Split from story 1-1 so this spec stays on bootstrap, login, Actor, and the /api/v1 envelope. The screen depends on those routes and was the secondary shippable piece.

## Deferred from: code review of spec-1-1-bootstrap-a-tenant-and-sign-in (2026-09-21)

- `http-envelope.md` does not list `VALIDATION_ERROR`. Product handlers return that code on 422. Updating the shared envelope spec is outside this story's code.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-fix-ingestion-status-commit.md`
  summary: If the worker crashes after the early processing commit, the row stays processing and a later run skips it.
  evidence: ProcessDocument only ingests pending rows, and the Celery task retries only a deferred outcome. A raised error after mark_processing, including a failed final commit, leaves the concurrency slot occupied.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-3-1-find-ready-chunks-for-a-question.md`
  summary: Chunk point identity is `document_id` plus `chunk_index`, so two tenants cannot both keep that same pair.
  evidence: `chunk_point_id` and the in-memory upsert key predate retrieval. Search filters by tenant, but a later upsert with the same id overwrites the earlier point. Real document ids are distinct, so this story's tenant filter is not what removes the other tenant's chunk.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-5-2-sign-in-with-an-identity-provider.md`
  summary: `GET /api/v1/me` is 403 in memory and 401 on Postgres when the token's user exists under a different tenant.
  evidence: `GetCurrentMember` calls `assert_same_tenant` when the row is returned. Story 5.1 already records that Postgres row-level security hides that row, so `get_by_id` returns nothing and the route is 401. The in-memory fake still returns the row. This story does not change that lookup.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-web-login-documents-and-chat.md`
  summary: Chat shows the API page index, so the first PDF page appears as page 0.
  evidence: `PypdfTextExtractor` stores `enumerate` from 0 and the web prints `source.page`. This story shows that field and does not change the API.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-web-login-documents-and-chat.md`
  summary: A blank `VITE_API_PROXY_TARGET` is used as the Vite proxy target.
  evidence: `??` only replaces nullish values. The previous `process.env` line behaved the same way, so this is pre-existing.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-web-login-documents-and-chat.md`
  summary: Guest redirects, session clear on 401, the Bearer envelope, the ready-document rule, document polling, refresh logout, and health cache mode have no automated test.
  evidence: The web spec forbids a test runner. The human chose to accept the production build and manual checks instead.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-web-router-and-layout.md`
  summary: A 401 that arrives after the user leaves Documents or Chat does not open `/login`.
  evidence: `onUnauthorized` only clears the in-memory token. `RequireAuth` is mounted on those two routes, so a 401 while `/health` is open leaves the signed-out shell on `/health`. The same wrappers existed before this router move. The earlier web spec says any `/api/v1` 401 opens `/login`.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-web-tailwind.md`
  summary: The web image installs from `package.json` only, so the lockfile hashes are not used at image build time.
  evidence: `apps/web/Dockerfile` copies `package.json` and runs `npm install` before `COPY . .`. That order predates Tailwind. Direct dependencies stay on the exact versions in `package.json`.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-web-tailwind.md`
  summary: The Compose `web_node_modules` volume does not install packages when `package.json` changes.
  evidence: The volume is filled from the image only while empty. This install was applied with `docker compose exec web npm install`. A later dependency still needs that command, or a new volume, before Vite can import it.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-persist-web-session.md`
  summary: Reload, sign-out, a 401, and startup `/me` have no in-repo test.
  evidence: The frozen spec forbids a web test runner, and `apps/web` has none. `npm run build` typechecks and bundles only. A headless Chrome script outside the repo passed those rows once.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-persist-web-session.md`
  summary: `apps/web/package-lock.json` has no integrity hash for packages npm did not refetch, including `react`.
  evidence: The `react` lock entry has a version and no `resolved` or `integrity`. The lockfile was created by the Tailwind install. This story did not add it. The image still runs `npm install` from `package.json` only.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-persist-web-session.md`
  summary: Tailwind preflight still changes line height, box sizing, list markers, and the file button.
  evidence: `styles.css` restores headings, paragraph margins, and the Health underline only. It does not set `box-sizing`, `line-height`, or `::file-selector-button`. Those rules come from the Tailwind install, not from session restore.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-persist-web-session.md`
  summary: Product colors are not available as Tailwind theme tokens.
  evidence: The stylesheet has no `@theme` block. The Tailwind intent kept the existing hex rules and did not convert screens. This story does not add utility styling.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-chat-pdf-source-panel.md`
  summary: The source panel's page jump, failure text, and blob revoke have no automated test.
  evidence: `apps/web` has no test runner. The spec assigns the citation click to a manual check. A wrong `#page=` or a leaked blob URL would not fail the API suite.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-chat-pdf-source-panel.md`
  summary: Nothing asserts that an open source panel shares height and drops the `max-h-48` cap.
  evidence: The classes are in `ChatPage` and `sourcePanel`. `apps/web` has no test runner, so restoring the short cap would not fail a test.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-chat-pdf-source-panel.md`
  summary: A 401 from the PDF fetch has no test that the session is cleared.
  evidence: `apiBytes` calls `rejectResponse`, which calls `onUnauthorized`. `apps/web` has no test runner, so skipping that call would not fail a test.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-chat-pdf-source-panel.md`
  summary: On a large screen the PDF stays in a column at most 22rem wide, with no zoom or download control.
  evidence: That column width predates this story. The spec required a readable height, which the shared row provides. A wider viewer is a separate layout change.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: An extraction exception marks the document failed and does not log the error.
  evidence: `_ingest` catches `Exception` from `extract` and returns `_fail` with no log. The baseline `extract_pages` path did the same.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: A conversion that returns no pages would report `page_count` 0 and skip the page limit.
  evidence: `page_count` is `len(result.pages)`. Whether Docling leaves that list empty when `generate_parsed_pages=True` was not executed. A converter run that prints `len(result.pages)` for a blank PDF would settle it.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: The worker image may still install CUDA torch, and it may need `libgomp1` or RapidOCR weights that the model download does not fetch.
  evidence: The Dockerfile installs a CPU torch wheel and then `.[worker]` from PyPI. The image was not built. `pip show torch` and a one-page convert inside that image would settle it.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: Heading hierarchy options and `generate_parsed_pages` have no test.
  evidence: `_get_converter` sets them. The default suite must not import `docling` or convert a PDF. A test marked off that run, on the worker extra, would settle it.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: A partial Docling conversion can still be ingested.
  evidence: `_convert_pdf` returns `result.document` without reading `result.status`. Whether `convert()` raises or returns a partial document was not executed.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: A caption and table that together exceed 512 tokens might become separate chunks.
  evidence: The covered table keeps its caption because the caption is on the table item. A table whose markdown plus caption exceeds 512 tokens was not built.

- source_spec: `/home/ale/Escritorio/DEV/Own/AI-RAG/_bmad-output/implementation-artifacts/spec-docling-pdf-extraction-and-chunking.md`
  summary: A scanned page may be ingested with no text when no OCR engine is selected.
  evidence: Pipeline options do not set an OCR engine. OCR repair is out of scope. A scanned PDF through the worker converter would settle whether text is dropped.
