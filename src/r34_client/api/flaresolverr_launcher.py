from __future__ import annotations

import logging
import shutil
import subprocess
import time
from urllib.parse import urlparse
import requests

logger = logging.getLogger(__name__)

def detect_container_cmd() -> list[str] | None:
    """Detect whether podman or docker is available, supporting passwordless sudo."""
    if shutil.which("podman"):
        return ["podman"]
    if shutil.which("docker"):
        # Check if we can run docker info directly
        try:
            res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if res.returncode == 0:
                return ["docker"]
        except Exception:
            pass
        # Try with passwordless sudo
        try:
            res = subprocess.run(["sudo", "-n", "docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if res.returncode == 0:
                return ["sudo", "-n", "docker"]
        except Exception:
            pass
    return None

def is_url_local(url: str) -> bool:
    """Check if the given URL points to a local address (localhost/127.0.0.1)."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return hostname in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


def _is_container_running(cmd: list[str], container_name: str) -> bool:
    """Check if a container with the given name is currently running."""
    try:
        res = subprocess.run(
            cmd + ["ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        return container_name in res.stdout.splitlines()
    except Exception:
        return False


def restart_flaresolverr_container(solver_url: str = "http://127.0.0.1:8191") -> bool:
    """
    Restart the FlareSolverr container to clear stale sessions.
    If the container is running, stop and restart it.
    If it's not running, start it fresh.
    Returns True if FlareSolverr is reachable after restart, False otherwise.
    """
    if not is_url_local(solver_url):
        # Can't manage remote containers — just check if it's reachable
        try:
            response = requests.get(f"{solver_url.rstrip('/')}/status", timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False

    cmd = detect_container_cmd()
    if not cmd:
        logger.warning("No container runtime (docker/podman) detected. Cannot restart FlareSolverr.")
        return False

    container_name = "r34-flaresolverr"

    if _is_container_running(cmd, container_name):
        logger.info("Restarting FlareSolverr container '%s' to clear stale sessions...", container_name)
        try:
            subprocess.run(
                cmd + ["restart", container_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            )
            return _wait_for_flaresolverr(solver_url)
        except Exception as exc:
            logger.warning("Failed to restart container: %s. Removing and recreating...", exc)
            try:
                subprocess.run(cmd + ["rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    # Container not running or restart failed — start fresh
    return start_flaresolverr_container(solver_url)


def start_flaresolverr_container(solver_url: str = "http://127.0.0.1:8191") -> bool:
    """
    Ensure FlareSolverr is running. If solver_url is local and unreachable,
    attempt to spin up a Docker/Podman container.
    Returns True if FlareSolverr is reachable, False otherwise.
    """
    # 1. First probe if it's already running
    try:
        response = requests.get(f"{solver_url.rstrip('/')}/status", timeout=2)
        if response.status_code == 200:
            logger.info("FlareSolverr is already running at %s", solver_url)
            return True
    except requests.RequestException:
        pass

    # 2. If it's not a local URL, we can't start a local container for it
    if not is_url_local(solver_url):
        logger.warning("FlareSolverr URL %s is remote and unreachable. Cannot launch local container.", solver_url)
        return False

    # 3. Detect container runtime
    cmd = detect_container_cmd()
    if not cmd:
        logger.warning("No container runtime (docker/podman) detected. Cannot start FlareSolverr.")
        return False

    container_name = "r34-flaresolverr"
    image_name = "ghcr.io/flaresolverr/flaresolverr:latest"
    fallback_image = "ghcr.io/flaresolverr/flaresolverr:v3.3.21"

    # 4. Check if container exists
    try:
        ps_cmd = cmd + ["ps", "-a", "--format", "{{.Names}}"]
        res = subprocess.run(ps_cmd, capture_output=True, text=True, check=True)
        containers = res.stdout.splitlines()
    except Exception as exc:
        logger.warning("Failed to check existing container: %s", exc)
        return False

    if container_name in containers:
        logger.info("Starting existing FlareSolverr container '%s'...", container_name)
        try:
            subprocess.run(cmd + ["start", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            logger.warning("Failed to start existing container. Recreating...")
            try:
                subprocess.run(cmd + ["rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            return _run_new_container(cmd, image_name, fallback_image, container_name, solver_url)
    else:
        return _run_new_container(cmd, image_name, fallback_image, container_name, solver_url)

    return _wait_for_flaresolverr(solver_url)

def _run_new_container(cmd: list[str], image: str, fallback_image: str, container_name: str, solver_url: str) -> bool:
    # Try to pull the image first (optional/best-effort)
    try:
        subprocess.run(cmd + ["pull", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        image = fallback_image
        try:
            subprocess.run(cmd + ["pull", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        except Exception:
            logger.warning("Could not pull FlareSolverr image. Attempting run anyway.")

    run_cmd = cmd + [
        "run", "-d",
        "--name", container_name,
        "--restart", "no",
        "-p", "8191:8191",
        "-e", "LOG_LEVEL=info",
        image
    ]
    try:
        subprocess.run(run_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return _wait_for_flaresolverr(solver_url)
    except Exception as exc:
        logger.error("Failed to run FlareSolverr container: %s", exc)
        return False

def _wait_for_flaresolverr(solver_url: str) -> bool:
    status_url = f"{solver_url.rstrip('/')}/status"
    for _ in range(30):
        try:
            response = requests.get(status_url, timeout=1)
            if response.status_code == 200:
                logger.info("FlareSolverr started successfully at %s", solver_url)
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    logger.error("FlareSolverr did not respond at %s within 30 seconds.", solver_url)
    return False

