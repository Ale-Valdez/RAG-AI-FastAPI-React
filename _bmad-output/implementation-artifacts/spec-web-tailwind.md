---
title: 'Install Tailwind in the web app'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The web app has no utility CSS toolchain. New layout work cannot use Tailwind classes.

**Approach:** Install Tailwind CSS v4 and the official Vite plugin, with exact versions, and load it from the existing stylesheet. Keep the current CSS rules and do not convert screens to utility classes. The running Compose web container must receive the same packages without an image rebuild.

</frozen-after-approval>

## Implementation Notes

- Installed `tailwindcss` 4.3.3 and `@tailwindcss/vite` 4.3.3 as exact devDependencies. The Vite config registers the plugin. `apps/web/src/styles.css` imports Tailwind and keeps the previous rules inside `@layer components`, so a utility can override them.
- Preflight clears user-agent heading size, paragraph margins, and link underlines. Restored `header h1`, panel headings, `p` margins, and the Health link underline.
- Host `npm run build` passed. The Compose web container got the same packages with `docker compose exec web npm install` and a restart, without an image rebuild. Login and Health still render on `http://127.0.0.1:5173`. A temporary `text-red-600` class changed the eyebrow color and was removed.
- Screens were not converted to utility classes.

## Review Triage Log

- defer — The image runs `npm install` before the lockfile is copied. Pre-existing Dockerfile order. Direct versions stay exact in `package.json`. Recorded in `deferred-work.md`.
- false — The `web_node_modules` volume was missing Tailwind until an install. After `docker compose exec web npm install` and a restart, Vite started and a utility class applied. The missing automatic reinstall is deferred in `deferred-work.md`.
- patch — Preflight left headings at `font-size: inherit` and removed the Health underline and paragraph margins. Restored those rules in `styles.css`. Login and Health were checked again in the browser.
- false — Element rules live in `@layer components` and there is no `@theme` palette. That layer is what lets a utility override the current sheet. Tokens and a utility rewrite were out of scope.
- false — Components still use the existing class names. The spec keeps that sheet. `sign-out` was already unused before this install.
- false — `NODE_ENV` is unset in the web container, and the dev server started with `@tailwindcss/vite` installed. A production static image is not what this service runs.
