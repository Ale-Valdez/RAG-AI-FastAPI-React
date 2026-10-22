---
title: 'Open a cited PDF page'
type: 'feature'
created: '2026-10-22'
status: 'done'
baseline_commit: '4e5bad86f0276b4b2bac177c8b451d75c157491f'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A citation names a document and a page, but the browser cannot read the stored PDF. The source panel only shows the filename and the page number.

**Approach:** Add an authenticated read of that document's bytes for the caller's tenant. The panel fetches those bytes with the existing bearer token and shows them in an iframe opened on the cited page.

## Boundaries & Constraints

**Always:**
- `tenant_id` comes from the authenticated actor. The route accepts neither a tenant id nor a filename.
- A missing row, another tenant's row, and an owned row with no object all raise `NotFoundError` (`document not found`). Do not return 403.
- Any status the tenant owns can be read. The bytes were stored at upload.
- Success is the raw PDF (`application/pdf`, `Content-Disposition: inline`, stored filename with quotes and line breaks removed). Errors stay on the JSON envelope.
- The iframe page is the stored page plus one. The stored field stays 0-based.
- The open panel is tall enough to read a page. Below `lg` it shares height with the thread and is not capped at `max-h-48`.
- Reuse `DocumentBytes.get` and the bearer client. No new npm package.

**Never:**
- No migration, object-key change, or change to upload, delete, reingest, chat, or citation selection.
- Do not wrap the file body in the JSON success envelope.
- Do not take the filename from the client.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Owned file | `GET /api/v1/documents/{id}/file` with bearer | 200, body equals stored bytes, `application/pdf` | N/A |
| Unknown id or other tenant | bearer | 404 `NOT_FOUND`, `document not found` | existing handler |
| Missing object | owned row, bytes port raises `KeyError` | 404 `NOT_FOUND`, `document not found` | use case translates |
| No token | no bearer | 401 | existing auth dependency |
| Panel loads | click a citation | iframe `src` is the blob URL plus `#page=` and the 1-based page; revoke the previous blob URL when the source changes or the panel closes | N/A |
| Panel fails | file request 404s | panel shows the API error message and no iframe | N/A |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/domain/ports/documents.py` — `DocumentBytes.get` already returns bytes. Do not change the port.
- `apps/api/src/app/application/documents/delete_document.py` — copy its tenant check.
- `apps/api/src/app/infrastructure/storage/s3_document_bytes.py` — translate a missing object to `KeyError`. `InMemoryDocumentBytes.get` in `apps/api/tests/fakes.py` already does. Do not change the fake.
- `apps/api/src/app/infrastructure/http/documents_router.py` — add the GET beside delete and reingest. `require_actor` already exists.
- `apps/api/src/app/infrastructure/http/error_handlers.py` — 404 envelope already exists. Do not change it.
- `apps/api/src/app/bootstrap/create_app.py` — follow `SessionBoundDeleteDocument` and the optional `create_app` argument. Repository and bytes store only.
- `apps/api/tests/test_documents_http.py`, `test_conversations_http.py`, `test_oidc_http.py` — each passes all four document use cases. Pass the new one too, or a `None` argument builds the S3 default. Leave `test_access_log.py`.
- `apps/web/src/api/client.ts` — `apiData` parses JSON. Add a bytes fetch that reuses the bearer token and the 401 handler.
- `apps/web/src/features/chat/components/sourcePanel.tsx` — load the PDF here. `sourcePageLabel` already adds one.
- `apps/web/src/features/chat/ChatPage.tsx` — the open panel's grid row is `auto` and the panel uses `max-h-48`. Give it a readable height.
- `apps/web/src/features/chat/components/messageThread.tsx` — citation buttons already set `ActiveSource`. Do not change them.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/application/documents/get_document_file.py` -- `Actor` plus `document_id` returns filename and bytes; missing row, other tenant, and `KeyError` become `NotFoundError`
- [x] `apps/api/src/app/infrastructure/storage/s3_document_bytes.py` -- map a missing object to `KeyError`
- [x] `apps/api/src/app/infrastructure/http/documents_router.py` -- GET returns raw `application/pdf` with an inline disposition
- [x] `apps/api/src/app/bootstrap/create_app.py` -- wire the session-bound use case through the optional argument and `_default_documents`
- [x] `apps/api/tests/test_get_document_file.py` -- in-memory fakes for owned bytes, another tenant, and a missing object
- [x] `apps/api/tests/test_documents_http.py` -- 200, unknown id, other tenant, and no token
- [x] `apps/api/tests/test_conversations_http.py` and `apps/api/tests/test_oidc_http.py` -- pass the new use case into `create_app`
- [x] `apps/web/src/api/client.ts` and `apps/web/src/features/chat/api.ts` -- fetch the file as a `Blob` with the bearer token
- [x] `apps/web/src/features/chat/components/sourcePanel.tsx` and `apps/web/src/features/chat/ChatPage.tsx` -- iframe on `#page=`, revoke the blob URL, show loading and the API error, readable panel height

