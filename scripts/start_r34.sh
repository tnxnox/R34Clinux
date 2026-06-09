#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail
IFS=$'\n\t'

# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/share}/r34-client"
LOG_FILE="$LOG_DIR/launcher.log"

FLARESOLVERR_IMAGE="ghcr.io/flaresolverr/flaresolverr:latest"
FLARESOLVERR_URL="http://127.0.0.1:8191"
FLARESOLVERR_PORT=8191
CONTAINER_NAME="r34-flaresolverr"

# ─── Helpers ───────────────────────────────────────────────────────────────────

log()       { printf "\033[36m[r34]\033[0m %s\n" "$*"; }
warn()      { printf "\033[33m[r34] ⚠  %s\n\033[0m" "$*"; }
error()     { printf "\033[31m[r34] ✖  %s\n\033[0m" "$*"; }
success()   { printf "\033[32m[r34] ✓  %s\n\033[0m" "$*"; }
section()   { printf "\n\033[1;34m━━━ %s ━━━\033[0m\n\n" "$*"; }

has_cmd()   { command -v "$1" >/dev/null 2>&1; }
safe_run()  { "$@" 2>/dev/null || true; }

log_file() {
  printf "[r34] %s %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG_FILE"
}

log_both() {
  log "$*"
  log_file "$*"
}

# ─── Distro detection ─────────────────────────────────────────────────────────

PKG_MANAGER=""
PKG_INSTALL=""
PKG_UPDATE=""
DISTRO_NAME=""

detect_distro() {
  # Read /etc/os-release for a friendly name
  if [[ -f /etc/os-release ]]; then
    DISTRO_NAME="$(grep -oP 'PRETTY_NAME="\K[^"]+' /etc/os-release 2>/dev/null || true)"
  fi
  DISTRO_NAME="${DISTRO_NAME:-Linux}"

  if has_cmd apt-get; then
    PKG_MANAGER="apt"
    PKG_UPDATE="apt-get update -qq"
    PKG_INSTALL="apt-get install -y -qq"
  elif has_cmd dnf; then
    PKG_MANAGER="dnf"
    PKG_UPDATE="dnf check-update -q || true"
    PKG_INSTALL="dnf install -y"
  elif has_cmd pacman; then
    PKG_MANAGER="pacman"
    PKG_UPDATE="pacman -Sy"
    PKG_INSTALL="pacman -S --noconfirm"
  elif has_cmd zypper; then
    PKG_MANAGER="zypper"
    PKG_UPDATE="zypper refresh"
    PKG_INSTALL="zypper install -y"
  elif has_cmd apk; then
    PKG_MANAGER="apk"
    PKG_UPDATE="apk update"
    PKG_INSTALL="apk add"
  fi
}

run_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"
  elif has_cmd sudo; then sudo "$@"
  else
    warn "This step needs root, but sudo isn't available."
    warn "Run manually: $*"
    return 1
  fi
}

install_pkg() {
  local pkgs=("$@")
  if [[ -z "$PKG_MANAGER" ]]; then
    warn "No package manager detected. Install manually: ${pkgs[*]}"
    return 1
  fi
  log_both "Installing: ${pkgs[*]} (via $PKG_MANAGER)"
  local rc=0
  run_as_root $PKG_INSTALL "${pkgs[@]}" 2>&1 | tail -5 >>"$LOG_FILE" || rc=$?
  if [[ "$rc" -ne 0 ]]; then
    warn "Install failed. Try: run_as_root $PKG_INSTALL ${pkgs[*]}"
    return 1
  fi
  return 0
}

# ─── Logging setup ────────────────────────────────────────────────────────────

setup_logging() {
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  touch "$LOG_FILE" 2>/dev/null || true
  log_file "=== Launcher started ==="
}

# ─── Python ────────────────────────────────────────────────────────────────────

PYTHON_BIN=""

find_python() {
  local candidates=("python3" "python3.12" "python3.11" "python")
  for c in "${candidates[@]}"; do
    if has_cmd "$c"; then
      local ver
      ver="$("$c" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      local major="${ver%%.*}"
      local minor="${ver#*.}"
      if [[ "$major" -ge 3 && "$minor" -ge 11 ]] 2>/dev/null; then
        PYTHON_BIN="$c"
        return 0
      fi
    fi
  done
  return 1
}

