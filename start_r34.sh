#!/usr/bin/env bash

set -e

SCRIPTPATH="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"

# Source Rust/Cargo environment if it exists (e.g. installed via rustup but not in current shell path)
if [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi

# Verify prerequisites
MISSING_PREREQ=false

if ! command -v cargo &>/dev/null; then
    echo "Rust/Cargo is missing."
    MISSING_PREREQ=true
fi

if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
    echo "Node.js/npm is missing."
    MISSING_PREREQ=true
fi

# Check Webkit2gtk dev library on Linux
if [ "$(uname)" = "Linux" ]; then
    if ! command -v pkg-config &>/dev/null || ! pkg-config --exists webkit2gtk-4.1; then
        echo "Tauri system dependencies (WebKit2GTK development libraries) appear to be missing."
        MISSING_PREREQ=true
    fi
fi

if [ "$MISSING_PREREQ" = true ]; then
    echo "===================================================="
    echo "  Automated system dependency installer needed      "
    echo "===================================================="
    bash "$SCRIPTPATH/scripts/setup.sh"
    # Source env again in case setup.sh just installed rustup
    if [ -f "$HOME/.cargo/env" ]; then
        . "$HOME/.cargo/env"
    fi
else
    # Auto install npm packages if node_modules is missing
    if [ ! -d "$SCRIPTPATH/desktop/node_modules" ]; then
        echo "Installing frontend dependencies..."
        cd "$SCRIPTPATH/desktop"
        npm install
        cd "$SCRIPTPATH"
    fi
fi

# Run the app
echo "Launching Rule34 Client..."
cd "$SCRIPTPATH"
make dev

