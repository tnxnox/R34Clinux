# V1 to VX Plan (Practical, High-Use Features Only)

Below is a trimmed roadmap focused on features users will actually use often, with good impact-to-effort ratio.

## V1 (Core UX and Reliability)
Goal: make daily usage fast, stable, and pleasant.

1. Keyboard-first navigation
- j/k next/previous post, f favorite toggle, o open in browser, d download.
- Why now: high frequency actions, immediate productivity boost.

2. Fit mode toggles in image viewer
- Fit width, fit height, 1:1, smart fit.
- Why now: directly improves media consumption quality.

3. Smarter loading and cancellation
- Explicit loading state + cancel ongoing preview/search/download task.
- Why now: prevents "stuck" feeling and reduces frustration on slow networks.

4. Built-in diagnostics page
- Show sync state, session state, last errors, and quick checks.
- Why now: shortens bug-fix loops and helps users self-diagnose.

5. Automatic degraded mode for rate limiting
- Backoff/retry policies and cleaner user messaging when remote throttles.
- Why now: directly tied to your known pain point (429s).

## V2 (Favorites Power Features)
Goal: make favorites actually manageable at scale.

1. Multi-select favorites actions
- Bulk remove, bulk download, bulk open.
- Why now: huge time saver once favorites list grows.

2. Favorites collections/folders
- User-defined groups (e.g., "Artists", "Refs", "To Download").
- Why now: high practical value for organization, simple mental model.

3. Sync conflict strategy selector
- local wins / remote wins / merge.
- Why now: avoids surprises and restores trust in sync behavior.

4. Background sync interval
- Sync every N minutes with quiet retries.
- Why now: keeps state fresh without manual refresh spam.

## V3 (Search and Discovery)
Goal: reduce search friction and improve discovery speed.

1. Saved searches + pinned filters
- One-click rerun for common queries.
- Why now: repeated behavior for nearly all users.

2. Search history with quick rerun
- Recent queries, editable before submit.
- Why now: small effort, very common use.

3. Related tags suggestions
- Show likely companion tags from current results.
- Why now: improves discovery without heavy complexity.

## V4 (Download Workflow) [DONE]
Goal: turn downloads into a reliable pipeline.

1. Download profiles [DONE]
- Original/sample mode, naming template, destination template.
- Why now: most users want consistency and control.

2. Retry manager + duplicate detection [DONE]
- Retry failed items and avoid re-downloading same file.
- Why now: practical reliability upgrade.

3. Metadata sidecar export [DONE]
- Save .json/.txt per media file.
- Why now: useful for cataloging and external tools.

## V5 (Polish and Scalability)
Goal: smoothness and long-session performance.

1. Smart prefetch for adjacent posts
- Prefetch next/previous media metadata/preview.
- Why now: noticeable speed feel for browsing sessions.

2. One-click bug report bundle
- Export recent logs + env + relevant traces.
- Why now: makes future support/fixes much faster.

3. Unified status center
- Centralized "what’s happening" panel for searches, downloads, sync.
- Why now: better transparency as app complexity grows.

## Features intentionally excluded
I excluded items like plugin systems, local analytics dashboards, rule engines, and heavy automation because they are niche, high-maintenance, and not core to most users’ daily workflow.

## Suggested execution cadence
1. V1 fully before anything else.
2. Then V2 (favorites scale pain appears quickly).
3. V3 and V4 in parallel if you want both discovery and download maturity.
4. V5 once core behavior is locked.
