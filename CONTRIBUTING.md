# Contributing

Thanks for considering contributing to the R34 Linux Client!

## Repository Rules & Hygiene

To maintain the security and cleanliness of this repository:

1. **No Secrets/Credentials**: Never commit or push personal access keys, user credentials (`id.txt`, `apikey.txt`), passwords, or configuration files containing credentials.
2. **No Development-Only Trackers**: Do not commit internal bug audits, concurrency trackers, or personal task lists (such as `AUDIT_REPORT.md`). These should stay ignored locally.
3. **No Private/Internal Documentation**: Public documentation must only cover user-facing setup, help guides, and contributing procedures. Detailed internal cheatsheets, credentials templates, and development notes must go into the private submodule (`docs/private/`).

## Getting Started

1. Fork and clone the repo
2. Create a venv: `python3 -m venv .venv && source .venv/bin/activate`
3. Install in editable mode: `pip install -e .`
4. Run the tests: `python src/tests/run_all.py`

## Code Style

- Target Python 3.11+
- Use type annotations (`from __future__ import annotations`)
- Follow the existing patterns — this project uses PySide6/Qt6 and plain `unittest`

## Commit Messages

This project uses conventional commits:

```
type: short description

Optional body explaining the why, not the what.
```

Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `chore`, `test`, `build`

## Pull Requests

- Keep PRs focused on one thing
- Make sure all tests pass before opening
- Link related issues if applicable
- Squash commits if the history is noisy

## Running Tests

```bash
# Full suite
python src/tests/run_all.py

# Single file
python -m unittest src.tests.test_core_models -v
```

Tests that touch Qt use `QCoreApplication` and run fine headless. No display server needed.

## License

By contributing, you agree that your contributions will be licensed under the MIT license.
