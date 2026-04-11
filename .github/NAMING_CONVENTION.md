# Naming Convention

This repository follows a scope-first naming system.

## 1) Package and folder naming
- Use lowercase snake_case for all package and folder names.
- Top-level runtime package folders under src/r34_client represent architecture scope:
  - clients: HTTP/API clients and external service adapters
  - core: domain models, settings, pure shared logic
  - storage: persistence and local stores
  - execution: workers, concurrency, runtime execution primitives
  - ui: user interface concerns only
- Feature folders under ui/features represent user-facing feature domains.
- Split large features into subpackages when they have clear sub-responsibilities.

## 2) Module naming
- Use lowercase snake_case.py.
- Use role suffixes when they improve clarity:
  - *_client.py for service/API clients
  - *_store.py for persistence backends
  - *_dialog.py for dialog widgets
  - *_sync.py for synchronization workflows
  - *_fetcher.py for fetch-only adapters
- Avoid generic ambiguous names that collide with neighboring scopes.
  - Preferred: ui_dialogs.py
  - Avoid: dialogs.py in ui/features when ui/dialogs package also exists

## 3) Class, function, variable naming
- Classes: PascalCase.
- Functions and methods: snake_case.
- Module-level constants: UPPER_SNAKE_CASE.
- Private helpers: leading underscore, for example _sync_enabled.
- Boolean-returning names should read as predicates (is_, has_, can_, should_).

## 4) UI feature package conventions
- Feature package exports are defined in __init__.py and used as public surface.
- Internal split modules are short role names inside feature package:
  - favorites/bulk.py
  - favorites/single.py
  - favorites/pending.py
  - favorites/collections.py
- Main window imports features through package facades, not deep internals.

## 5) Test naming
- Tests use test_*.py naming.
- Test functions and methods describe behavior, not implementation detail.

## 6) Lint enforcement
- Ruff naming rules (N) are enabled.
- Framework-required method names that are intentionally non-snake-case are explicitly allowed in Ruff config.
