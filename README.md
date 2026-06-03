# R34 Linux Client

Python desktop client for rule34.xxx using the official authenticated API.

This app is built for keyboard-driven browsing, favorites management, and
practical Linux desktop use. It includes optional FlareSolverr-backed account
favorites sync, local favorites collections, search presets, related-tag
suggestions, and a launcher that can bootstrap the runtime on a fresh system.

## Features

- Search posts by tag query with autocomplete suggestions.
- Browse paginated results with next/previous controls.
- Re-run recent searches from a quick history dropdown.
- Save and pin common searches for one-click reuse.
- See related tags suggested from the current search results.
- Preview images and videos in the built-in viewer.
- Use fit modes for the preview: smart, width, height, and 1:1.
- Play, pause, seek, and adjust volume for video posts.
- Copy the selected post link, open it in a browser, or download it.
- Save favorites locally with instant indexing in the Favorites tab.
- Add or remove multiple favorites at once from the context menu.
- Organize favorites into collections/folders.
- **High Performance:** Connection pooling via `requests.Session` for rapid search and autocomplete responses.
- **Intelligent Sync:** Non-destructive favorites synchronization that preserves local data while aligning with your remote account.
- **Robustness:** Thread-safe operations and automatic handling of Rule34 rate limits.
- Configure background favorites sync intervals.
- See built-in diagnostics and controls panels.
- Persist API credentials, sync settings, and download location with Qt settings.
- Launch with a helper script that can install dependencies and start FlareSolverr.

## Keyboard Shortcuts

- `J` / `K`: move to the next or previous post.
- `Ctrl+J` / `Ctrl+K`: extend selection.
- `F`: toggle the current favorite.
- `O`: open the selected post in the browser.
- `D`: download the selected post.
- `Esc`: cancel current operations.

## Requirements

- Python 3.11 or newer
- A rule34.xxx API account with `user_id` and `api_key`
- Optional for favorites sync: FlareSolverr running locally
- Optional for video playback: VLC

If you want the launcher to manage dependencies automatically, use a Linux
system with `bash`, a package manager, and Docker.

## Install

Recommended on Linux if you want the app to bootstrap itself:

```bash
chmod +x scripts/start_r34.sh
./scripts/start_r34.sh
```

Manual setup:

```bash
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/r34-linux-client
```

Or run directly from the source tree:

```bash
python -m r34_client
```

## Settings

- Enter your API credentials on first launch before searching.
- Set a download directory if you do not want to use the default Downloads folder.
- Set your preferred results-per-page value.
- Enable FlareSolverr sync only if you want remote favorites to stay aligned.
- If you use account add/remove sync, also provide website username/password so the app can authenticate a browser session.
- Choose a sync conflict strategy:
  - `merge`: combine local and remote favorites.
  - `local_wins`: keep local favorites as the source of truth.
  - `remote_wins`: replace local favorites with the remote set.
- Set the background sync interval to `0` to disable quiet periodic sync.

## Notes

- The official API requires authentication.
- Search will prompt for credentials if they are missing.
- Search history, saved searches, pinned filters, and recent UI preferences are stored locally with Qt settings.
- FlareSolverr sync is optional and only needed for account favorites sync.
- Bulk favorite actions and collections are available from the favorites context menu.
- Related-tag suggestions are generated from the current search results.
- Diagnostics and sync debug output are available from the built-in diagnostics view and local sync log file.

## Troubleshooting

- If the app cannot search, verify your API credentials in Settings.
- If FlareSolverr sync is failing, confirm the local FlareSolverr container or service is reachable at `http://127.0.0.1:8191` or your configured URL.
- If video playback is unstable on Linux, install VLC and keep software OpenGL enabled as the launcher configures.
- If the launcher reports missing dependencies, rerun `./scripts/start_r34.sh` and let it install the required packages.

## Launcher Behavior

The recommended launcher does the following on Linux:

1. Checks for Python 3.11+.
2. Creates or repairs the local virtual environment if needed.
3. Installs or verifies runtime dependencies.
4. Starts FlareSolverr in Docker if sync is enabled and Docker is available.
5. Launches the app and stops FlareSolverr on exit.
