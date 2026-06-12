#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "==========================================="
echo "  Rule34 Linux Client System Setup Script  "
echo "==========================================="

# Detect Package Manager
if [ -f /etc/debian_version ]; then
    PM="apt"
elif [ -f /etc/redhat-release ] || [ -f /etc/fedora-release ]; then
    PM="dnf"
elif [ -f /etc/arch-release ]; then
    PM="pacman"
else
    # Fallback/heuristic if release files aren't standard
    if command -v apt-get &>/dev/null; then PM="apt";
    elif command -v dnf &>/dev/null; then PM="dnf";
    elif command -v pacman &>/dev/null; then PM="pacman";
    fi
fi

# Install system dependencies
install_system_deps() {
    echo "Installing Tauri system build dependencies. You may be prompted for sudo password..."
    case "$PM" in
        apt)
            sudo apt update
            sudo apt install -y build-essential curl wget file libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev
            ;;
        dnf)
            sudo dnf groupinstall -y "Development Tools"
            sudo dnf install -y webkit2gtk4.1-devel openssl-devel gtk3-devel libappindicator-gtk3-devel librsvg2-devel
            ;;
        pacman)
            sudo pacman -Syu --needed --noconfirm base-devel webkit2gtk-4.1 openssl gtk3 libappindicator-gtk3 librsvg
            ;;
        *)
            echo "Warning: Could not detect your package manager (apt, dnf, pacman)."
            echo "Please manually install the system requirements for Tauri: https://tauri.app/v1/guides/getting-started/prerequisites"
            ;;
    esac
}

if [ -n "$PM" ]; then
    echo "Detected package manager: $PM"
    install_system_deps
else
    echo "Could not auto-detect package manager. Skipping system packages installation."
fi

# Check for Node.js and npm
echo ""
echo "Checking Node.js & npm..."
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
    echo "Error: Node.js and/or npm not found."
    echo "Please install Node.js (v18+) and npm using your package manager or nvm (Node Version Manager)."
    echo "Example (Ubuntu/Debian): sudo apt install nodejs npm"
    exit 1
else
    NODE_VERSION=$(node -v)
    echo "Found Node.js: $NODE_VERSION"
fi

# Check for Rust and Cargo
echo ""
echo "Checking Rust & Cargo..."
if ! command -v cargo &>/dev/null; then
    echo "Rust/Cargo not found. Would you like to install it now via rustup? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        # Source cargo environment
        source "$HOME/.cargo/env"
    else
        echo "Please install Rust manually from https://rustup.rs/ before running the app."
        exit 1
    fi
else
    RUST_VERSION=$(rustc --version)
    echo "Found Rust: $RUST_VERSION"
fi

# Check for Docker/Podman (optional)
echo ""
echo "Checking Docker & Podman (optional for FlareSolverr sync)..."
if ! command -v docker &>/dev/null && ! command -v podman &>/dev/null; then
    echo "Notice: Neither Docker nor Podman was found on your system."
    echo "If you plan to use Rule34 account favorites sync (requires FlareSolverr):"
    echo "  - Please install Docker (e.g., 'sudo apt install docker.io' / 'sudo dnf install docker')"
    echo "  - Ensure your user has permissions by running: 'sudo usermod -aG docker \$USER'"
    echo "  - Enable and start the service: 'sudo systemctl enable --now docker'"
    echo "Note: This is completely optional. Local favorites and downloads will work fine without it."
else
    if command -v docker &>/dev/null; then
        echo "Found Docker: $(docker --version)"
    else
        echo "Found Podman: $(podman --version)"
    fi
fi

# Install project frontend dependencies
echo ""
echo "Installing project dependencies (npm install)..."
SCRIPTPATH="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPTPATH")"

cd "$PROJECT_ROOT/desktop"
npm install

echo ""
echo "==========================================="
echo "  Setup completed successfully!            "
echo "  You can now start the app using:         "
echo "  ./start_r34.sh                           "
echo "==========================================="
