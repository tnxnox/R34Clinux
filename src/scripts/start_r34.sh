#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail
shopt -s nullglob

unset PYTHONINSPECT PYTHONSTARTUP

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/r34-launcher.log"

FLARESOLVERR_IMAGE="ghcr.io/flaresolverr/flaresolverr:latest"
FLARESOLVERR_URL="http://127.0.0.1:8191"
FLARESOLVERR_PORT=8191
CONTAINER_NAME="r34-flaresolverr"

CONTAINER_STARTED=0
APP_LAUNCHED=0

# ─── Logging ──────────────────────────────────────────────────────────────────

log()      { printf "[r34-launch] %s\n" "$*"; }
log_to_file() {
  printf "[r34-launch] %s %s\n" "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || true)" "$*" >>"$LOG_FILE" 2>/dev/null || true
}
log_both() { log "$*"; log_to_file "$*"; }

init_logging() {
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  touch "$LOG_FILE" 2>/dev/null || true
  log "Logging to $LOG_FILE"
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

has_command() { command -v "$1" >/dev/null 2>&1; }

safe_run() { "$@" 2>/dev/null || true; }

run_with_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"
  elif has_command sudo; then sudo "$@"
  else "$@"
  fi
}

log_stderr() {
  local out
  out="$(safe_run "$@" 2>&1)"
  local rc=$?
  printf "%s\n" "$out"
  return "$rc"
}

# ─── Display backend ──────────────────────────────────────────────────────────

configure_display_backend() {
  export LIBVA_DRIVER_NAME=""
  export VDPAU_DRIVER=""

  if [[ -n "${QT_QPA_PLATFORM:-}" ]]; then
    log_both "QT_QPA_PLATFORM already set to '$QT_QPA_PLATFORM'; keeping it."
    return
  fi

  if [[ "${XDG_SESSION_TYPE:-}" == "wayland" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    export QT_QPA_PLATFORM="xcb"
    log_both "Wayland detected; set QT_QPA_PLATFORM=xcb for VLC embedding."
  fi
}

# ─── Python ───────────────────────────────────────────────────────────────────

PYTHON_BIN=""

_find_python() {
  local candidates=("python3" "python3.14" "python3.13" "python3.12" "python3.11" "python")
  local ver

  for c in "${candidates[@]}"; do
    if has_command "$c"; then
      ver=$("$c" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0")
      if [[ "$(echo "$ver" | cut -d. -f1)" -ge 3 && "$(echo "$ver" | cut -d. -f2)" -ge 11 ]]; then
        PYTHON_BIN="$c"
        return 0
      fi
    fi
  done

  if has_command python; then
    ver=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0")
    if [[ "$(echo "$ver" | cut -d. -f1)" -ge 3 && "$(echo "$ver" | cut -d. -f2)" -ge 11 ]]; then
      PYTHON_BIN="python"
      return 0
    fi
  fi

  return 1
}

_install_python_via_conda() {
  if has_command conda; then
    log_both "Creating conda environment as Python fallback..."
    conda create -y -n r34-client python=3.12 pip 2>/dev/null || return 1
    PYTHON_BIN="$(conda run -n r34-client which python 2>/dev/null || true)"
    if [[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]]; then
      VENV_DIR="$PROJECT_DIR/.venv"
      "$PYTHON_BIN" -m venv "$VENV_DIR" 2>/dev/null || return 1
      return 0
    fi
  fi
  return 1
}

_install_python_via_pyenv() {
  if has_command pyenv; then
    log_both "Installing Python 3.12 via pyenv..."
    pyenv install -s 3.12.9 2>/dev/null || return 1
    PYTHON_BIN="$(pyenv prefix 3.12.9)/bin/python"
    return 0
  fi
  return 1
}

ensure_python() {
  if _find_python; then
    log_both "Found $("$PYTHON_BIN" --version 2>&1)"
    return 0
  fi

  log_both "No Python 3.11+ found. Trying automatic installation..."

  if _ensure_package_manager; then
    case "$PKG_MANAGER" in
      apt)    safe_run install_system_packages python3 python3-venv python3-pip ;;
      dnf)    safe_run install_system_packages python3 python3-pip ;;
      pacman) safe_run install_system_packages python python-pip ;;
      zypper) safe_run install_system_packages python3 python3-pip ;;
      apk)    safe_run install_system_packages python3 py3-pip ;;
      yum)    safe_run install_system_packages python3 python3-pip ;;
    esac
    if _find_python; then return 0; fi
  fi

  _install_python_via_conda && return 0
  _install_python_via_pyenv && return 0

  log_both "Could not find or install Python 3.11+."
  log_both "Install Python 3.11+ manually and retry."
  exit 1
}

