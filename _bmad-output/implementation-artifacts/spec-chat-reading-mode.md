---
title: 'Chat reading mode for cited PDFs'
type: 'feature'
created: '2026-10-23'
status: 'done'
baseline_commit: '251f5e80c494517d0518c564f22b0628c273a65d'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** With a citation open, the PDF is capped at 22rem inside a `max-w-7xl` page, and below `lg` it shares height with the thread. A page is not readable.

**Approach:** Opening a source enters reading mode. The conversation rail hides, and the open/closed choice the member had before is restored when the source closes. From `lg` up, the thread is a narrow column and the PDF takes the remaining viewport width. Below `lg` the thread stays mounted but hidden, and the PDF fills the screen until the source is closed. The chat route drops the page max-width. The iframe asks the viewer to fit the page to the panel width.

</frozen-after-approval>

## Implementation Notes

- Reading mode is `activeSource !== null`. `railOpen` is left unchanged, so closing the source restores the rail the member had open or closed.
- Desktop (`lg` and up): grid is `minmax(20rem,26rem)` for the thread and the rest for the PDF. Below `lg` the thread stays mounted with `hidden` and the PDF is the only grid item.
- Chat route uses `max-w-none`. Other routes keep `max-w-7xl`. With the rail open and no source, the thread stays `max-w-3xl` and sits beside the rail. With the rail closed, it stays centered.
- The iframe fragment is `#page={n}&view=FitH` (1-based page). No new PDF library.
- `apps/web` `tsc --noEmit` reports unused `token` and `me` in `Header.tsx`. Those parameters were already unused. The unused `Link` import was removed while aligning the header width with the chat route.
- Review fixes: the open rail centers the thread below `lg`; the chat header uses `max-w-none`; the rail stays mounted and hidden in reading mode so its scroll position remains; below `lg` the close button takes focus and Escape closes the panel; a conversation change clears the source during render; message text uses `break-words`; the reading thread uses `hidden lg:flex` without a competing `flex`.

## Review Triage Log

- low — Below `lg`, an open rail left the `max-w-3xl` thread on the left. Patched with `mx-auto lg:mx-0`.
- medium — Chat content was `max-w-none` while the header stayed `max-w-7xl`, so a wide PDF ran past the header. Patched: the header drops `max-w-7xl` on `/chat`.
- medium — Unmounting the rail discarded its scroll position. Patched: the rail stays mounted with `hidden` while a source is open.
- medium — Below `lg` the thread is `display: none`, so focus left the citation and Escape did nothing. Patched: the close button is focused under 1024px, and Escape calls `onClose`.
- medium — Clearing the source in an effect left one paint of the previous PDF. Patched: `activeSource` resets during render when the conversation id changes.
- low — App header, `main` padding, and the card still sit above the iframe on a short screen. The extra "Source" heading and the stacked filename/page lines were removed. The app header stays; it is the shell on every route, and the PDF already fills the content region under it.
- medium — A long unbroken token in the 26rem column could force a horizontal scrollbar. Patched with `min-w-0` and `break-words` on user and assistant messages. Code blocks and tables keep their own horizontal scroll.
- low — Reading mode set both `flex` and `hidden`, so visibility depended on Tailwind emitting `.hidden` later. Patched: reading mode is `hidden lg:flex` only.