**Acceptance Criteria:**
- Given a citation, when the user clicks its page, then the panel shows that PDF opened on the displayed page number.
- Given the panel is open, when the user clicks another page or closes the panel, then the previous blob URL is revoked.
- Given the user switches conversation, then the panel still closes.

## Implementation Notes

- `GetDocumentFile` follows the delete tenant check and maps `KeyError` to `NotFoundError`. `S3DocumentBytes.get` turns a missing object into `KeyError`.
- The file route returns raw PDF bytes. Call sites that passed every document use case now also pass `GetDocumentFile`, so they do not build the S3 default.
- The panel fetches with `apiBytes`, shows `{blobUrl}#page={sourcePageLabel}`, and revokes the object URL when the source changes or the panel unmounts.
- Verified: `uv run pytest tests/test_get_document_file.py tests/test_documents_http.py tests/test_conversations_http.py tests/test_oidc_http.py tests/test_document_adapters.py` from `apps/api` — 80 passed. The citation click was not exercised in a browser. `apps/web` has no test runner, so the two panel matrix rows are covered by the component, not by a test.

## Spec Change Log

## Review Triage Log

- medium — `documents_router.py` `_inline_disposition` — a stored name outside latin-1 makes Starlette raise `UnicodeEncodeError`, and the file route returns 500. Upload allows those characters. Patch: keep the header latin-1 safe.
- low — rejected — a name that is only quotes and line breaks becomes `filename=""`. The spec requires those characters to be stripped, the body is still the PDF, and that filename is not an everyday upload.
- low — rejected — `SessionBoundGetDocumentFile` reads the object inside the database session. Upload already caps the size, delete uses the same session shape, and splitting the read out is more than a direct correction. The PDF still returns.
- false — other `ClientError` codes stay 500. `NoSuchKey`, `404`, and `NotFound` are already mapped to `KeyError`. A different code is not a missing object. The missing tests for `404` and `NotFound` are the verification-gap rows below.
- false — a success payload with no `Body` is not what `get_object` returns. `KeyError` on this path is the missing-object translation and the in-memory fake.
- medium — `sourcePanel.tsx` iframe — the first paint after a new citation still uses the previous `fileUrl` and error, because the iframe only checks `fileUrl`. Patch: show the iframe and the error only when `loadedId` matches the citation, and keep the loading state until that match has a URL or an error.
- false — changing page revokes and rebuilds the blob URL. The acceptance criteria require that revoke when another page is clicked.
- low — rejected — closing the panel does not abort the download. The `cancelled` flag drops the result. An abort controller is extra machinery the user does not see.
- false — every HTTP 200 becomes an iframe. This route's 200 body is the stored PDF with `application/pdf`, and the panel calls only that route.
- low — defer — the large-screen column stays `minmax(16rem,22rem)` and has no zoom control. That column predates this story. This story removes the `max-h-48` cap and shares height, which is what the spec required.
- false — below `lg` the open panel has no extra minimum height. Its grid row is `minmax(0,1fr)`, so it shares the thread height instead of staying at `max-h-48`.
- low — rejected — the file route has no invalid-bearer test. It uses the same `require_actor` as `test_delete_and_reingest_reject_invalid_bearer`.
- medium — `documents_router.py` latin-1, edge-case hunter — same 500 as the first row. Grouped with that patch.
- medium — `sourcePanel.tsx` citation flash, edge-case hunter — same stale paint as the iframe row. Grouped with that patch.
- medium — verification gap, pre-verified — codes `404` and `NotFound` are mapped but only `NoSuchKey` is tested. Removing them would ship a missing object as 500. Patch the adapter test.
- medium — verification gap, pre-verified — a non-missing `ClientError` such as `AccessDenied` is re-raised, and no test locks that. Patch the adapter test.
- medium — verification gap, pre-verified — defer. The panel's `#page=`, failure text, and blob revoke have no web test. `apps/web` has no test runner, and this spec assigns that click to a manual check.
- low — verification gap, pre-verified — defer. Nothing asserts the open panel row is `minmax(0,1fr)` or that `max-h-48` is gone. The classes are in the diff. Same missing web runner.
- low — verification gap, pre-verified — defer. Nothing asserts `apiBytes` calls `onUnauthorized` on 401. The client does call `rejectResponse`, which does. Same missing web runner.

## Design Notes

`pypdf_extractor.py` stores pages from `enumerate`, so they start at 0. The iframe uses the same label as the button: `{blobUrl}#page={sourcePageLabel(source.page)}`.

## Verification

**Commands:**
- `uv run pytest tests/test_get_document_file.py tests/test_documents_http.py tests/test_conversations_http.py tests/test_oidc_http.py` from `apps/api` -- expected: all passed

**Manual checks (if no CLI):**
- Click a citation. The panel shows the PDF on the button's page. Closing the panel or switching threads removes it. `apps/web` has no test runner. Do not edit `Header.tsx`.