# ─── Package management ───────────────────────────────────────────────────────

PKG_MANAGER=""
PKG_INSTALL=""

_ensure_package_manager() {
  if has_command apt-get; then
    PKG_MANAGER="apt"
    PKG_INSTALL="run_with_sudo apt-get install -y -qq"
    safe_run run_with_sudo apt-get update -qq
  elif has_command dnf; then
    PKG_MANAGER="dnf"
    PKG_INSTALL="run_with_sudo dnf install -y"
  elif has_command pacman; then
    PKG_MANAGER="pacman"
    PKG_INSTALL="run_with_sudo pacman -Sy --noconfirm"
  elif has_command zypper; then
    PKG_MANAGER="zypper"
    PKG_INSTALL="run_with_sudo zypper install -y"
  elif has_command apk; then
    PKG_MANAGER="apk"
    PKG_INSTALL="run_with_sudo apk add"
  elif has_command yum; then
    PKG_MANAGER="yum"
    PKG_INSTALL="run_with_sudo yum install -y"
  else
    PKG_MANAGER=""
    PKG_INSTALL=""
  fi
  [[ -n "$PKG_MANAGER" ]]
}

install_system_packages() {
  local packages=("$@")
  if [[ -z "$PKG_MANAGER" ]]; then
    log_both "No package manager found; install manually: ${packages[*]}"
    return 1
  fi
  log_both "Installing with $PKG_MANAGER: ${packages[*]}"
  local out rc
  out="$(eval "$PKG_INSTALL" "${packages[@]}" 2>&1)" || rc=$?
  if [[ "${rc:-0}" -ne 0 ]]; then
    if echo "$out" | grep -qi "password\|terminal\|askpass\|permission denied"; then
      log_both "Install failed: root/sudo required but unavailable (non-interactive)."
      log_both "Run manually: sudo pacman -S ${packages[*]}"
    fi
    return 1
  fi
  return 0
}

install_feature() {
  local feature="$1"
  case "$feature" in
    python)
      safe_run install_system_packages python3 python3-venv python3-pip
      safe_run install_system_packages python python-pip
      ;;
    docker)
      case "$PKG_MANAGER" in
        pacman)
          safe_run install_system_packages podman
          safe_run install_system_packages docker 2>/dev/null || true
          ;;
        apt)
          safe_run install_system_packages docker.io podman
          ;;
        dnf|zypper|yum)
          safe_run install_system_packages docker-ce docker-ce-cli containerd.io podman
          ;;
        apk)
          safe_run install_system_packages docker podman
          ;;
        *)
          safe_run install_system_packages docker.io docker-ce docker-ce-cli containerd.io
          safe_run install_system_packages docker docker-engine
          safe_run install_system_packages podman podman-docker
          ;;
      esac
      ;;
    vlc)
      safe_run install_system_packages vlc vlc-plugins-all vlc-plugin-base libvlc-bin
      safe_run install_system_packages vlc
      ;;
    curl)
      safe_run install_system_packages curl ca-certificates
      ;;
    nodejs)
      safe_run install_system_packages nodejs npm
      ;;
  esac
}

# ─── VLC ──────────────────────────────────────────────────────────────────────

ensure_vlc() {
  if has_command vlc; then
    if [[ "$PKG_MANAGER" == "pacman" ]]; then
      if ! pacman -Qq vlc-plugins-all >/dev/null 2>&1 && ! pacman -Qq vlc-plugin-ffmpeg >/dev/null 2>&1; then
        log_both "Installing VLC codec plugins..."
        safe_run install_system_packages vlc-plugins-all
      fi
    fi
    return 0
  fi

  log_both "VLC not found. Attempting installation..."
  install_feature vlc

  if ! has_command vlc; then
    log_both "VLC could not be installed. In-app video will be unavailable."
    log_both "Install VLC manually: https://www.videolan.org/vlc/"
  fi
}

# ─── curl ─────────────────────────────────────────────────────────────────────

