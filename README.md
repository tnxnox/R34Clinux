# R34 Linux Client

[![Rust](https://img.shields.io/badge/Rust-2024-orange?logo=rust)](https://rust-lang.org)
[![Release](https://img.shields.io/github/v/release/tnxnox/R34Clinux?color=blue&logo=github)](https://github.com/tnxnox/R34Clinux/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml/badge.svg)](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-FF5E5B?logo=kofi)](https://ko-fi.com/thenoix)

A fast, privacy-focused desktop client for rule34.xxx — search, browse, collect, and download. Built with Rust, Tauri 2, and React for Linux (with planned Windows support).

---

## Quick Start

Get your API credentials from rule34.xxx (**Account → My Settings → API**), then choose an installation method:

### Option 1: Run from source (Development mode)

Prerequisites can be automatically checked and installed:

```bash
git clone https://github.com/tnxnox/R34Clinux.git
cd R34Clinux
./start_r34.sh
```

Alternatively, run via `make`:

```bash
make setup  # Installs system build dependencies (WebKit2GTK, GTK3, etc.)
make dev    # Installs npm dependencies and launches Tauri in dev mode
```

### Option 2: Install system-wide

Build and install the binary directly with Cargo:

```bash
git clone https://github.com/tnxnox/R34Clinux.git
cd R34Clinux
cargo install --path app/src-tauri --locked
```

The binary `r34-client` is installed to `~/.cargo/bin/`. Ensure `~/.cargo/bin` is in your `$PATH`. Frontend assets and dependencies are bundled automatically during build. You can reclaim build disk space afterwards with `cargo clean`.

The application prompts for API credentials on first launch.

**Prerequisites:** Node.js (v18+) & npm, Rust & Cargo, and Tauri Linux dependencies (WebKit2GTK 4.1, GTK3, OpenSSL). Docker or Podman is optional, needed only if you use FlareSolverr account sync.

---

## Features

- **Search & Tag Discovery**:
  - Fast search by tag with real-time autocomplete suggestions
  - Multi-tag filtering and global tag blacklist filtering to hide unwanted content
  - Search history and saved searches for quick access
  - Configurable page size (1–1,000 posts per page)
- **Interactive Media Viewer**:
  - High-resolution image preview with smooth zoom and pan (`Ctrl + Scroll`, click-and-drag)
  - Custom HTML5 video player with timeline seek bar, duration display, and volume/mute controls
  - Detail modal with categorized and color-coded tags grouped by type (General, Artist, Character, Copyright, Metadata)
  - Instant tag clicking to trigger new searches, plus external source and browser links
  - Fullscreen viewing support (`F11`)
- **Local Favorites & Collections**:
  - Offline-first favorites library backed by a local SQLite database
  - Create and manage custom collections/albums
  - Multi-select toolbar for batch favorites, downloads, and collection management
- **Account Sync & Resilient Mutation Queue**:
  - Synchronize account favorites using FlareSolverr
  - Automated local container lifecycle management for Docker or Podman
  - Configurable sync conflict resolution strategies (`Remote Wins`, `Merge`, `Local Wins`)
  - Background mutation queue with exponential backoff retries against Rule34 rate limits (HTTP 429) or temporary network outages, accompanied by a glassmorphic progress bar
- **Download Manager**:
  - Single and batch post downloads with live progress indicators
  - Customizable file naming templates (`{id}`, `{md5}`, `{tags}`, etc.)
  - Option to download compressed sample files or original full-resolution media
  - Optional `.json` and `.txt` tag metadata sidecars saved alongside media files
- **Friends**:
  - Add friends by Rule34 username to browse their public favorites directly inside the app

> [!WARNING]
> **TOS Disclaimer regarding FlareSolverr Sync**: 
> Managing account-bound favorites is not supported by the official Rule34 Developer API (DAPI). To sync favorites, the application interacts with the standard web interface using a local FlareSolverr instance. Under the website's Terms of Service, using automated processes to retrieve or modify web pages is technically prohibited. While the sync feature enforces rate limits to mimic human browsing behavior and runs entirely locally, it is disabled by default. **Use this feature at your own risk and discretion.**

---

## Project Structure

This repository uses a virtual Cargo workspace:

```
R34Clinux/
├── Cargo.toml            # Virtual workspace root
├── Makefile              # Developer shortcuts (dev, build, check, test, clean)
├── start_r34.sh          # Quickstart launcher with automated dependency checks
├── scripts/
│   └── setup.sh          # System package dependency installer (apt, dnf, pacman)
└── app/
    ├── package.json      # Frontend package configuration (Vite, React 19)
    ├── src/              # React frontend (components, tabs, services)
    └── src-tauri/        # Tauri 2 backend (Rust, SQLite, reqwest, FlareSolverr)
```

---

## Development & Testing

Run the full automated test suite (backend unit tests + frontend Vitest suites):

```bash
# Run all tests (Rust backend + Frontend Vitest)
make test

# Or run test suites individually:
cargo test --workspace      # Rust backend unit tests (39 tests)
npm --prefix app test       # Frontend Vitest suites (77 tests across 11 suites)

# Type-checking and clippy lints:
make check                  # cargo check --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all -- --check
```

---

## Settings

Access via the toolbar (gear icon). Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| API User ID | — | Your rule34.xxx API user ID |
| API Key | — | Your rule34.xxx API key |
| Website Username | — | Needed for remote favorites sync |
| Website Password | — | Needed for remote favorites sync |
| Tag Blacklist | — | Hide posts containing specific tags from searches |
| Download Directory | `~/Downloads` | Destination folder for downloaded files |
| Naming Template | `{id}` | File naming format (supports `{id}`, `{md5}`, `{tags}`, etc.) |
| Save JSON/TXT tags sidecar | No | Download metadata tag sidecar files alongside media |
| Use compressed sample | No | Download compressed sample files instead of original high-res files |
| Conflict Resolution Strategy | `Remote Wins` | Strategy when local and remote differ: `Remote Wins`, `Merge`, or `Local Wins` |
| Enable FlareSolverr Proxy | No | Enable FlareSolverr integration for remote sync |
| FlareSolverr URL | `http://127.0.0.1:8191` | FlareSolverr local endpoint |
| Posts per Page | 50 | Results per search page (1–1000) |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `J` / `K` | Move selection down / up |
| `Ctrl+J` / `Ctrl+K` | Extend selection (multi-select) |
| `F` | Toggle favorite |
| `O` | Open in browser |
| `D` | Download |
| `F11` | Toggle fullscreen |
| `Esc` | Cancel multi-select / close modals |
| `Ctrl+Scroll` | Zoom preview |
| Click + drag | Pan preview when zoomed |
| Click video / Space | Play / pause video |

---

## Troubleshooting

- **Search returns nothing** — check your API credentials in Settings.
- **FlareSolverr fails** — make sure Docker or Podman is running and reachable at `http://127.0.0.1:8191`; check terminal console logs where the app was launched.
- **Missing system dependencies on Linux** — run `./scripts/setup.sh` to install required WebKit2GTK and GTK development libraries.

---

## Feedback & Support

- If you encounter problems or discover bugs, feel free to open an [issue](https://github.com/tnxnox/R34Clinux/issues) or reach out on Discord: `thenoix`.
- If you find this app helpful, thank you for supporting development:

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/thenoix)

---

## License

MIT — see [LICENSE](LICENSE) for details.
