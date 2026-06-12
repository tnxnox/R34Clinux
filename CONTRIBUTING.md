# Contributing

Thanks for considering contributing to the R34 Linux Client!

## Repository Rules & Hygiene

To maintain the security and cleanliness of this repository:

1. **No Secrets/Credentials**: Never commit or push personal access keys, user credentials (`id.txt`, `apikey.txt`), passwords, or configuration files containing credentials.
2. **No Development-Only Trackers**: Do not commit internal bug audits, concurrency trackers, or personal task lists (such as `AUDIT_REPORT.md`). These should stay ignored locally.
3. **No Private/Internal Documentation**: Public documentation must only cover user-facing setup, help guides, and contributing procedures. Detailed internal cheatsheets, credentials templates, and development notes must go into the private submodule (`docs/private/`).

## Getting Started

1. Fork and clone the repo
2. Install system dependencies using `./scripts/setup.sh` or the guide in `README.md`
3. Start the development server using `./start_r34.sh` or `make dev`
4. Run unit tests using `make test` or `cd desktop/src-tauri && cargo test`

## Code Style

- Ensure all Rust code is formatted via `cargo fmt` and matches `clippy` checks (`cargo clippy --all-targets -- -D warnings`)
- Keep UI components responsive, modular, and use vanilla CSS (or components styles) adhering to design system tokens

## Commit Messages

This project uses conventional commits:

```
type: short description

Optional body explaining the why, not the what.
```

Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `chore`, `test`, `build`

## Pull Requests

- Keep PRs focused on one thing
- Make sure all unit tests, clippy, and build checks pass before opening
- Link related issues if applicable
- Squash commits if the history is noisy

## Running Tests

```bash
# Run backend unit tests
make test
```

## License

By contributing, you agree that your contributions will be licensed under the MIT license.
