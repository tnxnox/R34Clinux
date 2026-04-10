#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
CONTAINER_NAME="r34-flaresolverr"
FLARESOLVERR_IMAGE="ghcr.io/flaresolverr/flaresolverr:latest"
FLARESOLVERR_URL="http://127.0.0.1:8191"
CONTAINER_STARTED=0
PYTHON_BIN="python3"

log() {
  printf "[r34-launch] %s\n" "$*"
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

require_linux() {
  if [[ "${OSTYPE:-}" != linux* ]]; then
    log "This launcher currently supports Linux only."
    exit 1
  fi
}

require_python_version() {
  if ! has_command python3; then
    log "python3 was not found, attempting Python installation..."
    install_feature python
  fi

  if ! has_command python3 && has_command python; then
    PYTHON_BIN="python"
  fi

  if ! has_command "$PYTHON_BIN"; then
    log "A Python 3.11+ interpreter is required but was not found."
    exit 1
  fi

  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    log "Python 3.11+ is required. Please install/upgrade python3 and retry."
    exit 1
  fi
}

run_with_sudo() {
  if has_command sudo; then
    sudo "$@"
  else
    "$@"
  fi
}

install_system_packages() {
  local packages=("$@")

  if has_command apt-get; then
    log "Installing system packages with apt-get: ${packages[*]}"
    run_with_sudo apt-get update
    run_with_sudo apt-get install -y "${packages[@]}"
    return
  fi

  if has_command dnf; then
    log "Installing system packages with dnf: ${packages[*]}"
    run_with_sudo dnf install -y "${packages[@]}"
    return
  fi

  if has_command pacman; then
    log "Installing system packages with pacman: ${packages[*]}"
    run_with_sudo pacman -Sy --noconfirm "${packages[@]}"
    return
  fi

  log "No supported package manager found (apt-get, dnf, pacman)."
  log "Please install manually: ${packages[*]}"
  exit 1
}

package_manager() {
  if has_command apt-get; then
    printf "apt"
    return
  fi
  if has_command dnf; then
    printf "dnf"
    return
  fi
  if has_command pacman; then
    printf "pacman"
    return
  fi
  printf "unknown"
}

install_feature() {
  local feature="$1"
  local manager
  manager="$(package_manager)"

  case "$manager:$feature" in
    apt:python)
      install_system_packages python3 python3-venv python3-pip
      ;;
    dnf:python)
      install_system_packages python3 python3-pip
      ;;
    pacman:python)
      install_system_packages python python-pip
      ;;

    apt:docker)
      install_system_packages docker.io
      ;;
    dnf:docker)
      install_system_packages docker
      ;;
    pacman:docker)
      install_system_packages docker
      ;;

    apt:vlc)
      install_system_packages vlc libvlc-bin vlc-plugin-base
      ;;
    dnf:vlc)
      install_system_packages vlc
      ;;
    pacman:vlc)
      install_system_packages vlc
      ;;

    apt:curl|dnf:curl|pacman:curl)
      install_system_packages curl
      ;;

    *)
      log "Unsupported package manager or feature mapping: $manager / $feature"
      exit 1
      ;;
  esac
}

ensure_system_dependencies() {
  require_python_version

  if ! "$PYTHON_BIN" -m venv --help >/dev/null 2>&1; then
    install_feature python
  fi

  if ! has_command docker; then
    install_feature docker
  fi

  if ! has_command vlc; then
    install_feature vlc
  fi

  if ! has_command curl; then
    install_feature curl
  fi
}

ensure_docker_running() {
  if ! has_command docker; then
    log "docker command is still missing after dependency install."
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    log "Docker daemon is not running, attempting to start it..."
    if has_command systemctl; then
      # Docker on Ubuntu typically uses socket activation with -H fd://.
      run_with_sudo systemctl reset-failed docker.service docker.socket containerd.service || true
      run_with_sudo systemctl enable containerd docker.socket docker.service >/dev/null 2>&1 || true
      run_with_sudo systemctl start containerd.service || true
      run_with_sudo systemctl start docker.socket || true
      run_with_sudo systemctl start docker.service || true
    fi
  fi

  # Retry once more in case package post-install left units in a failed state.
  if ! docker info >/dev/null 2>&1 && has_command systemctl; then
    log "Retrying Docker startup sequence..."
    run_with_sudo systemctl restart containerd.service || true
    run_with_sudo systemctl restart docker.socket || true
    run_with_sudo systemctl restart docker.service || true
    sleep 2
  fi

  if ! docker info >/dev/null 2>&1; then
    log "Docker daemon is unavailable after automatic recovery."
    if has_command systemctl; then
      log "Run: sudo systemctl status docker.service --no-pager -l"
      log "Run: sudo systemctl status docker.socket --no-pager -l"
      log "Run: sudo journalctl -xeu docker.service --no-pager"
    fi
    exit 1
  fi
}

ensure_python_environment() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log "Creating Python virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  log "Installing Python dependencies..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
  "$VENV_DIR/bin/python" -m pip install -e "$PROJECT_DIR"
}

cleanup() {
  if [[ "$CONTAINER_STARTED" -eq 1 ]]; then
    log "Stopping FlareSolverr container..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}

wait_for_flaresolverr() {
  local retries=30

  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "$FLARESOLVERR_URL" >/dev/null 2>&1; then
      log "FlareSolverr is reachable at $FLARESOLVERR_URL"
      return 0
    fi
    sleep 1
  done

  log "FlareSolverr did not become ready in time."
  return 1
}

start_flaresolverr() {
  log "Preparing FlareSolverr container..."
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker pull "$FLARESOLVERR_IMAGE"

  docker run -d \
    --name "$CONTAINER_NAME" \
    --rm \
    -p 127.0.0.1:8191:8191 \
    "$FLARESOLVERR_IMAGE" >/dev/null

  CONTAINER_STARTED=1
  wait_for_flaresolverr
}

launch_app() {
  log "Launching R34 Linux Client..."
  "$VENV_DIR/bin/r34-linux-client"
}

main() {
  require_linux
  ensure_system_dependencies
  ensure_docker_running
  ensure_python_environment

  trap cleanup EXIT INT TERM
  start_flaresolverr
  launch_app
}

main "$@"