ensure_python() {
  if find_python; then
    log_both "Python: $("$PYTHON_BIN" --version 2>&1)"
    return 0
  fi

  warn "Python 3.11+ not found. Trying to install..."
  case "$PKG_MANAGER" in
    apt)    install_pkg python3 python3-venv python3-pip ;;
    dnf|yum) install_pkg python3 python3-pip ;;
    pacman) install_pkg python python-pip ;;
    zypper) install_pkg python3 python3-pip ;;
    apk)    install_pkg python3 py3-pip ;;
  esac

  if ! find_python; then
    error "Could not find or install Python 3.11+."
    error "Install it manually (https://python.org) and re-run."
    exit 1
  fi
  log_both "Python installed: $("$PYTHON_BIN" --version 2>&1)"
}

# ─── Virtual environment ──────────────────────────────────────────────────────

ensure_venv() {
  if [[ -d "$VENV_DIR" ]]; then
    log_both "Virtual environment: $VENV_DIR (exists)"
    return 0
  fi
  log_both "Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  success "Virtual environment created."
}

ensure_deps() {
  log_both "Checking dependencies..."
  local pip_checksum="$VENV_DIR/.pip-installed"

  # Re-run if checksum doesn't match pyproject.toml or setup.py
  local src_checksum
  if [[ -f "$PROJECT_DIR/pyproject.toml" ]]; then
    src_checksum="$(md5sum "$PROJECT_DIR/pyproject.toml" 2>/dev/null | cut -d' ' -f1 || true)"
  else
    src_checksum="0"
  fi

  if [[ -f "$pip_checksum" ]] && [[ "$(cat "$pip_checksum" 2>/dev/null || true)" == "$src_checksum" ]]; then
    log_both "Dependencies up to date."
    return 0
  fi

  log_both "Installing project and dependencies..."
  "$VENV_DIR/bin/pip" install -q --upgrade pip >>"$LOG_FILE" 2>&1 || true
  "$VENV_DIR/bin/pip" install -q -e "$PROJECT_DIR" >>"$LOG_FILE" 2>&1 || {
    error "Failed to install dependencies."
    error "Check $LOG_FILE for details."
    error "Try manually: cd $PROJECT_DIR && .venv/bin/pip install -e ."
    exit 1
  }
  echo "$src_checksum" >"$pip_checksum"
  success "Dependencies installed."
}

# ─── VLC ──────────────────────────────────────────────────────────────────────

check_vlc() {
  if has_cmd vlc; then
    log_both "VLC: found"
    return 0
  fi
  warn "VLC not found. Video playback won't work."
  warn "Install VLC from https://videolan.org or your package manager."
}

# ─── Container runtime ────────────────────────────────────────────────────────

CONTAINER_CMD=""

detect_container_runtime() {
  if has_cmd podman; then
    CONTAINER_CMD="podman"
    return 0
  fi
  if has_cmd docker; then
    # Check if we can talk to docker daemon
    if docker info >/dev/null 2>&1; then
      CONTAINER_CMD="docker"
      return 0
    fi
    # Try with sudo
    if sudo -n docker info >/dev/null 2>&1; then
      CONTAINER_CMD="sudo docker"
      return 0
    fi
    warn "Docker is installed but not accessible."
    warn "Either add your user to the docker group:"
    warn "  sudo usermod -aG docker $USER && newgrp docker"
    warn "Or use passwordless sudo for docker."
    return 1
  fi
  warn "Neither Docker nor Podman found."
  warn "FlareSolverr sync won't be available without a container runtime."
  return 1
}

ensure_container_runtime() {
  if detect_container_runtime; then
    log_both "Container runtime: $CONTAINER_CMD"
    return 0
  fi

  warn "FlareSolverr favorites sync requires Docker or Podman."
  warn "Install with your package manager, e.g.:"
  case "$PKG_MANAGER" in
    apt)    warn "  sudo apt-get install docker.io" ;;
    dnf)    warn "  sudo dnf install docker" ;;
    pacman) warn "  sudo pacman -S docker" ;;
    zypper) warn "  sudo zypper install docker" ;;
    apk)    warn "  sudo apk add docker" ;;
    *)      warn "  https://podman.io/docs/installation" ;;
  esac
  warn "Then re-run this script."
}

# ─── FlareSolverr ──────────────────────────────────────────────────────────────

run_container() {
  $CONTAINER_CMD run -d \
    --name "$CONTAINER_NAME" \
    --restart no \
    -p "$FLARESOLVERR_PORT:8191" \
    -e LOG_LEVEL=info \
    "$FLARESOLVERR_IMAGE" >/dev/null 2>>"$LOG_FILE" || {
    error "Failed to start FlareSolverr container."
    error "Check $LOG_FILE for details."
    return 1
  }

  # Wait for it to be ready
  local waited=0
  while [[ "$waited" -lt 30 ]]; do
    if curl -sf "$FLARESOLVERR_URL/status" -o /dev/null 2>/dev/null; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  error "FlareSolverr container started but didn't respond within 30s."
  error "Check $LOG_FILE for details."
  return 1
}

