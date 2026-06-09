# R34 Linux Client

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml/badge.svg)](https://github.com/tnxnox/R34Clinux/actions/workflows/tests.yml)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-FF5E5B?logo=kofi)](https://ko-fi.com/thenoix)

A proper desktop client for rule34.xxx — search, browse, collect, download. Built
with Python and Qt6 for Linux.

## Quick Start

```bash
git clone https://github.com/tnxnox/R34Clinux.git
cd R34Clinux
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Get your API credentials from rule34.xxx (Account → My Settings → API), then:

```bash
r34-linux-client
```

The app will prompt you to enter them on first launch.

**Requirements:** Python 3.11+. VLC is needed for video playback, Docker/Podman for
FlareSolverr sync — both optional, local favorites work without either.

## What It Does

- Search by tag with autocomplete, pagination, search history, and saved searches
- Browse image previews with zoom/pan, watch videos with seek controls
- Manage favorites locally — collections, bulk operations, keyboard shortcuts
- Sync your account favorites via FlareSolverr (optional)
- Download posts individually or in batches
- Add friends and browse their public favorites

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
  `http://127.0.0.1:8191`; check `~/.config/r34-client/sync-debug.log`
- **Video won't play** — install VLC; software decode is automatic if VA-API
  isn't available
- **Large images don't load** — Qt caps image allocation at ~256 MB; images over
  9–10 MB JPEG may hit this

## Support

If this helps you out, consider buying me a coffee:

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/thenoix)

## License

MIT — see [LICENSE](LICENSE) for the full text.