ensure_curl() {
  if has_command curl; then return 0; fi
  log_both "curl not found. Installing..."
  install_feature curl
  if ! has_command curl; then
    log_both "curl could not be installed. FlareSolverr health checks will fail."
    log_both "Install curl manually: sudo pacman -S curl"
    return 1
  fi
}

# ─── Port management ──────────────────────────────────────────────────────────

_port_in_use() {
  local port="${1:-$FLARESOLVERR_PORT}"
  if has_command ss; then
    ss -tlnp "sport = :$port" 2>/dev/null | grep -q ":$port" && return 0
  fi
  if has_command netstat; then
    netstat -tlnp 2>/dev/null | grep -q ":$port " && return 0
  fi
  if has_command lsof; then
    lsof -i ":$port" >/dev/null 2>&1 && return 0
  fi
  # Try /proc/net/tcp as last resort
  if [[ -r /proc/net/tcp ]]; then
    local hex
    printf -v hex ":%04X" "$port"
    grep -q "$hex" /proc/net/tcp 2>/dev/null && return 0
  fi
  return 1
}

_free_port() {
  local port="${1:-$FLARESOLVERR_PORT}"
  if ! _port_in_use "$port"; then return 0; fi

  log_both "Port $port is in use. Attempting to identify and free it..."

  # Try to find PID using the port
  local pid=""
  if has_command ss; then
    pid=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1 || true)
  fi
  if [[ -z "$pid" ]] && has_command lsof; then
    pid=$(lsof -t -i ":$port" 2>/dev/null | head -1 || true)
  fi

  if [[ -n "$pid" ]]; then
    local pname
    pname="$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")"
    log_both "Process $pid ($pname) is using port $port. Attempting to stop it..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      log_both "Process $pid did not stop. Using force (SIGKILL)..."
      kill -9 "$pid" 2>/dev/null || true
      sleep 1
    fi
    if _port_in_use "$port"; then
      log_both "Could not free port $port."
      return 1
    fi
    log_both "Port $port freed."
    return 0
  fi

  # No PID found but port is in use - likely owned by another user or kernel
  log_both "Port $port is reserved but no owning process found."
  log_both "Try: sudo lsof -i :$port"
  return 1
}

# ─── Container runtime ────────────────────────────────────────────────────────

CONTAINER_RUNTIME=""
CONTAINER_SUDO=0

_detect_container_runtime() {
  if has_command podman; then
    CONTAINER_RUNTIME="podman"
    return 0
  fi
  if has_command docker; then
    CONTAINER_RUNTIME="docker"
    return 0
  fi
  return 1
}

DOCKER_ACCESS_DENIED=0

_container_accessible() {
  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then return 0; fi

  local info_out
  info_out="$(docker info 2>&1)" || true

  # Check if daemon is running but user lacks permission
  if echo "$info_out" | grep -qi "permission denied"; then
    DOCKER_ACCESS_DENIED=1
    return 1
  fi
  DOCKER_ACCESS_DENIED=0

  if echo "$info_out" | grep -qi "server version"; then
    CONTAINER_SUDO=0
    return 0
  fi

  # Try with sudo (works if user has passwordless sudo or NOPASSWD rule)
  local sudo_out
  if has_command sudo; then
    sudo_out="$(run_with_sudo docker info 2>&1)" || true
    if echo "$sudo_out" | grep -qi "server version"; then
      CONTAINER_SUDO=1
      return 0
    fi
  fi

  return 1
}

container_cmd() {
  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then podman "$@"
  elif [[ "$CONTAINER_SUDO" -eq 1 ]]; then run_with_sudo docker "$@"
  else docker "$@"
  fi
}

_check_docker_group() {
  if id -nG "$USER" 2>/dev/null | grep -qw docker; then return 0; fi
  log_both "User '$USER' is not in the 'docker' group."
  log_both "Docker daemon is running but you lack socket access."
  log_both ""
  log_both "To fix Docker access, run ONE of these:"
  log_both "  sudo usermod -aG docker $USER && newgrp docker"
  log_both "  sudo chmod 666 /var/run/docker.sock  (less secure, immediate)"
  log_both ""
  log_both "Script will try Podman as an alternative..."
  return 1
}

