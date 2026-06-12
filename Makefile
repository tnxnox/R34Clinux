.PHONY: dev build check test clean

dev:
	cd desktop && npm run tauri dev

build:
	cd desktop && npm run tauri build

check:
	cd desktop/src-tauri && cargo check

test:
	cd desktop/src-tauri && cargo test

clean:
	cd desktop/src-tauri && cargo clean
	rm -rf desktop/dist