start_flaresolverr() {
  # Skip if FlareSolverr is already running
  if curl -sf "$FLARESOLVERR_URL/status" -o /dev/null 2>/dev/null; then
    log_both "FlareSolverr: already running"
    return 0
  fi

  # Check if container exists and start it
  if $CONTAINER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER_NAME"; then
    log_both "Starting existing FlareSolverr container..."
    $CONTAINER_CMD start "$CONTAINER_NAME" >/dev/null 2>>"$LOG_FILE" || {
      warn "Failed to start existing FlareSolverr container. Recreating..."
      $CONTAINER_CMD rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
      return 1
    }
    sleep 3
    if curl -sf "$FLARESOLVERR_URL/status" -o /dev/null 2>/dev/null; then
      success "FlareSolverr started."
      return 0
    fi
    return 1
  fi

  log_both "Starting FlareSolverr container..."

  # Try to pull first, silently
  $CONTAINER_CMD pull "$FLARESOLVERR_IMAGE" >>"$LOG_FILE" 2>&1 || {
    warn "Couldn't pull latest FlareSolverr image. Trying fallback tag..."
    local fallback_image="ghcr.io/flaresolverr/flaresolverr:v3.3.21"
    FLARESOLVERR_IMAGE="$fallback_image"
    $CONTAINER_CMD pull "$FLARESOLVERR_IMAGE" >>"$LOG_FILE" 2>&1 || {
      error "Failed to pull FlareSolverr image."
      error "Check your internet connection and container runtime."
      return 1
    }
  }

  run_container || return 1
  success "FlareSolverr started."
}

stop_flaresolverr() {
  if $CONTAINER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER_NAME"; then
    log_both "Stopping FlareSolverr container..."
    $CONTAINER_CMD rm -f "$CONTAINER_NAME" >/dev/null 2>>"$LOG_FILE" || true
    log_both "FlareSolverr stopped."
  fi
}

check_flaresolverr_enabled() {
  local conf="${XDG_CONFIG_HOME:-$HOME/.config}/R34LinuxClient/R34LinuxClient.conf"
  if [[ -f "$conf" ]]; then
    if grep -iq "^flaresolverr_enabled[[:space:]]*=[[:space:]]*true" "$conf"; then
      return 0
    fi
  fi
  return 1
}

# ─── Display ───────────────────────────────────────────────────────────────────

configure_display() {
  if [[ -n "${QT_QPA_PLATFORM:-}" ]]; then
    log_both "Display: QT_QPA_PLATFORM=$QT_QPA_PLATFORM (preserved)"
    return
  fi
  if [[ "${XDG_SESSION_TYPE:-}" == "wayland" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    export QT_QPA_PLATFORM="xcb"
    log_both "Display: Wayland detected, forced QT_QPA_PLATFORM=xcb (needed for VLC)"
  fi
}

# ─── Cleanup ────────────────────────────────────────────────────────────────────

cleanup() {
  local rc=$?
  echo ""
  log "Shutting down..."
  stop_flaresolverr
  log_file "=== Launcher exited (code $rc) ==="
  if [[ "$rc" -eq 0 ]]; then
    success "Done."
  else
    error "Exited with code $rc — check $LOG_FILE for details."
  fi
}

# ─── Main ──────────────────────────────────────────────────────────────────────

main() {
  section "R34 Linux Client Launcher"
  log "Log: $LOG_FILE"

  setup_logging
  detect_distro
  log_both "Distro: $DISTRO_NAME"

  configure_display

  # ── Python + venv ──
  ensure_python
  ensure_venv
  ensure_deps

  # ── Optional: VLC ──
  check_vlc

  # ── Optional: FlareSolverr ──
  ensure_container_runtime
  if [[ -n "$CONTAINER_CMD" ]]; then
    if check_flaresolverr_enabled; then
      start_flaresolverr || warn "FlareSolverr failed to start — sync won't be available."
    else
      log_both "FlareSolverr is disabled in settings. Skipping container start."
    fi
  fi

  # ── Launch ──
  echo ""
  log "Starting R34 Linux Client..."
  log_file "Launching application..."

  trap cleanup EXIT INT TERM

  exec "$VENV_DIR/bin/python" -m r34_client "$@"
}

main "$@"