_try_add_to_docker_group() {
  if id -nG "$USER" 2>/dev/null | grep -qw docker; then return 0; fi

  # Attempt non-interactive sudo to add user to group
  if has_command sudo; then
    if sudo -n usermod -aG docker "$USER" 2>/dev/null; then
      log_both "Added user to docker group (via sudo -n)."
      log_both "A new login shell is needed for this to take effect."
      log_both "For now, trying alternative access methods..."
      return 0
    fi
    # Check if passwordless sudo is available for specific commands
    if sudo -l docker 2>/dev/null | grep -qi NOPASSWD; then
      CONTAINER_SUDO=1
      log_both "User has passwordless sudo for docker. Will use sudo."
      return 0
    fi
  fi

  # Last resort: try to make socket world-accessible (less secure but immediate)
  if has_command sudo; then
    if sudo -n chmod 666 /var/run/docker.sock 2>/dev/null; then
      log_both "Made Docker socket world-accessible (chmod 666)."
      log_both "Consider adding user to docker group instead for security."
      return 0
    fi
  fi

  return 1
}

_fix_docker_storage() {
  log_both "Attempting to repair Docker storage..."

  # Step 1: Prune (safest)
  log_both "Step 1: docker system prune..."
  if run_with_sudo docker system prune -af --volumes 2>/dev/null; then
    log_both "Prune succeeded. Retrying daemon..."
    safe_run run_with_sudo systemctl restart docker
    sleep 2
    if _container_accessible; then return 0; fi
  fi

  # Step 2: Stop Docker, remove corrupted container metadata
  log_both "Step 2: Stopping Docker to repair container metadata..."
  safe_run run_with_sudo systemctl stop docker docker.socket containerd 2>/dev/null
  safe_run run_with_sudo service docker stop 2>/dev/null
  safe_run run_with_sudo pkill -9 dockerd 2>/dev/null || true
  sleep 1

  # Remove just the containers directory (less destructive)
  if [[ -d /var/lib/docker/containers ]]; then
    log_both "Removing /var/lib/docker/containers (containers will be lost but images preserved)..."
    safe_run run_with_sudo rm -rf /var/lib/docker/containers
  fi

  # Also remove corrupted overlay2 metadata if present
  if [[ -d /var/lib/docker/overlay2 ]]; then
    log_both "Cleaning overlay2 metadata..."
    safe_run run_with_sudo rm -rf /var/lib/docker/overlay2/*-removing 2>/dev/null
    safe_run run_with_sudo rm -rf /var/lib/docker/overlay2/*/merged 2>/dev/null
  fi

  safe_run run_with_sudo systemctl reset-failed docker docker.socket containerd 2>/dev/null
  safe_run run_with_sudo systemctl start containerd 2>/dev/null
  safe_run run_with_sudo systemctl start docker.socket 2>/dev/null
  safe_run run_with_sudo systemctl start docker 2>/dev/null
  sleep 3

  if _container_accessible; then
    log_both "Docker storage repair succeeded."
    return 0
  fi

  # Step 3: Nuclear option - backup and recreate docker storage
  log_both "Step 3: Nuclear repair - recreating Docker storage..."
  safe_run run_with_sudo systemctl stop docker docker.socket containerd 2>/dev/null
  safe_run run_with_sudo service docker stop 2>/dev/null
  safe_run run_with_sudo pkill -9 dockerd 2>/dev/null || true
  sleep 1

  local backup="/var/lib/docker.backup.$(date +%s)"
  log_both "Backing up /var/lib/docker to $backup..."
  safe_run run_with_sudo mv /var/lib/docker "$backup"
  safe_run run_with_sudo mkdir -p /var/lib/docker

  safe_run run_with_sudo systemctl start containerd 2>/dev/null
  safe_run run_with_sudo systemctl start docker 2>/dev/null
  sleep 3

  if _container_accessible; then
    log_both "Nuclear repair succeeded. All Docker images/containers were reset."
    log_both "Backup of old data: $backup"
    return 0
  fi

  log_both "Docker storage repair failed."
  log_both "Backup of old data: $backup"
  return 1
}

_ensure_container_runtime() {
  if _detect_container_runtime; then
    log_both "Using $CONTAINER_RUNTIME as container runtime."
    return 0
  fi

  log_both "No container runtime found (docker/podman). Trying to install..."
  install_feature docker

  if _detect_container_runtime; then
    log_both "Installed $CONTAINER_RUNTIME."
    return 0
  fi

  log_both "Could not install Docker or Podman through package manager."
  log_both "Trying Podman standalone..."
  install_feature podman 2>/dev/null || true

  if has_command podman; then
    CONTAINER_RUNTIME="podman"
    log_both "Installed Podman."
    return 0
  fi

  log_both "FlareSolverr favorites sync will be unavailable."
  log_both "Install Podman: https://podman.io/docs/installation"
  return 1
}

