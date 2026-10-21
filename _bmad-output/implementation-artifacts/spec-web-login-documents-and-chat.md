---
title: 'Web login, documents, and chat'
type: 'feature'
created: '2026-10-21'
status: 'done'
route: 'dispatch'
baseline_commit: '97430d373a2f6198a236847d01ac35b7414dc3e4'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `apps/web` shows API health, but Documents and Chat are placeholders. Login, PDF storage, and answers already exist on the API and are unused in the browser.

**Approach:** One in-memory session and three screens: login, the tenant document library, and a conversation over that tenant's ready PDFs. The header shows email and `tenant_id` from `GET /api/v1/me`. The tenant comes only from the Bearer token.

## Boundaries & Constraints

**Always:**
- HTTP API only. Do not change `apps/api`.
- Token stays in memory. No `localStorage`, `sessionStorage`, or cookie. A 401 clears it and opens `/login`.
- `/api/v1` uses `{ data, error }` and `Authorization: Bearer`. Show `error.message`. `/api/health` and `/api/ready` stay raw and public.
- English copy. PDF upload only. Poll documents every 3 seconds while any row is `pending` or `processing`. Confirm before delete.
- Chat send is disabled until a document is `ready`. The filter lists only `ready` documents; the default omits `document_id`. The first question creates the thread and opens `/chat/:id`. Follow-ups append. Sources show filename and page.
- Documents are the tenant's. Conversations are that user's, newest first, as returned.

**Never:**
- Registration, tenant switcher, tenant name, or a `tenant_id` field.
- Logout request, new npm packages, a test runner, a UI framework, or OIDC.
- Fields the API does not return.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Login | Valid email and password | Token in memory, `/me` loaded, open `/documents` | N/A |
| Bad login | Wrong password | Stay on `/login` | `Invalid email or password` |
| Guest | No token on `/`, `/documents`, or `/chat` | Redirect to `/login` | N/A |
| Signed in | Token on `/` or `/login` | Redirect to `/documents` | N/A |
| Unknown path | Any other path | Same redirect as `/` | N/A |
| Upload | PDF | Row starts `pending`, then `ready` or `failed` via polling | API message for non-PDF or oversize |
| Empty library | No documents | Empty state; chat composer disabled | N/A |
| Delete | Confirmed | Row disappears | API message on failure |
| Reingest | `ready` or `failed` | Back to `pending`; polling resumes | API message |
| New question | Ready docs and text on `/chat` | `POST /conversations`, then `/chat/:id` with sources | Blank text is not sent |
| Follow-up | Text on `/chat/:id` | Append user and assistant | 404 shows the API message |
| No ready docs | Question attempted | Composer disabled, with the reason | N/A |
| Scoped question | One ready document chosen | Send that `document_id` | N/A |
| Refusal | No matching chunks | API refusal sentence, no sources | N/A |
| Expired token | Any `/api/v1` 401 | Session cleared, `/login` | N/A |
| Health | `/health`, session or not | Existing probe panel | Existing error if the API is down |

</frozen-after-approval>

## Code Map

- `apps/web/src/api/client.ts` — keep raw `getJson` for health. Add a `/api/v1` helper: Bearer, unwrap `data`, `ApiError` carries `status`, `code`, `message`.
- `apps/web/src/features/health/*` — raw probes. Move the route to `/health`, off the product nav.
- `apps/web/src/App.tsx`, `main.tsx`, `shared/states.tsx`, `styles.css` — shell, guards, existing states, current look.
- `apps/api/.../auth_router.py` — `data.access_token`. `/me`: `user_id`, `tenant_id`, `email`. Bad login: 401 `INVALID_CREDENTIALS`.
- `apps/api/.../documents_router.py`, `upload_document.py` — list, multipart `file` (201), delete, reingest. Fields: `id`, `filename`, `status`. Non-PDF, bad name, or over 20 MB is 409.
- `apps/api/.../conversations_router.py`, `ask_question.py` — create 201, append 200, get, list `{ id, created_at }`. Body: `question`, optional `document_id`. Blank is 409. Unknown thread or scoped doc not `ready` is 404. No chunks: refusal text, no sources.
- `conversation_repository.py` `list_for_actor` — this tenant and user, newest first. `error_handlers.py`: 401, 403, 404, 409. Do not change API, worker, CLI, or deploy.

## Tasks & Acceptance

**Execution:**
- [x] `apps/web/src/api/client.ts` -- Bearer envelope client; keep raw `getJson` for health
- [x] `apps/web/src/auth/session.tsx` -- memory token, `/me`, login, logout, clear on 401
- [x] `apps/web/src/features/auth/LoginPage.tsx` -- email and password form
- [x] `apps/web/src/App.tsx` and `apps/web/src/main.tsx` -- provider, guards, and shell
- [x] `apps/web/src/features/documents/DocumentsPage.tsx` and `api.ts` -- list, upload, poll, delete, reingest
- [x] `apps/web/src/features/chat/ChatPage.tsx` and `api.ts` -- list, create, append, sources, ready-document filter
- [x] `apps/web/src/styles.css` -- shell, library, and thread layout
- [x] `apps/web/src/features/health/api.ts` -- stay on the raw helper

