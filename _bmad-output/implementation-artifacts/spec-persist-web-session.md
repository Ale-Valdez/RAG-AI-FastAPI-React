---
title: 'Persist the web session across reload'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
baseline_commit: '567dc9ca9da502b0ca4d466974bb011d2dfed2ea'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The signed-in Bearer token lives only in React state. A full page reload remounts the app with no token, and the route guards send the user back to `/login`.

**Approach:** Keep the same in-memory session, and also restore the access token from `sessionStorage` before the first route decision so a reload stays on the current product route. Logout and a 401 still end the session.

**Decision:** The access token lives in `sessionStorage`. A reload in that tab stays signed in. Closing the tab, or opening a new tab, starts signed out. Do not use `localStorage`.

## Boundaries & Constraints

**Always:**
- The API stays Bearer JWT. The web app sends `Authorization: Bearer` and never sends `tenant_id` as an auth filter. `tenant_id` still comes from `GET /api/v1/me`.
- Persist the access token only after login has loaded `/me` successfully, the same moment `setToken` runs today.
- Logout and a 401 for the current token clear the persisted token and the in-memory session.
- Store the access token in `sessionStorage` only. Read it synchronously before guards render, so a reload does not flash `/login` and then bounce back.
- A saved token that `/me` rejects with 401 is cleared and product routes open `/login`. A network failure on that startup `/me` keeps the token.

**Never:**
- Do not change login, `/me`, JWT expiry (15 days), or any API contract.
- Do not store the password, and do not add cookies, refresh, revocation, or `localStorage`.
- Do not add a web test runner. `apps/web` has none.
- Do not change route paths, `AppLayout`, or feature pages except where a guard must wait on the restored token.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reload while signed in | Valid token saved; user reloads `/documents` or `/chat` | Same route stays open; header fills email and tenant from `/me` | N/A |
| Reload signed out | No saved token | `/`, `/documents`, and `/chat` open `/login` | N/A |
| Sign out | User clicks Sign out | Token cleared; `/login`; a later reload still opens `/login` | N/A |
| Expired or rejected token | Saved token; startup `/me` returns 401 | Session cleared; product routes open `/login` | 401 only |
| API down on startup | Saved token; `/me` fails without 401 | User stays signed in; `me` stays empty until a later success | Keep the token |
| Login then reload | Fresh login succeeded | Reload does not open `/login` | Failed login stores nothing |
| New tab or closed tab | Token saved in the previous tab | The new tab has no token and product routes open `/login` | N/A |

</frozen-after-approval>

## Code Map

- `apps/web/src/auth/session.tsx` — `SessionProvider` (lines 27–75) holds `tokenRef` and `token` in memory. `login` (42–61) writes `setToken` only after `/me` succeeds. `logout` (63–67) and `onUnauthorized` (34–39) clear it. This is the only place that should read and write the saved token. Reuse `configureApi`, `login`, `logout`, and the 401 guard that ignores a stale token.
- `apps/web/src/routes.tsx` — `RequireAuth` (10–14), `GuestOnly` (16–20), and `HomeRedirect` (22–25) branch on `token`. Leave them if the token is already restored on the first render.
- `apps/web/src/api/client.ts` — `apiData` (50–84) sets `Authorization` from `readToken()` and calls `handleUnauthorized` on 401. Do not change the envelope or the header.
- `apps/web/src/main.tsx` — `SessionProvider` wraps the app. Do not move it.
- `apps/api/src/app/infrastructure/auth/jwt.py` — `ACCESS_TOKEN_TTL` is 15 days. Do not change it.
- `_bmad-output/planning-artifacts/architecture/architecture-AI-RAG-2026-09-18/ARCHITECTURE-SPINE.md` — AD-8 keeps the token out of `localStorage`. This spec uses `sessionStorage` for the same tab only.

## Tasks & Acceptance

**Execution:**
- [x] `apps/web/src/auth/session.tsx` -- restore the access token from `sessionStorage` before the first render, write it when login succeeds, and clear it on logout and on a 401 for the current token -- so reload no longer drops the session
- [x] `apps/web/src/auth/session.tsx` -- after a restored token, load `/me` and publish `me`; clear only on 401 -- so the header and a dead token behave as they do today

**Acceptance Criteria:**
- Given a successful sign-in, when the user reloads a product route, then that route stays open and `/login` does not replace it.
- Given Sign out or a 401 for the current token, when the user reloads, then product routes open `/login`.

## Implementation Notes