_start_docker_daemon() {
  if _container_accessible; then return 0; fi
  if [[ "$CONTAINER_RUNTIME" != "docker" ]]; then return 0; fi

  log_both "Docker daemon not accessible. Diagnosing..."

  # Case 1: Daemon is running but user can't access socket
  if [[ "$DOCKER_ACCESS_DENIED" -eq 1 ]]; then
    log_both "Docker daemon is RUNNING but user lacks socket permission."
    _check_docker_group

    if _try_add_to_docker_group; then
      if _container_accessible; then
        log_both "Docker access restored."
        return 0
      fi
    fi

    log_both "Docker not usable due to permissions."
    log_both "Switch to Podman or fix Docker permissions as shown above."
    return 1
  fi

  # Case 2: Daemon not reachable - capture error details
  local err
  err="$(docker info 2>&1)" || true
  log_both "Docker error: $(echo "$err" | head -5 | tr '\n' ' ')"

  if echo "$err" | grep -qi "read-only file system"; then
    log_both "Detected Docker storage corruption (read-only file system)."
    _fix_docker_storage && return 0
  fi

  if echo "$err" | grep -qi "connect: connection refused\|no such host\|cannot connect"; then
    log_both "Docker daemon is not running."
  fi

  log_both "Attempting to start Docker daemon..."

  # Try systemd
  if has_command systemctl; then
    safe_run run_with_sudo systemctl reset-failed docker.service docker.socket containerd.service 2>/dev/null
    safe_run run_with_sudo systemctl enable containerd docker.socket docker.service 2>/dev/null
    safe_run run_with_sudo systemctl start containerd.service 2>/dev/null
    safe_run run_with_sudo systemctl start docker.socket 2>/dev/null
    safe_run run_with_sudo systemctl start docker.service 2>/dev/null
    sleep 3
    if _container_accessible; then return 0; fi
    safe_run run_with_sudo systemctl restart containerd.service 2>/dev/null
    safe_run run_with_sudo systemctl restart docker.service 2>/dev/null
    sleep 3
    if _container_accessible; then return 0; fi
  fi

  # Try service command (init.d systems)
  if has_command service; then
    safe_run run_with_sudo service docker start
    sleep 3
    if _container_accessible; then return 0; fi
  fi

  # Try starting dockerd directly (rootless setups)
  if has_command dockerd-rootless-setuptool.sh; then
    log_both "Setting up rootless Docker..."
    safe_run dockerd-rootless-setuptool.sh install
    sleep 3
    if _container_accessible; then return 0; fi
  fi

  # Start dockerd directly
  if has_command dockerd; then
    log_both "Starting dockerd directly (may take 8-10 seconds)..."
    run_with_sudo bash -c 'nohup dockerd >/dev/null 2>&1 &' 2>/dev/null || true
    sleep 8
    if _container_accessible; then
      log_both "Docker daemon started successfully."
      return 0
    fi
  fi

  log_both "Could not start Docker daemon."
  return 1
}

# ─── Python venv ──────────────────────────────────────────────────────────────

_ensure_venv_pip() {
  if "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then return 0; fi

  log_both "pip not found in venv. Trying ensurepip..."
  safe_run "$VENV_DIR/bin/python" -m ensurepip --upgrade
  if "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then return 0; fi

  log_both "ensurepip failed. Trying get-pip.py..."
  safe_run curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  if [[ -f /tmp/get-pip.py ]]; then
    safe_run "$VENV_DIR/bin/python" /tmp/get-pip.py --quiet
    rm -f /tmp/get-pip.py
  fi
  if "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then return 0; fi

  log_both "pip bootstrap failed. Trying system package manager..."
  if [[ -n "$PKG_MANAGER" ]]; then
    case "$PKG_MANAGER" in
      apt)    safe_run install_system_packages python3-pip python3-venv ;;
      pacman) safe_run install_system_packages python-pip ;;
      dnf)    safe_run install_system_packages python3-pip ;;
    esac
  fi

  if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    log_both "Recreating venv with --system-site-packages..."
    rm -rf "$VENV_DIR"
    "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
  fi

  "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1
}

