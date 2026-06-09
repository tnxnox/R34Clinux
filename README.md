# R34 Linux Client

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml/badge.svg)](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-FF5E5B?logo=kofi)](https://ko-fi.com/thenoix)

Python desktop client for rule34.xxx using the official authenticated API and
Qt6 (PySide6). Built for keyboard-driven browsing, local favorites management,
and practical Linux desktop use.

---

## Features

### Search & Browsing
- Search posts by any tag query — supports full booru tag syntax.
- **Autocomplete** as you type: token-aware `QCompleter` popup with 90 ms
  debounce, fetched from the Rule34 autocomplete API.
- **Pagination** with Previous / Next controls; page counter in the toolbar.
- **Search history** dropdown (last 12 queries, persisted).
- **Saved searches** — name and persist any query; pick from a dropdown.
- **Pinned filters** — toggle a filter on/off for one-click reuse.
- **Related tags** — extracted from current search results, ranked by frequency.
  Click any tag to append it to the current query and re-search.

### Preview & Media
- **Image preview** loaded in a scrollable panel with four fit modes:
  - *Smart* — long strips fit width, images fit viewport.
  - *Fit Width* — scale to panel width.
  - *Fit Height* — scale to panel height.
  - *Original* — 1:1 pixel mapping with scroll.
- **Zoom** — `Ctrl+Mouse Wheel` zooms in/out (10%–300%).
- **Pan** — left-click drag when zoomed in.
- **Video playback** via embedded VLC (`python-vlc`):
  - Play / pause (click the video surface).
  - Seek slider with click-to-position.
  - Volume slider (default 80%).
  - Time label showing current / total duration.
  - Hardware acceleration fallback (software decode on systems without VA-API).
- **Hydration** — posts loaded from minimal sources (HTML parsing, thumbnails)
  get enriched with full API metadata on first view or batch-hydrated on load.

### Favorites
- **Local favorites** stored in a managed SQLite database — no server round-trip
  for listing or indexing.
- **Bulk operations** — select multiple posts, add or remove all at once from the
  context menu.
- **Collections** — create named folders and assign posts to them. Filter the
  favorites list by collection.
- **Pending mutations** — if FlareSolverr / remote sync is unavailable, add and
  remove operations are queued locally with exponential backoff and retried
  automatically. The queue persists across restarts.
- **Toggle favorite** with keyboard shortcut `F`.

### Friends
- Add friends by Rule34 user ID with a display name and optional notes.
- Click a friend to load their public favorites (fetched via FlareSolverr, then
  enriched with full metadata from the API).
- Browse, download, open, and add their posts to your own favorites.

### Downloads
- **Single and batch download** from the context menu.
- Download manager with serial queue, retry (3 attempts, 1.5 s backoff), and
  resume support via `Range` header.
- Files saved to `~/Downloads/r34/` by post ID + original extension.
- Download completion tracked in the database.

### Sync (FlareSolverr)
- **Remote favorites sync** via FlareSolverr — pulls your full account favorites
  list and reconciles it with your local database (adds missing, removes stale).
- **Background sync** on a configurable timer (default 15 min; set to 0 to
  disable).
- **Fallback chain** — tries DAPI first, falls back to HTML page parsing if
  the API returns empty.
- **Degraded mode** — after 5 consecutive rate-limited responses, sync pauses
  for 300 seconds with exponential backoff.
- Uses a web-authenticated FlareSolverr session (username + password) for add
  and remove operations on the remote account.
- Sync progress and errors reported in the status bar; full debug log written
  to `~/.config/r34-client/sync-debug.log`.

### Threading & Reliability
- **Isolated worker pools** — separate `QThreadPool` instances for general,
  search, sync, mutation, download, preview, and hydration. One pool can be
  busy without freezing the UI or blocking other work.
- **Token-based stale-result discarding** — every async operation gets an
  incrementing token; results from a stale operation are silently dropped.
- **TokenBucket rate limiter** for API requests and pending remote mutations.
- **Automatic 429 handling** with backoff and degraded-mode cooldown.
- **Graceful shutdown** — saves settings, stops timers, drains worker pools,
  destroys the FlareSolverr session, and forces exit after a 3.5 s timeout.

### Diagnostics & Controls
- **Diagnostics dialog** — one-click snapshot of timers, settings, worker pool
  counts, VLC state, sync state, pending mutation queue, and rate-limit state.
- **Controls dialog** — lists all keyboard shortcuts and mouse controls.
- **Sync debug log** — append-only log at `~/.config/r34-client/sync-debug.log`
  with timestamps for every sync event and error.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `J` | Move selection **down** in the active post list |
| `K` | Move selection **up** in the active post list |
| `Ctrl+J` | **Extend** selection down (multi-select) |
| `Ctrl+K` | **Extend** selection up (multi-select) |
| `F` | Toggle current post's **favorite** status |
| `O` | Open selected post in the default browser |
| `D` | **Download** the selected post |
| `Esc` | Cancel current operations (workers, timers) |
| `Ctrl+Scroll` | Zoom in / out on the preview image |
| Click + drag | Pan the preview image when zoomed in |
| Click video | Toggle play / pause |

Shortcuts are active application-wide unless a text input is focused.

---

## Requirements

- **Python** 3.11 or newer
- A **rule34.xxx API account** with `user_id` and `api_key`
- **Qt6/PySide6** (installed automatically by the launcher)
- **VLC** (optional — needed for video playback)
- **Docker** or **Podman** (optional — needed for FlareSolverr-based favorites
  sync; the launcher can install either)
- A Linux system with `bash` and a package manager (apt, dnf, pacman, zypper,
  or apk) — the launcher can bootstrap the entire runtime on a fresh system.

---

## Install

The launcher script handles everything: Python discovery (`pyenv`, `asdf`,
`mise`, system package manager, distrobox), venv creation, dependency
installation, optional VLC install, optional Docker/Podman setup, and
FlareSolverr start.

```bash
chmod +x scripts/start_r34.sh
./scripts/start_r34.sh
```

Manual setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m r34_client
```

Or directly from the source tree without pip-installing:

```bash
python3 -m venv .venv
.venv/bin/pip install PySide6 requests python-vlc  # or let pip resolve pyproject.toml
.venv/bin/python -m r34_client
```

---

## Settings

Access settings via the toolbar button (gear icon). On first launch without
credentials, settings open automatically in "Initial Setup" mode.

| Setting | Default | Description |
|---------|---------|-------------|
| API User ID | — | Your rule34.xxx API user ID |
| API Key | — | Your rule34.xxx API key |
| Website Username | — | Username for web login (needed for remote add/remove sync) |
| Website Password | — | Password for web login |
| FlareSolverr URL | `http://127.0.0.1:8191` | Endpoint for the FlareSolverr container |
| Enable FlareSolverr Sync | `True` | Enable remote favorites sync via FlareSolverr |
| Background Sync Interval | 15 min | Periodic favorites sync (0 = disabled) |
| Posts per Page | 42 | Results per search page (1–200) |

---

## Launcher Behaviour

The recommended `scripts/start_r34.sh` script does the following on Linux:

1. **Logging** — writes to `~/.local/share/r34-client/r34-launcher.log`.
2. **Display** — auto-detects Wayland vs X11 and sets `QT_QPA_PLATFORM`.
3. **Python discovery** — checks for `python3.11+` via `pyenv`, `asdf`, `mise`,
   system package manager, and distrobox — in that order.
4. **VLC** — verifies `vlc --version`; installs via package manager if missing.
5. **Container runtime** — detects Docker or Podman; attempts to install the
   missing one.
6. **FlareSolverr** — starts via a 6-tier fallback chain:
   - Tier 1: Already running check against the configured URL.
   - Tier 2: Existing stopped container (`r34-flaresolverr`).
   - Tier 3: Launch a new container with image tag fallback
     (`latest` → `v3.3.21` → `v3.3.20` → `v3.3.19`).
   - Tier 4: Fall back to Podman if Docker is unavailable.
   - Tier 5: Install FlareSolverr via `npm` as a last resort.
   - Tier 6: Install FlareSolverr via `pip`.
7. **Cleanup** — on exit (trap on EXIT, INT, TERM), stops and removes the
   FlareSolverr container.

Docker storage corruption (\"read-only file system\") is detected and
auto-repaired by backing up and resetting the overlay2 storage.

---

## Project Structure

```
src/r34_client/
├── __main__.py                 # CLI entry point
├── api/
│   ├── client.py               # Rule34 API client (search, autocomplete, rate limiting)
│   ├── urls.py                  # URL constants and builders
│   ├── flaresolverr.py          # FlareSolverr HTTP client + session management
│   └── flaresolverr_parsing.py  # HTML/JSON parsing for FlareSolverr responses
├── core/
│   ├── models.py                # Post / TagSuggestion dataclasses
│   ├── settings.py              # AppSettings model + JSON settings store
│   ├── db.py                    # SQLite database (favorites, collections, friends, cache, etc.)
│   ├── download_manager.py      # Download queue + file I/O
│   ├── worker.py                # FunctionWorker + worker pool builder
│   └── rate_limit.py            # TokenBucket + DegradedModeController
├── sync/
│   ├── favorites_sync.py        # Remote → local favorites reconciliation
│   └── pending_mutations.py     # Offline-tolerant add/remove queue with backoff
└── ui/
    ├── main_window.py           # MainWindow — all widgets, layout, connections
    ├── features/
    │   ├── preview.py           # Post preview, hydration, image display
    │   ├── media.py             # Video playback controls
    │   ├── navigation.py        # Keyboard shortcuts
    │   ├── context_menu.py      # Right-click menus for all post lists
    │   ├── autocomplete.py      # Token-aware QCompleter
    │   ├── status.py            # Status bar + action state
    │   └── settings_action.py   # Toolbar action connector
    ├── search/controller.py     # Search, pagination, history, saved searches, pins
    ├── favorites/
    │   ├── controller.py        # Favorites CRUD, refresh, sync trigger
    │   ├── bulk.py              # Add/remove multiple favorites
    │   ├── collections.py       # Named collection management
    │   └── pending.py           # Pending mutation state machine + watchdog
    ├── friends/controller.py    # Friends CRUD + friend favorites loading
    ├── widgets/
    │   ├── video_player.py      # VLC-based video engine
    │   └── custom.py            # ClickSeekSlider, ClickVideoSurface
    ├── helpers/
    │   ├── post.py              # Tile/metadata formatting, hydration check, file-size probe
    │   ├── preview_fetcher.py   # Image download with host fallback
    │   └── image_fit.py         # Fit-mode computation
    └── dialogs/
        ├── settings.py          # Settings form dialog
        ├── controls.py          # Keyboard/mouse reference dialog
        └── diagnostics.py       # System state snapshot dialog
scripts/
└── start_r34.sh                 # Launcher — Python/venv/VLC/Docker/FlareSolverr bootstrap
```

---

## Notes

- The official API requires authentication. Search and autocomplete will prompt
  for credentials if they are missing.
- Search history, saved searches, pinned filters, and UI preferences are stored
  via the Qt settings backend.
- Favorites, collections, friends, post metadata cache, and tag autocomplete
  cache are stored in a local SQLite database.
- FlareSolverr sync is optional and only needed for two-way account favorites
  management.
- When FlareSolverr is disabled, local favorites still work fully; pending
  remote mutations queue up silently.
- The autocomplete cache has a 1-hour TTL and is purged on stale lookups.
- Video playback falls back to software decoding on systems without working
  VA-API drivers (common in containers or VMs).
- Use the Controls dialog (toolbar → Controls) to see all shortcuts at any
  time.
- Use the Diagnostics dialog (toolbar → Diagnostics) to inspect live state
  without grepping log files.

---

## Troubleshooting

- **Search returns nothing:** Verify your API credentials in Settings.
- **FlareSolverr sync fails:** Confirm the container is reachable at
  `http://127.0.0.1:8191` (or your configured URL). Check the sync debug log
  at `~/.config/r34-client/sync-debug.log`.
- **Video playback is unstable:** Install VLC. On systems without VA-API, the
  launcher configures software decode automatically; if you see `get_buffer()
  failed` in the logs, that's expected and harmless.
- **Launcher reports missing dependencies:** Re-run `./scripts/start_r34.sh` —
  it will re-attempt installation.
- **Docker storage errors:** The launcher detects and repairs overlay2
  corruption automatically; if repairs fail, check `docker system df` and
  consider pruning unused data.
- **Large images don't load:** Qt has a default 256 MB image allocation limit.
  Images over ~9–10 MB JPEG may hit this during decompression.

---

## Support

If this project helps you out, consider buying me a coffee:

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/thenoix)

## License

MIT — see [LICENSE](LICENSE) for the full text.
