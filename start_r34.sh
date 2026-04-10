#!/usr/bin/env bash
set -euo pipefail

# Avoid entering an interactive REPL if PYTHONINSPECT is set in the shell environment.
unset PYTHONINSPECT PYTHONSTARTUP

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/r34-launcher.log"
CONTAINER_NAME="r34-flaresolverr"
FLARESOLVERR_IMAGE="ghcr.io/flaresolverr/flaresolverr:latest"
FLARESOLVERR_URL="http://127.0.0.1:8191"
CONTAINER_STARTED=0
PYTHON_BIN="python3"
DOCKER_USE_SUDO=0
LOGGING_INITIALIZED=0

log() {
  printf "[r34-launch] %s\n" "$*"
}

init_logging() {
  if [[ "$LOGGING_INITIALIZED" -eq 1 ]]; then
    return
  fi

  mkdir -p "$LOG_DIR"
  touch "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
  LOGGING_INITIALIZED=1
  log "Logging to $LOG_FILE"
}

configure_display_backend() {
  if [[ -n "${QT_QPA_PLATFORM:-}" ]]; then
    return
  fi

  if [[ "${XDG_SESSION_TYPE:-}" == "wayland" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    export QT_QPA_PLATFORM="xcb"
    log "Wayland session detected; forcing Qt to xcb for VLC video embedding."
  fi
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
  if has_command python3; then
    PYTHON_BIN="python3"
  elif has_command python; then
    PYTHON_BIN="python"
  else
    log "python3 was not found, attempting Python installation..."
    install_feature python
  fi

  if has_command python3; then
    PYTHON_BIN="python3"
  elif has_command python; then
    PYTHON_BIN="python"
  fi

  if ! has_command "$PYTHON_BIN"; then
    log "A Python 3.11+ interpreter is required but was not found."
    exit 1
  fi

  if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
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

docker_cmd() {
  if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
    run_with_sudo docker "$@"
  else
    docker "$@"
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
      install_system_packages vlc vlc-plugins-all
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

ensure_vlc_codec_support() {
  if ! has_command vlc; then
    install_feature vlc
    return
  fi

  if [[ "$(package_manager)" != "pacman" ]]; then
    return
  fi

  if pacman -Qq vlc-plugins-all >/dev/null 2>&1 || pacman -Qq vlc-plugin-ffmpeg >/dev/null 2>&1; then
    return
  fi

  log "Installing VLC codec plugins for H.264 playback..."
  install_system_packages vlc-plugins-all
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

  ensure_vlc_codec_support

  if ! has_command curl; then
    install_feature curl
  fi
}

ensure_docker_running() {
  local accessible=0

  if ! has_command docker; then
    log "docker command is still missing after dependency install."
    exit 1
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if has_command sudo && run_with_sudo docker info >/dev/null 2>&1; then
    DOCKER_USE_SUDO=1
    return 0
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

  if docker info >/dev/null 2>&1; then
    accessible=1
  elif has_command sudo && run_with_sudo docker info >/dev/null 2>&1; then
    DOCKER_USE_SUDO=1
    accessible=1
  fi

  if [[ "$accessible" -ne 1 ]]; then
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
  local recreate_venv=0

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    recreate_venv=1
  elif ! "$VENV_DIR/bin/python" -c 'import sys; print(sys.version)' >/dev/null 2>&1; then
    recreate_venv=1
  elif [[ -f "$VENV_DIR/bin/pip" ]] && ! grep -Fq "$VENV_DIR/bin/python" "$VENV_DIR/bin/pip"; then
    recreate_venv=1
  fi

  if [[ "$recreate_venv" -eq 1 ]]; then
    log "Recreating Python virtual environment (stale or invalid venv detected)..."
    rm -rf "$VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log "Virtual environment python is unavailable after venv creation."
    exit 1
  fi

  if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    log "Bootstrapping pip in virtual environment..."
    "$VENV_DIR/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi

  if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    log "pip is unavailable in the virtual environment. Install python3-venv/python3-pip and retry."
    exit 1
  fi

  log "Installing Python dependencies..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
  "$VENV_DIR/bin/python" -m pip install -e "$PROJECT_DIR"
}

cleanup() {
  if [[ "$CONTAINER_STARTED" -eq 1 ]]; then
    log "Stopping FlareSolverr container..."
    docker_cmd stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
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
  docker_cmd rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker_cmd pull "$FLARESOLVERR_IMAGE"

  docker_cmd run -d \
    --name "$CONTAINER_NAME" \
    --rm \
    -p 127.0.0.1:8191:8191 \
    "$FLARESOLVERR_IMAGE" >/dev/null

  CONTAINER_STARTED=1
  wait_for_flaresolverr
}

launch_app() {
  log "Launching R34 Linux Client..."
  "$VENV_DIR/bin/python" -m r34_client
}

main() {
  init_logging
  configure_display_backend
  require_linux
  ensure_system_dependencies
  ensure_docker_running
  ensure_python_environment

  trap cleanup EXIT INT TERM
  start_flaresolverr
  launch_app
}

main "$@"
