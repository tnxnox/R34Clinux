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
	cd app/src-tauri && cargo check

test:
	cd app/src-tauri && cargo test

clean:
	cd app/src-tauri && cargo clean
	rm -rf app/dist