ensure_venv() {
  local recreate=0

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    recreate=1
  elif ! "$VENV_DIR/bin/python" -c 'import sys; print(sys.version)' >/dev/null 2>&1; then
    recreate=1
  fi

  if [[ "$recreate" -eq 1 ]]; then
    log_both "Creating Python virtual environment..."

    if ! "$PYTHON_BIN" -m venv "$VENV_DIR" 2>/dev/null; then
      log_both "Standard venv failed. Trying --without-pip..."
      rm -rf "$VENV_DIR"
      "$PYTHON_BIN" -m venv --without-pip "$VENV_DIR" 2>/dev/null || {
        log_both "venv module unavailable. Trying virtualenv..."
        if has_command virtualenv; then
          virtualenv "$VENV_DIR"
        else
          safe_run pip3 install --user virtualenv
          has_command virtualenv && virtualenv "$VENV_DIR"
        fi
      }
    fi
  fi

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log_both "Virtual environment creation failed."
    log_both "Falling back: installing packages directly with --user..."
    safe_run "$PYTHON_BIN" -m pip install --user --upgrade pip setuptools wheel
    safe_run "$PYTHON_BIN" -m pip install --user -e "$PROJECT_DIR"
    log_both "Installed with --user flag. Launching directly..."
    APP_PYTHON="$PYTHON_BIN"
    APP_EXTRA_ARGS="--user-install"
    return 0
  fi

  log_both "Virtual environment ready at $VENV_DIR"
  _ensure_venv_pip || log_both "pip still unavailable; continuing anyway."

  log_both "Installing project dependencies..."
  safe_run "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel --quiet
  safe_run "$VENV_DIR/bin/python" -m pip install -e "$PROJECT_DIR" --quiet
  log_both "Dependencies installed."
}

# ─── FlareSolverr ─────────────────────────────────────────────────────────────

_wait_for_flaresolverr() {
  local retries=30
  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "$FLARESOLVERR_URL" >/dev/null 2>&1; then
      log_both "FlareSolverr is reachable at $FLARESOLVERR_URL"
      return 0
    fi
    sleep 1
  done
  return 1
}

_try_container_pull() {
  local image="$1"
  log_both "Pulling $image..."

  # Try normal pull
  if container_cmd pull "$image" >/dev/null 2>&1; then
    log_both "Image pull succeeded."
    return 0
  fi

  # If pull failed, try --pull=never (use cached image)
  if container_cmd inspect "$image" >/dev/null 2>&1; then
    log_both "Using cached image."
    return 0
  fi

  return 1
}

_try_container_run() {
  local image="$1"
  shift

  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
    # Podman: try with --security-opt label=disable for SELinux compat
    if container_cmd run -d --name "$CONTAINER_NAME" --rm \
      -p "127.0.0.1:$FLARESOLVERR_PORT:$FLARESOLVERR_PORT" \
      --security-opt label=disable \
      "$@" \
      "$image" 2>/dev/null; then
      CONTAINER_STARTED=1
      return 0
    fi

    # Retry without security opt
    safe_run container_cmd rm -f "$CONTAINER_NAME"
    if container_cmd run -d --name "$CONTAINER_NAME" --rm \
      -p "127.0.0.1:$FLARESOLVERR_PORT:$FLARESOLVERR_PORT" \
      "$@" \
      "$image" 2>/dev/null; then
      CONTAINER_STARTED=1
      return 0
    fi
  else
    # Docker standard run
    safe_run container_cmd rm -f "$CONTAINER_NAME"
    if container_cmd run -d --name "$CONTAINER_NAME" --rm \
      -p "127.0.0.1:$FLARESOLVERR_PORT:$FLARESOLVERR_PORT" \
      "$@" \
      "$image" 2>/dev/null; then
      CONTAINER_STARTED=1
      return 0
    fi
  fi

  return 1
}

_try_flaresolverr_npx() {
  log_both "Trying FlareSolverr via npm..."

  if ! has_command node; then
    log_both "Node.js not found. Trying to install..."
    install_feature nodejs 2>/dev/null || true
  fi
  if ! has_command node; then return 1; fi

  log_both "Installing flaresolverr via npm (experimental)..."
  safe_run npm install -g flaresolverr 2>/dev/null || true

  if has_command flaresolverr 2>/dev/null; then
    FLARESOLVERR_URL="http://127.0.0.1:$FLARESOLVERR_PORT"
    log_both "Starting flaresolverr..."
    safe_run flaresolverr --port "$FLARESOLVERR_PORT" &
    local fs_pid=$!
    disown "$fs_pid" 2>/dev/null || true
    if _wait_for_flaresolverr; then
      log_both "FlareSolverr running directly (PID $fs_pid)."
      return 0
    fi
    kill "$fs_pid" 2>/dev/null || true
  fi

  return 1
}

