from __future__ import annotations

import logging
import time
from typing import Callable
import requests

from r34_client.api.flaresolverr.errors import FlareSolverrError
from r34_client.api.flaresolverr.launcher import start_flaresolverr_container

logger = logging.getLogger(__name__)


class FlareSolverrSession:
    """Manages the transport layer, lifecycle, and request routing through a FlareSolverr session."""

    def __init__(
        self,
        session_name: str,
        solver_url: str = "http://127.0.0.1:8191",
        timeout: int = 60,
        max_timeout_ms: int = 60000,
        session_ttl_minutes: int = 30,
        debug_callback: Callable[[str], None] | None = None,
    ):
        self.session_name = session_name
        self.solver_url = solver_url
        self.timeout = timeout
        self.max_timeout_ms = max_timeout_ms
        self.session_ttl_minutes = session_ttl_minutes
        self.debug_callback = debug_callback

        self.session_ready = False
        self._session = requests.Session()

    def _debug(self, message: str) -> None:
        if self.debug_callback:
            self.debug_callback(message)
        else:
            logger.debug("FlareSolverrSession [%s]: %s", self.session_name, message)

    def _solver_endpoint(self) -> str:
        return f"{self.solver_url.rstrip('/')}/v1"

    def _ensure_session(self) -> None:
        if self.session_ready:
            self._debug("ensure_session: cached")
            return
        self._debug(f"ensure_session: creating/reusing session={self.session_name}")
        payload = {
            "cmd": "sessions.create",
            "session": self.session_name,
        }

        body: dict[str, object] | None = None
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self._session.post(self._solver_endpoint(), json=payload, timeout=self.timeout)
                response.raise_for_status()
                body = response.json()
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == 1:
                    self._debug("ensure_session: connection failed, attempting to auto-start FlareSolverr container")
                    try:
                        started = start_flaresolverr_container(self.solver_url)
                        if started:
                            self._debug("ensure_session: FlareSolverr container auto-started successfully")
                        else:
                            self._debug("ensure_session: failed to auto-start FlareSolverr container")
                    except Exception as launch_exc:
                        self._debug(f"ensure_session: failed to run launcher: {launch_exc}")

                if attempt < 3:
                    delay = float(attempt)
                    self._debug(f"ensure_session: transient failure attempt={attempt}/3 wait={delay:.1f}s")
                    time.sleep(delay)
                    continue
                raise FlareSolverrError(f"Unable to create FlareSolverr session: {exc}") from exc
            except ValueError as exc:
                raise FlareSolverrError("FlareSolverr returned invalid JSON while creating session.") from exc

        if body is None:
            if last_exc is not None:
                raise FlareSolverrError(f"Unable to create FlareSolverr session: {last_exc}") from last_exc
            raise FlareSolverrError("Unable to create FlareSolverr session.")

        status = str(body.get("status", "")).lower()
        if status == "ok":
            self.session_ready = True
            self._debug("ensure_session: ok")
            return

        message = str(body.get("message") or body.get("error") or "")
        if "already exists" in message.lower():
            self.session_ready = True
            self._debug("ensure_session: already exists")
            return

        raise FlareSolverrError(message or "Unable to create FlareSolverr session.")

    def _destroy_session(self) -> None:
        payload = {
            "cmd": "sessions.destroy",
            "session": self.session_name,
        }
        try:
            response = self._session.post(self._solver_endpoint(), json=payload, timeout=self.timeout)
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            self._debug(f"destroy_session: ignored error={exc}")
            return

        status = str(body.get("status", "")).lower()
        if status == "ok":
            self._debug("destroy_session: ok")
            return

        message = str(body.get("message") or body.get("error") or "")
        if "not found" in message.lower() or "doesn't exist" in message.lower() or "does not exist" in message.lower():
            self._debug("destroy_session: already absent")
            return
        self._debug(f"destroy_session: ignored status={status} message={message}")

    def close(self) -> None:
        """Close the underlying requests session and destroy the FlareSolverr session."""
        try:
            self._destroy_session()
        finally:
            self._session.close()

    def __enter__(self) -> FlareSolverrSession:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @staticmethod
    def is_session_error(message: str) -> bool:
        lowered = (message or "").lower()
        return "session" in lowered and (
            "not found" in lowered or "doesn't exist" in lowered or "does not exist" in lowered or "invalid" in lowered
        )

    def request_via_solver(self, url: str, headers: dict[str, str] | None = None) -> str:
        self._debug(f"request.get: {url}")

        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self.max_timeout_ms,
            "session": self.session_name,
            "session_ttl_minutes": self.session_ttl_minutes,
        }
        if headers:
            payload["headers"] = headers

        for attempt in range(1, 5):
            self._ensure_session()
            try:
                response = self._session.post(self._solver_endpoint(), json=payload, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException:
                delay = 0.35 * attempt
                logger.warning("FlareSolverr request.get failed (attempt %d/4): retrying in %.2fs", attempt, delay)
                self._debug(f"request.get: transient failure attempt={attempt}/4 wait={delay:.2f}s")
                self.session_ready = False
                time.sleep(delay)
                continue

            try:
                body = response.json()
            except ValueError as exc:
                raise FlareSolverrError("FlareSolverr returned invalid JSON.") from exc

            status = str(body.get("status", "")).lower()
            if status == "ok":
                solution = body.get("solution") or {}
                content = solution.get("response")
                if not isinstance(content, str):
                    raise FlareSolverrError("FlareSolverr response payload is missing page content.")
                self._debug(f"request.get: ok bytes={len(content)}")
                return content.strip()

            message = str(body.get("message") or body.get("error") or "Unknown FlareSolverr error")
            if attempt < 5 and self.is_session_error(message):
                self._debug(f"request.get: stale session detected, recreating (attempt={attempt}/4)")
                self.session_ready = False
                time.sleep(0.2)
                continue
            self._debug(f"request.get: failed status={status} message={message}")
            raise FlareSolverrError(message)

        raise FlareSolverrError("FlareSolverr request failed after retries.")

    def post_via_solver(self, url: str, post_data: str, referer: str | None = None) -> str:
        # Mask password for logging
        import re
        safe_post_data = re.sub(r"(pass=)[^&]*", r"\1***", post_data, flags=re.IGNORECASE)
        self._debug(f"request.post: {url} payload={safe_post_data[:200]}")

        headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if referer:
            headers["Referer"] = referer

        payload = {
            "cmd": "request.post",
            "url": url,
            "postData": post_data,
            "headers": headers,
            "maxTimeout": self.max_timeout_ms,
            "session": self.session_name,
            "session_ttl_minutes": self.session_ttl_minutes,
        }

        for attempt in range(1, 5):
            self._ensure_session()
            try:
                response = self._session.post(self._solver_endpoint(), json=payload, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException:
                delay = 0.35 * attempt
                logger.warning("FlareSolverr request.post failed (attempt %d/4): retrying in %.2fs", attempt, delay)
                self._debug(f"request.post: transient failure attempt={attempt}/4 wait={delay:.2f}s")
                self.session_ready = False
                time.sleep(delay)
                continue

            try:
                body = response.json()
            except ValueError as exc:
                raise FlareSolverrError("FlareSolverr returned invalid JSON.") from exc

            status = str(body.get("status", "")).lower()
            if status == "ok":
                solution = body.get("solution") or {}
                content = solution.get("response")
                if not isinstance(content, str):
                    raise FlareSolverrError("FlareSolverr response payload is missing page content.")
                self._debug(f"request.post: ok bytes={len(content)}")
                return content.strip()

            message = str(body.get("message") or body.get("error") or "Unknown FlareSolverr error")
            if attempt < 5 and self.is_session_error(message):
                self._debug(f"request.post: stale session detected, recreating (attempt={attempt}/4)")
                self.session_ready = False
                time.sleep(0.2)
                continue
            self._debug(f"request.post: failed status={status} message={message}")
            raise FlareSolverrError(message)

        raise FlareSolverrError("FlareSolverr POST request failed after retries.")
