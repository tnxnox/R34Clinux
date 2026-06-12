# R34 Linux Client

[![Rust](https://img.shields.io/badge/Rust-1.70%2B-orange?logo=rust)](https://rust-lang.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml/badge.svg)](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-FF5E5B?logo=kofi)](https://ko-fi.com/thenoix)

A proper desktop client for rule34.xxx — search, browse, collect, download. Built
with Rust and Tauri for Linux.
I'm also planning a windows release soon.

## Quick Start

Get your API credentials from rule34.xxx (Account → My Settings → API), then clone and start the app:

```bash
git clone https://github.com/tnxnox/R34Clinux.git
cd R34Clinux

# Setup dependencies and start the app automatically
./start_r34.sh
```

The app will prompt you to enter credentials on first launch.

**Requirements:** Node.js (v18+) & npm, Rust & Cargo. VLC is needed for video playback, Docker/Podman for
FlareSolverr sync — both optional, local favorites work without either.

## What It Does

- Search by tag with autocomplete, pagination, search history, and saved searches
- Browse image previews with zoom/pan, watch videos with seek controls (including click-to-seek)
- Interactive details panel with clickable metadata tags (for quick searching) and source links (to open in browser)
- Manage favorites locally — collections, bulk operations, and keyboard shortcuts
- Sync your account favorites via FlareSolverr (optional) with automatic local container management (Docker/Podman support)
- Robust pending remote favorites mutation queue (add/remove favorite) with automated exponential backoff retry logic (resilient to Rule34 rate limits / HTTP 429) and a sleek glassmorphic progress bar
- Download posts individually or in batches
- Add friends and browse their public favorites

> [!WARNING]
> **TOS Disclaimer regarding FlareSolverr Sync**: 
> Managing account-bound favorites is not supported by the official Rule34 Developer API (DAPI). To sync favorites, the application interacts with the standard web interface using a local FlareSolverr instance. Under the website's Terms of Service, using automated processes to retrieve or modify web pages is technically prohibited. While the sync feature enforces rate limits to mimic human browsing behavior and runs entirely locally, it is disabled by default. **Use this feature at your own risk and discretion.**

## Settings

Access via the toolbar (gear icon). Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| API User ID | — | Your rule34.xxx API user ID |
| API Key | — | Your rule34.xxx API key |
| Website Username | — | Needed for remote add/remove sync |
| Website Password | — | Needed for remote add/remove sync |
| FlareSolverr URL | `http://127.0.0.1:8191` | FlareSolverr endpoint |
| Enable FlareSolverr Sync | Yes | Enable remote favorites sync |
| Background Sync Interval | 0 (disabled) | Auto-sync interval in minutes |
| Posts per Page | 50 | Results per search page (1–200) |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `J` / `K` | Move selection down / up |
| `Ctrl+J` / `Ctrl+K` | Extend selection (multi-select) |
| `F` | Toggle favorite |
| `O` | Open in browser |
| `D` | Download |
| `Esc` | Cancel current operations |
| `Ctrl+Scroll` | Zoom preview |
| Click + drag | Pan preview when zoomed |
| Click video | Play / pause |

## Troubleshooting

- **Search returns nothing** — check your API credentials in Settings
- **FlareSolverr fails** — make sure the container is running and reachable at
  `http://127.0.0.1:8191`; check the terminal console logs where the app was launched.

## Feedback

- If you encounter problems you don't know how to solve, or discover bugs, feel free
  to either open an [issue](https://github.com/tnxnox/R34Clinux/issues) or message me
  on discord : thenoix

## Support

If you like the app, you can thank me here :

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/thenoix)

## License

MIT — see [LICENSE](LICENSE) for the full text.