_try_flaresolverr_direct_pip() {
  log_both "Trying FlareSolverr via pip..."
  safe_run pip3 install flaresolverr 2>/dev/null || true
  if has_command flaresolverr 2>/dev/null; then
    safe_run flaresolverr &
    sleep 3
    if _wait_for_flaresolverr; then
      log_both "FlareSolverr running via pip install."
      return 0
    fi
  fi
  return 1
}

_try_podman_fallback() {
  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then return 1; fi

  log_both "Docker failed. Trying Podman as fallback..."

  if ! has_command podman; then
    log_both "Podman not found. Attempting install..."
    install_system_packages podman 2>/dev/null || true
  fi

  if has_command podman; then
    CONTAINER_RUNTIME="podman"
    CONTAINER_SUDO=0
    log_both "Switched to Podman."

    # Free port again (previous container run may have left it dirty)
    _free_port "$FLARESOLVERR_PORT" || true

    # Retry with Podman
    log_both "Starting FlareSolverr via Podman..."
    safe_run container_cmd rm -f "$CONTAINER_NAME" 2>/dev/null || true

    if _try_container_pull "$FLARESOLVERR_IMAGE"; then
      if _try_container_run "$FLARESOLVERR_IMAGE"; then
        if _wait_for_flaresolverr; then
          log_both "FlareSolverr running via Podman."
          return 0
        fi
      fi
    fi

    # Try host networking with Podman
    log_both "Podman bridge mode failed. Trying host networking..."
    safe_run container_cmd rm -f "$CONTAINER_NAME"
    if container_cmd run -d --name "$CONTAINER_NAME" --rm \
      --network host \
      "$FLARESOLVERR_IMAGE" 2>/dev/null; then
      CONTAINER_STARTED=1
      FLARESOLVERR_URL="http://127.0.0.1:$FLARESOLVERR_PORT"
      if _wait_for_flaresolverr; then
        log_both "FlareSolverr running via Podman (host network)."
        return 0
      fi
    fi
  fi

  return 1
}

# ─── FlareSolverr startup (multi-tier fallback) ───────────────────────────────

