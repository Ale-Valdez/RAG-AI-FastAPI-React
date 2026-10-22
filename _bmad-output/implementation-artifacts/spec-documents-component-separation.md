---
title: 'Link documents upload and table'
type: 'refactor'
created: '2026-10-22'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `UploadComponent` and `DocumentsTableComponent` were split out of `DocumentsPage`, but upload keeps its own revision, in-flight id, and error. Those no longer share the page poll, the busy lock, or the visible action error. A successful upload does not restart the 3-second poll, and an upload failure is not shown.

**Approach:** One library coordinator owns the list, the poll revision, the single in-flight action, and the action error. Upload submits a file into that coordinator. The table runs reingest and delete through the same coordinator. Visible behavior stays the committed documents screen: PDF only, poll while any row is `pending` or `processing`, confirm before delete, one action error under the form, and busy disables upload and row actions together.

</frozen-after-approval>

## Implementation Notes

- `useDocumentLibrary` owns the list, `documentsRef`, poll revision, one in-flight action, and both errors. Upload, reingest, and delete all go through `run`, which sets the shared busy flag and bumps revision after a successful mutation so polling restarts.
- An in-flight ref blocks a second action before React re-renders `busy`. Upload clears the file input only when `upload` returns true.
- `documentStatus.ts` holds `isActive` and `canReingest`. The table and the hook share that rule; neither component imports the hook.
- `apps/web` has no test runner. `tsc --noEmit` reports no errors in the documents files. Pre-existing unused locals in `AppLayout.tsx` and `Header.tsx` are outside this change.
- Browser tools are not available in this session, so the upload → list → poll path was not clicked through in a browser.
- `replaceDocuments` increments a generation ref before React cleans up the previous list effect. A list response from an older generation does not write `documentsRef` or `documents`.

## Review Triage Log

- medium — stale `listDocuments` can overwrite a newer upload, reingest, or delete before effect cleanup sets `cancelled`. Patched: `generation` increments in `replaceDocuments`, and `load` applies a response only when that generation is still current.
- false — clearing busy before the follow-up list returns lets a second action run on a stale snapshot. `documentsRef` already holds the mutation, and `inFlight` blocks overlap. The stale overwrite was the generation bug above, not the busy flag. The committed page also cleared the in-flight id in `finally`.
- false — the upload form works while `documents === null` and a success shows only the new file. The previous `DocumentsPage` rendered the form above the loading line and prepended the created row the same way.
- false — a failed first load does not retry. The previous effect scheduled another poll only when `documentsRef` already had a `pending` or `processing` row. The frozen intent keeps that poll rule.
- false — list and mutation fetches have no timeout or `AbortSignal`. Those calls go through the existing `apiData` client, which the previous page used unchanged.
- false — a 401 on the first list leaves the loading line. `api/client.ts` calls `handleUnauthorized`, `session.tsx` clears the token, and `routes.tsx` sends a missing token to `/login`, which unmounts this page.
- low — rejected. Raw status text, no status union, and row buttons without the filename match the list markup moved out of the previous page. Adding labels would change the frozen screen.
- low — rejected. The submit label stays "Upload", and the action error is the same paragraph under the form. That is the committed screen.
- false — an empty list plus `loadError` shows both the error and the empty state. The previous page rendered both branches, and polling stays off when no row is active.
- false — `window.confirm` blocks the page. The frozen intent requires confirm before delete, and the previous handler used the same prompt.
- false — `uploadComponent.tsx` and `documentsTableComponent.tsx` are camelCase. Those are the file names the request named.
