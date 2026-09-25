.PHONY: dev build check test clean setup

dev:
	@if [ ! -d "app/node_modules" ]; then \
		echo "Installing frontend dependencies..."; \
		cd app && npm install; \
	fi
	cd app && npm run tauri dev

build:
	@if [ ! -d "app/node_modules" ]; then \
		echo "Installing frontend dependencies..."; \
		cd app && npm install; \
	fi
	cd app && npm run tauri build

setup:
	bash scripts/setup.sh

check:
	cargo check --workspace

test:
	cargo test --workspace
	npm --prefix app test

clean:
	cargo clean
	rm -rf app/dist

