---
title: 'Web router and layout'
type: 'refactor'
created: '2026-10-22'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Route matching, auth redirects, and the app header all live in `apps/web/src/App.tsx`, so navigation structure is mixed with layout markup.

**Approach:** Move the route table into its own module and render it with React Router's data router (`createBrowserRouter` and `RouterProvider`). The installed `react-router-dom` 7.6.1 package does not export a stable `createRouter`; `createBrowserRouter` is that factory. Add a layout whose header wraps the login, documents, and chat pages. Keep the current auth gates, home and unknown-path redirects, health route, and header behavior (signed-in nav, sign out, health link). Do not add a styling library in this change.

</frozen-after-approval>

## Implementation Notes

- `react-router-dom` 7.6.1 does not export `createRouter`. The route module uses `createBrowserRouter` and `RouterProvider`. `UNSAFE_createRouter` was not used.
- `apps/web/src/routes.tsx` owns the route table and the guest, auth, and home redirects. `apps/web/src/layout/AppLayout.tsx` owns the header and renders child routes through `Outlet`. `App.tsx` only mounts `RouterProvider`. `main.tsx` no longer wraps the tree in `BrowserRouter`.
- Login, documents, and chat are children of the layout. Health stays a child too, so the existing header and Health link still wrap that page. Unknown paths and `/` still redirect.
- `npm --prefix apps/web run build` passed. On a local Vite server, a guest visit to `/`, `/login`, `/documents`, `/chat`, and an unknown path showed the header and the sign-in form. `/health` showed the header and the API status panel. Signed-in navigation was not exercised.

## Review Triage Log

- low — Root route has no `errorElement`, so a render error replaces `AppLayout` with the data-router error screen. Rejected: pages do not throw today, and adding an error screen is more than a correction.
- defer — A 401 opens `/login` only while `RequireAuth` is mounted. Pre-existing: the same wrappers guarded only documents and chat before this change. Recorded in `deferred-work.md`.
- false — Separate `RequireAuth` wrappers make a future sibling public. Existing documents and chat routes are still guarded. A shared parent is a later structure choice, not a current miss.
- false — No `ScrollRestoration`, title updates, focus move, or nav name. The previous shell did not have those either.
- false — Health is a `Link` without the active nav style. The previous header used that same link, outside the Documents and Chat nav.
- false — `/CHAT` matches `chat/:id?`. `matchRoutes` confirms the library default, and the previous `<Route path="/chat/:id?">` used that same default.
- false — `Navigate` leaves main empty until the URL updates. Guest redirects already rendered `Navigate` inside the old `<Routes>`. A one-frame sign-out flicker from `startTransition` was not observed.
- false — Implementation notes were empty at review time. This finalize step fills them and sets `status: done`.