**Acceptance Criteria:**
- Given two bootstrapped tenants, when each signs in, then each sees only that tenant's documents and that user's conversations, and the header shows that tenant id.
- Given a refresh, when the page loads, then the token is gone and product routes open `/login`.

## Implementation Notes

- Session, login, documents, and chat are in `apps/web`. The API was not changed.
- A 401 clears the in-memory token. Protected routes then open `/login`. Logout does not call the API.
- Health stays on raw `getJson` at `/health`. A Health link sits outside the Documents/Chat nav.
- `apps/web/vite.config.ts` reads `VITE_API_PROXY_TARGET` from `globalThis` so `tsc` can check the config without `@types/node`.
- `npm --prefix apps/web run build` passed (`tsc --noEmit` and the Vite build).
- Matrix rows were checked in the browser against a stand-in API. A file over 20 MB was not uploaded; that failure uses the same API error path as a non-PDF.
- No automated web tests. The spec forbids a test runner. The human chose to continue to review with the build and the manual checks only.
- Review patches: a 401 clears the session only when the failed request used the current token; login writes that token back after `/me`; network sign-in errors use `apiErrorMessage`; `/chat/:id?` is one route and an in-flight send does not navigate or replace another thread; chat reloads documents every 3 seconds while none are ready; an empty library shows `loadError` and a mutation row stays in `documentsRef` so polling continues; nested states no longer draw a second card.
- `npm --prefix apps/web run build` passed again after those patches.

## Spec Change Log

## Review Triage Log

- medium — A late 401 clears the newer session. `onUnauthorized` always nulls `tokenRef`. Login sets that ref, awaits `/me`, then `setToken` without writing the ref again. A slower 401 from the previous token in that window leaves the UI signed in while `getToken()` is null.
- medium — Login shows "Invalid email or password" for a non-`ApiError`, including a network failure (`LoginPage` catch). A failed `/me` that is an `ApiError` already shows `reason.message`. Editable fields and a missing alert are secondary.
- medium — The first question remounts chat. `/chat` and `/chat/:id` are separate route elements, so `ChatPage` state is dropped. `onSend` discards the created messages and the new mount refetches. If that get fails, the answer is not on screen.
- medium — An in-flight send still applies after the user leaves. `appendMessage` then `setConversation` and `setQuestion("")` use the id from submit time, and the conversation list stays clickable. `navigate` after create runs even if the user opened Documents.
- medium — Chat loads documents once (`useEffect` with `[]`). Send stays disabled after a PDF becomes ready while the page stays open.
- medium — A failed reload of an empty library hides `loadError` (only the non-empty branch renders it). `documentsRef` updates only after a successful list, so a failed reload after upload does not schedule the next poll. No client-side size check is required: the spec shows the API message after the server rejects the file. A short stale status before a successful refetch is not a stuck row.
- low — Rejected. A chat load error has no retry button, the empty-thread sentence does not change when a document is ready, and Send stays enabled on a 404. Refresh and the API message cover those cases. A retry control or a disabled composer would add branches.
- medium — Source lines print `source.page`, and `pypdf` stores `enumerate` from 0, so the first page is "page 0". Deferred: the index is pre-existing in the API, and this story must show that field without changing the API.
- low — `.state` inside `.panel` draws a second card. Header and message text do not wrap long unbroken strings. The unlabeled tenant id is the id the spec asked to show.
- low — Rejected. Delete and Reingest names omit the filename, and errors are not alerts. That is screen-reader polish, not a broken action.
- low — Rejected. The thread does not scroll, Send keeps its label, same-second timestamps collide, and a blank composer is the Chat link. The spec's list label is the timestamp.
- low — `VITE_API_PROXY_TARGET=""` is used as the proxy target because `??` ignores only nullish values. Deferred: the previous `process.env` line behaved the same way.
- low — No automated test covers guest redirects, 401 session clear, the Bearer envelope, the ready-document send rule, document polling, refresh logout, or `cache: "no-store"` on health. Pre-verified. Deferred: the spec forbids a test runner and the human chose the build plus manual checks.

## Design Notes

The session module owns the token. Feature clients use the shared helper and never read storage. Health stays on `getJson` because those routes are not the `{ data, error }` envelope.

## Verification

**Commands:**
- `npm --prefix apps/web run build` -- expected: `tsc --noEmit` and the Vite build succeed

**Manual checks (if no CLI):**
- Sign in, upload a PDF, wait for `ready`, ask, see filename and page, follow up, then sign out.
- Refresh returns to `/login`. A second tenant's library and threads stay hidden.
