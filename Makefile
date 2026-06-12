.PHONY: dev build check test clean setup

dev:
	@if [ ! -d "desktop/node_modules" ]; then \
		echo "Installing frontend dependencies..."; \
		cd desktop && npm install; \
	fi
	cd desktop && npm run tauri dev

build:
	@if [ ! -d "desktop/node_modules" ]; then \
		echo "Installing frontend dependencies..."; \
		cd desktop && npm install; \
	fi
	cd desktop && npm run tauri build

setup:
	bash scripts/setup.sh

check:
	cd desktop/src-tauri && cargo check

test:
	cd desktop/src-tauri && cargo test

clean:
	cd desktop/src-tauri && cargo clean
	rm -rf desktop/dist

