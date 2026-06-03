.PHONY: test lint typecheck run clean install

VENV = .venv
PYTHON = $(VENV)/bin/python
RUFF = $(VENV)/bin/ruff
MYPY = $(VENV)/bin/mypy

test:
	$(PYTHON) -m unittest discover -s src/tests -p "test_*.py" -v

test-quick:
	$(PYTHON) src/tests/run_all.py

lint:
	$(RUFF) check src/r34_client/

lint-fix:
	$(RUFF) check --fix src/r34_client/

typecheck:
	$(MYPY) src/r34_client/

run:
	$(PYTHON) -m r34_client

install:
	$(PYTHON) -m pip install -e .

clean:
	rm -rf build/ dist/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