- `apps/web/src/auth/session.tsx` stores `ai-rag.access-token` in `sessionStorage`. The `useState` initializer reads it and sets `tokenRef` before guards render. Login writes the key only after `/me` succeeds. Logout and a 401 for the current token remove it. A restored token loads `/me` after first paint. A non-401 failure leaves the token and leaves `me` empty.
- `npm --prefix apps/web run build` passed (`tsc --noEmit` and Vite).
- A headless Chrome pass against Vite, with the API mocked, asserted every matrix row. Signed-out `/`, `/documents`, and `/chat` open `/login`. A saved token keeps `/documents` and `/chat`, sends `Authorization: Bearer`, and then shows email and tenant. Sign-out and a 401 stay on `/login` after another load. An aborted `/me` keeps the token and leaves `me` empty. A failed login stores nothing. A late `/me` after sign-out does not restore the session. A new tab starts signed out. Nothing was written to `localStorage`.
- No web test runner was added. The browser script is outside the repo.
- Review patch: `readStoredAccessToken`, `writeStoredAccessToken`, and `clearStoredAccessToken` swallow `sessionStorage` failures. A blocked read stays signed out. A blocked write or remove still updates the in-memory session on login, logout, and a 401.
- `npm --prefix apps/web run build` passed again after that patch. The same headless Chrome matrix passed again.

## Spec Change Log

## Review Triage Log

- low — Guest lede shows beside the signed-in nav until startup `/me` returns. Rejected: Design Notes require that call after first paint, and the matrix row is met when `/me` fills email and tenant. A loading flag would add session state and edit `AppLayout`, which this spec leaves alone.
- false — Startup `/me` never retries, so a non-401 leaves the header empty for the tab. The API-down row says to keep the token and leave `me` empty. The empty `catch` is that row. Login remains the path that publishes `me`.
- low — A rejected token mounts Documents or Chat until the 401, and `/health` does not redirect. Rejected: reading the token before the guards is required so a valid reload does not flash `/login`, and a 401 still clears it. The `/health` non-redirect is already deferred and is not met on an ordinary product reload. The fix would be a new pending gate.
- medium — `sessionStorage` `getItem` / `setItem` / `removeItem` can throw. A throw in the `useState` initializer blanks the app. A throw from `removeItem` after `tokenRef` is cleared skips `setToken`, so the UI stays signed in while later requests send no token. A throw from `setItem` after a successful login `/me` surfaces as a failed sign-in. Patch: swallow storage errors so read returns null and logout, 401, and login still update memory.
- false — Storing the token in `sessionStorage` breaks AD-8. The frozen decision requires `sessionStorage` and forbids `localStorage`. AD-8's sentence forbids `localStorage`. The code does not write it.
- low — The code map still cites the pre-change line numbers. Rejected: the fix is an edit to this spec.
- medium — No in-repo test covers restore, logout, 401, startup `/me`, or `sessionStorage` versus `localStorage`. `npm run build` still passes if those paths break. The acceptance list does not repeat the matrix because the template says not to duplicate it. Defer: the frozen spec forbids a web test runner.
- low — A duplicated tab copies `sessionStorage` and stays signed in. Rejected: a blank new tab starts signed out, which is the checked behavior of the chosen storage. Stopping a duplicate from copying the key is a different storage design, and duplicating a tab is not the everyday "new tab".
- medium — `apps/web/package-lock.json` has no `integrity` on `react` (and other packages npm did not refetch). Defer: the lockfile arrived with the Tailwind install, which this story did not create. The image still installs from `package.json` only.
- low — Tailwind preflight still sets `line-height`, `box-sizing`, list markers, and the file-button face. `styles.css` does not override those. Defer: that reset came with the Tailwind install, not with session restore.
- low — Product colors are not `@theme` tokens. Defer: the Tailwind intent kept the existing rules and did not convert screens. This story does not add utility styling.

## Design Notes

Read the saved token inside the `useState` initializer and set `tokenRef` in that same turn. A `useEffect` runs too late: the guards would already have redirected to `/login`.

Call `/me` after that first render when a token was restored. Do not block the first paint on the network. Login keeps writing the token only after `/me` succeeds, so a failed sign-in never leaves a saved token behind.

## Verification

**Commands:**
- `npm run build` in `apps/web` -- expected: TypeScript and Vite build succeed

**Manual checks (if no CLI):**
- Sign in, reload `/documents` and `/chat`, and confirm both stay signed in with email and tenant in the header.
- Sign out, reload, and confirm `/login`.
- With a saved token, confirm a 401 from `/me` returns to `/login` and a later reload stays there.