start_flaresolverr() {
  ensure_curl || true

  # ── Tier 1: Already reachable ──────────────────────────────────────────────
  if curl -fsS "$FLARESOLVERR_URL" >/dev/null 2>&1; then
    log_both "FlareSolverr is already running at $FLARESOLVERR_URL"
    return 0
  fi

  # Free port if occupied by non-FlareSolverr process
  _free_port "$FLARESOLVERR_PORT" || true

  # ── Tier 2: Existing container already running ─────────────────────────────
  if [[ -n "$CONTAINER_RUNTIME" ]]; then
    if container_cmd ps --filter "name=$CONTAINER_NAME" --filter "status=running" --format "{{.Names}}" 2>/dev/null | grep -qF "$CONTAINER_NAME"; then
      log_both "FlareSolverr container is running. Waiting for it..."
      _wait_for_flaresolverr && return 0
      log_both "Container running but not responding; restarting..."
      safe_run container_cmd restart "$CONTAINER_NAME"
      _wait_for_flaresolverr && return 0
    fi

    # Remove dead container
    safe_run container_cmd rm -f "$CONTAINER_NAME" 2>/dev/null || true
  fi

  # ── Tier 3: Start with primary container runtime ───────────────────────────
  if [[ -n "$CONTAINER_RUNTIME" ]]; then
    log_both "Starting FlareSolverr via $CONTAINER_RUNTIME..."

    # Try pulling the image with tag fallback
    local images=(
      "$FLARESOLVERR_IMAGE"
      "ghcr.io/flaresolverr/flaresolverr:v3.3.21"
      "ghcr.io/flaresolverr/flaresolverr:v3.3.20"
      "ghcr.io/flaresolverr/flaresolverr:v3.3.19"
    )
    local pulled_image=""

    for img in "${images[@]}"; do
      if _try_container_pull "$img"; then
        pulled_image="$img"
        break
      fi
      log_both "Image $img not available."
    done

    if [[ -z "$pulled_image" ]]; then
      # Last try: maybe the image is already cached under 'latest'
      if container_cmd inspect "$FLARESOLVERR_IMAGE" >/dev/null 2>&1; then
        pulled_image="$FLARESOLVERR_IMAGE"
        log_both "Using cached $FLARESOLVERR_IMAGE despite pull failure."
      fi
    fi

    if [[ -n "$pulled_image" ]]; then
      # Try normal port-mapped run
      if _try_container_run "$pulled_image"; then
        if _wait_for_flaresolverr; then
          log_both "FlareSolverr running via $CONTAINER_RUNTIME."
          return 0
        fi
      fi

      # Fallback: host networking
      log_both "Bridge networking failed. Trying host network..."
      safe_run container_cmd rm -f "$CONTAINER_NAME"
      if container_cmd run -d --name "$CONTAINER_NAME" --rm \
        --network host \
        "$pulled_image" 2>/dev/null; then
        CONTAINER_STARTED=1
        if _wait_for_flaresolverr; then
          log_both "FlareSolverr running via $CONTAINER_RUNTIME (host network)."
          return 0
        fi
      fi

      # One more try with TTY allocation (some setups need -t)
      safe_run container_cmd rm -f "$CONTAINER_NAME"
      if container_cmd run -d --name "$CONTAINER_NAME" --rm -t \
        -p "127.0.0.1:$FLARESOLVERR_PORT:$FLARESOLVERR_PORT" \
        "$pulled_image" 2>/dev/null; then
        CONTAINER_STARTED=1
        if _wait_for_flaresolverr; then
          log_both "FlareSolverr running via $CONTAINER_RUNTIME (with -t)."
          return 0
        fi
      fi
    fi

    # ── Tier 4: Podman fallback (if Docker was primary and failed) ────────────
    if _try_podman_fallback; then
      return 0
    fi
  fi

  # ── Tier 5: Direct (no container) ──────────────────────────────────────────
  log_both "Container approach failed. Trying direct FlareSolverr install..."
  _try_flaresolverr_npx && return 0
  _try_flaresolverr_direct_pip && return 0

  # ── Tier 6: Failed gracefully ──────────────────────────────────────────────
  log_both "All FlareSolverr startup methods exhausted."
  log_both "FlareSolverr favorites sync will be unavailable."
  log_both "The app will still launch - you can browse, search, and manage local favorites."
  log_both "Set flaresolverr_enabled=false in Settings or add user/pass to suppress sync errors."
  log_both ""
  log_both "Fix Docker permission (one-time):"
  log_both "  sudo usermod -aG docker $USER && newgrp docker"
  log_both ""
  log_both "Alternative: install Podman"
  log_both "  sudo pacman -S podman"
  log_both ""
  log_both "Check logs: $LOG_FILE"
  return 0
}

# ─── Cleanup ──────────────────────────────────────────────────────────────────

cleanup() {
  if [[ "$CONTAINER_STARTED" -eq 1 ]]; then
    log_both "Stopping FlareSolverr container..."
    safe_run container_cmd stop "$CONTAINER_NAME" 2>/dev/null
    safe_run container_cmd rm -f "$CONTAINER_NAME" 2>/dev/null
  fi
}

# ─── Launch ───────────────────────────────────────────────────────────────────

launch_app() {
  APP_PYTHON="${APP_PYTHON:-$VENV_DIR/bin/python}"
  if [[ ! -x "$APP_PYTHON" ]]; then
    APP_PYTHON="$PYTHON_BIN"
  fi

  log_both "Launching R34 Linux Client with $APP_PYTHON..."
  APP_LAUNCHED=1
  set +o errexit
  "$APP_PYTHON" -m r34_client
  local rc=$?
  set -o errexit
  log_both "Application exited with code $rc."
  return "$rc"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
  init_logging
  log_to_file "=== R34 Launcher started ==="

  configure_display_backend
  ensure_python
  _ensure_package_manager || true
  ensure_vlc
  _ensure_container_runtime || true
  _start_docker_daemon || true
  ensure_venv

  trap cleanup EXIT INT TERM
  start_flaresolverr || true

  launch_app
  local app_rc=$?

  if [[ "$app_rc" -ne 0 ]]; then
    sleep 1
  fi

  return "$app_rc"
}

main "$@"
