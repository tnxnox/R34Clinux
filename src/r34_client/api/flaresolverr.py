from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests

from r34_client.api.flaresolverr_parsing import (
    decode_payload,
    extract_body_text,
    extract_favorite_tile_ids,
    extract_items,
    looks_logged_in,
    looks_rate_limited,
)
from r34_client.core.models import Post
from r34_client.api.urls import (
    RULE34_API_BASE_URL,
    account_home_url,
    account_login_url,
    add_favorite_public_url,
    add_favorite_web_url,
    delete_favorite_web_url,
    favorites_list_url,
    favorites_view_url,
)

logger = logging.getLogger(__name__)


class FlareSolverrError(RuntimeError):
    pass


@dataclass(slots=True)
class FlareSolverrFavoritesClient:
    user_id: str
    api_key: str
    website_username: str = ""
    website_password: str = ""
    solver_url: str = "http://127.0.0.1:8191"
    timeout: int = 60
    max_timeout_ms: int = 60000
    api_base_url: str = RULE34_API_BASE_URL
    session_ttl_minutes: int = 30
    _session_ready: bool = False
    _web_session_authenticated: bool = False
    _debug_events: list[str] = field(default_factory=list)
    _session: requests.Session = field(default_factory=requests.Session)

    def _debug(self, message: str) -> None:
        self._debug_events.append(message)
        if len(self._debug_events) > 80:
            self._debug_events = self._debug_events[-80:]

    def debug_summary(self) -> str:
        if not self._debug_events:
            return "No FlareSolverr debug events recorded."
        return "\n".join(self._debug_events)

    def _auth_params(self) -> dict[str, str]:
        if not self.user_id.strip() or not self.api_key.strip():
            raise FlareSolverrError("API credentials are required for sync.")
        return {"user_id": self.user_id.strip(), "api_key": self.api_key.strip()}

    def _solver_endpoint(self) -> str:
        return f"{self.solver_url.rstrip('/')}/v1"

    def _session_name(self) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", self.user_id.strip())
        return f"r34-{cleaned or 'default'}"

    def _ensure_session(self) -> None:
        if self._session_ready:
            self._debug("ensure_session: cached")
            return
        self._debug(f"ensure_session: creating/reusing session={self._session_name()}")
        payload = {
            "cmd": "sessions.create",
            "session": self._session_name(),
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
            self._session_ready = True
            self._debug("ensure_session: ok")
            return

        message = str(body.get("message") or body.get("error") or "")
        if "already exists" in message.lower():
            self._session_ready = True
            self._debug("ensure_session: already exists")
            return

        raise FlareSolverrError(message or "Unable to create FlareSolverr session.")

    def _destroy_session(self) -> None:
        payload = {
            "cmd": "sessions.destroy",
            "session": self._session_name(),
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

    def __enter__(self) -> FlareSolverrFavoritesClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Context manager exit; close session resources."""
        self.close()

    @staticmethod
    def _is_session_error(message: str) -> bool:
        lowered = (message or "").lower()
        return "session" in lowered and (
            "not found" in lowered or "doesn't exist" in lowered or "does not exist" in lowered or "invalid" in lowered
        )

    def _request_via_solver(self, url: str, headers: dict[str, str] | None = None) -> str:
        self._debug(f"request.get: {url}")

        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self.max_timeout_ms,
            "session": self._session_name(),
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
                self._session_ready = False
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
            if attempt < 5 and self._is_session_error(message):
                self._debug(f"request.get: stale session detected, recreating (attempt={attempt}/4)")
                self._session_ready = False
                self._web_session_authenticated = False
                time.sleep(0.2)
                continue
            self._debug(f"request.get: failed status={status} message={message}")
            raise FlareSolverrError(message)

        raise FlareSolverrError("FlareSolverr request failed after retries.")

    def _post_via_solver(self, url: str, post_data: str, referer: str | None = None) -> str:
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
            "session": self._session_name(),
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
                self._session_ready = False
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
            if attempt < 5 and self._is_session_error(message):
                self._debug(f"request.post: stale session detected, recreating (attempt={attempt}/4)")
                self._session_ready = False
                self._web_session_authenticated = False
                time.sleep(0.2)
                continue
            self._debug(f"request.post: failed status={status} message={message}")
            raise FlareSolverrError(message)

        raise FlareSolverrError("FlareSolverr POST request failed after retries.")

    def _api_url(self, extra: dict[str, object]) -> str:
        query = {**self._auth_params(), **extra}
        return f"{self.api_base_url}?{urlencode(query)}"

    def _favorite_exists(self, post_id: int) -> bool:
        return self._favorite_exists_in_view_with_retries(
            post_id,
            attempts=2,
            allow_unknown=False,
        )

    def _favorite_exists_in_view(self, post_id: int) -> bool:
        return self._favorite_exists_in_view_with_retries(post_id, attempts=3, allow_unknown=False)

    def _favorite_exists_in_view_with_retries(
        self,
        post_id: int,
        *,
        attempts: int,
        allow_unknown: bool,
    ) -> bool | None:
        url = favorites_view_url(self.user_id)
        capped_attempts = max(1, int(attempts))
        html_text = ""
        for attempt in range(1, capped_attempts + 1):
            html_text = self._request_via_solver(url)
            if not looks_rate_limited(html_text):
                break
            if attempt < capped_attempts:
                delay_seconds = float(attempt)
                self._debug(
                    f"favorites_view_check: rate limited attempt={attempt}/{capped_attempts} wait={delay_seconds:.1f}s"
                )
                time.sleep(delay_seconds)

        if looks_rate_limited(html_text):
            if allow_unknown:
                self._debug("favorites_view_check: unresolved due to rate limit, accepting unknown state")
                return None
            raise FlareSolverrError("Rate limited while checking favorites state. Please retry in a few seconds.")

        if not self._looks_favorites_view_authenticated(html_text):
            self._debug("favorites_view_check: unexpected page content while verifying favorites state")
            if allow_unknown:
                return None
            raise FlareSolverrError("Unable to verify favorites state from favorites view. Please retry.")

        target = int(post_id)
        parsed_ids = extract_favorite_tile_ids(html_text)
        self._debug(f"favorites_view_check: parsed_tiles={len(parsed_ids)}")
        return target in parsed_ids

    @staticmethod
    def _looks_transient_web_gate(text: str) -> bool:
        lowered = (text or "").strip().lower()
        compact = re.sub(r"\s+", "", lowered)
        return compact in {"<br>", "<br><br>", "<br/><br/>", "<br/><br>", "<br><br/>"}

    @staticmethod
    def _looks_logged_in(html_text: str) -> bool:
        return looks_logged_in(html_text)

    def _request_body_with_rate_limit_retries(
        self,
        *,
        url: str,
        headers: dict[str, str] | None = None,
        attempts: int = 3,
    ) -> str:
        last_body = ""
        capped_attempts = max(1, int(attempts))
        for attempt in range(1, capped_attempts + 1):
            raw = self._request_via_solver(url, headers=headers)
            body = extract_body_text(raw)
            last_body = body
            if not looks_rate_limited(body):
                return body
            if attempt < capped_attempts:
                delay_seconds = float(attempt)
                self._debug(
                    f"mutate_favorite: rate limited endpoint={url} attempt={attempt}/{capped_attempts} wait={delay_seconds:.1f}s"
                )
                time.sleep(delay_seconds)
        return last_body

    def _probe_web_login(self) -> bool:
        probe_urls = [
            account_home_url(),
            favorites_view_url(self.user_id),
        ]
        for url in probe_urls:
            try:
                html_text = self._request_via_solver(url)
            except FlareSolverrError as exc:
                self._debug(f"ensure_web_login: probe failed url={url} error={exc}")
                continue
            if looks_logged_in(html_text):
                self._debug(f"ensure_web_login: probe matched logged-in markers url={url}")
                return True
            if "page=account&s=home" in url and self._looks_account_home_authenticated(html_text):
                self._debug("ensure_web_login: account home indicates authenticated session")
                return True
            if "page=favorites&s=view" in url and self._looks_favorites_view_authenticated(html_text):
                self._debug("ensure_web_login: favorites view indicates authenticated session")
                return True
        return False

    @staticmethod
    def _looks_favorites_view_authenticated(html_text: str) -> bool:
        lowered = (html_text or "").lower()
        if "page=account&s=login&code=00" in lowered:
            return False
        if "name=\"user\"" in lowered and "name=\"pass\"" in lowered:
            return False
        return (
            "page=favorites&s=view" in lowered
            or "id=\"post-list\"" in lowered
            or "id=\"p" in lowered
        )

    @staticmethod
    def _looks_account_home_authenticated(html_text: str) -> bool:
        lowered = (html_text or "").lower()
        if "page=account&s=login&code=00" in lowered:
            return False
        if "name=\"user\"" in lowered and "name=\"pass\"" in lowered:
            return False
        if (
            "page=account&s=logout" in lowered
            or "s=logout" in lowered
            or "page=account&s=change_password" in lowered
            or "logged in as" in lowered
        ):
            return True
        # Account home can be authenticated but miss strict logout markers.
        return "page=account&s=home" in lowered and len(lowered) > 10000

    def _ensure_web_login(self) -> None:
        if self._web_session_authenticated:
            self._debug("ensure_web_login: already authenticated")
            return

        if self._probe_web_login():
            self._web_session_authenticated = True
            self._debug("ensure_web_login: probe indicates logged in")
            return

        username = self.website_username.strip()
        password = self.website_password.strip()
        if not username or not password:
            self._debug("ensure_web_login: missing website credentials")
            raise FlareSolverrError(
                "Account favorite add/remove requires website username/password in Settings "
                "(FlareSolverr sync uses a web login session)."
            )

        login_url = account_login_url()
        post_data = urlencode(
            {
                "user": username,
                "pass": password,
                "submit": "Log in",
                "login": "Log in",
            }
        )
        self._post_via_solver(login_url, post_data, referer=login_url)

        verified = False
        for attempt in range(1, 4):
            if self._probe_web_login():
                verified = True
                break
            if attempt < 3:
                delay = 0.4 * attempt
                self._debug(f"ensure_web_login: verification retry attempt={attempt}/3 wait={delay:.1f}s")
                time.sleep(delay)

        if not verified:
            # Some sessions propagate authentication to mutation endpoints with delay,
            # and strict probe verification can be a false negative on first attempt.
            # Let the caller retry the mutation endpoint and use its response as authority.
            self._debug("ensure_web_login: login verification inconclusive; proceeding with best-effort session")
            return

        self._web_session_authenticated = True
        self._debug("ensure_web_login: login verified")

    def list_favorites(self, limit: int) -> list[Post]:
        posts = self._list_favorites_from_dapi(limit)
        if posts:
            return posts

        logger.warning("list_favorites: DAPI returned empty, falling back to HTML parsing")

        html_posts = self._list_favorites_from_html(limit)
        if html_posts:
            return html_posts

        logger.warning(
            "list_favorites: both DAPI and HTML parsing returned zero posts. "
            "The favorite list page may have changed its HTML structure."
        )
        return []

    def _list_favorites_from_dapi(self, limit: int) -> list[Post]:
        url = self._api_url(
            {
                "page": "dapi",
                "s": "favorite",
                "q": "index",
                "json": 1,
                "limit": max(1, int(limit)),
            }
        )
        try:
            raw = self._request_via_solver(url)
            payload = decode_payload(raw)
        except FlareSolverrError as exc:
            self._debug(f"list_favorites_dapi: fallback_to_html reason={exc}")
            logger.warning("list_favorites_dapi: falling back to HTML due to: %s", exc)
            return []
        except RuntimeError as exc:
            raise FlareSolverrError("Unable to parse response returned via FlareSolverr.") from exc

        if isinstance(payload, list):
            raw_posts: Any = payload
        elif isinstance(payload, dict):
            if payload.get("success") is False:
                raise FlareSolverrError(str(payload.get("message") or payload))
            raw_posts = payload.get("post") or payload.get("posts") or payload.get("result") or []
        elif isinstance(payload, ET.Element):
            raw_posts = payload.findall(".//post")
        else:
            raw_posts = []

        if isinstance(raw_posts, dict):
            raw_posts = [raw_posts]

        posts: list[Post] = []
        for item in raw_posts:
            if isinstance(item, ET.Element):
                data = dict(item.attrib)
            elif isinstance(item, dict):
                data = item
            else:
                continue
            posts.append(Post.from_payload(data))
        return posts

    def _list_favorites_from_html(self, limit: int) -> list[Post]:
        candidates = [
            favorites_view_url(self.user_id),
            favorites_list_url(),
        ]

        seen_ids: set[int] = set()
        posts: list[Post] = []

        for url in candidates:
            html = self._request_via_solver(url)
            items = extract_items(html)
            self._debug(f"list_favorites_html: url={url} extracted_items={len(items)}")
            for post_id, preview_url in items:
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                posts.append(
                    Post.from_payload(
                        {
                            "id": post_id,
                            "preview_url": preview_url,
                            "sample_url": preview_url,
                        }
                    )
                )
                logger.debug(
                    "list_favorites_html: post %s has partial data (id/preview only, no tags/rating/score)",
                    post_id,
                )
                if len(posts) >= max(1, int(limit)):
                    return posts

            self._debug(f"list_favorites_html: total_unique_items={len(posts)}")
        return posts

    def add_favorite(self, post_id: int) -> None:
        self._mutate_favorite(post_id, "add")

    def remove_favorite(self, post_id: int) -> None:
        self._mutate_favorite(post_id, "delete")

    def _mutate_favorite(self, post_id: int, query: str) -> None:
        target_id = int(post_id)
        want_present = query == "add"
        self._debug(f"mutate_favorite: action={query} post_id={target_id}")
        self._ensure_web_login()
        favorites_view_referrer = favorites_view_url(self.user_id)

        if want_present:
            add_url = add_favorite_public_url(target_id)
            for auth_attempt in range(1, 3):
                raw = self._request_via_solver(add_url, headers=None)
                body = extract_body_text(raw)
                effective_body = body
                self._debug(f"mutate_favorite: endpoint={add_url} body={body[:120]}")

                if looks_rate_limited(body):
                    raise FlareSolverrError(
                        "Rule34 temporarily rate limited favorite add (HTTP 429). Please retry in a few seconds."
                    )

                if body == "2":
                    if auth_attempt == 1:
                        self._debug("mutate_favorite: add endpoint reported not logged in, resetting session and re-login")
                        self._destroy_session()
                        self._session_ready = False
                        self._web_session_authenticated = False
                        self._ensure_web_login()
                        continue

                    alt_url = add_favorite_web_url(target_id)
                    alt_raw = self._request_via_solver(alt_url, headers={"Referer": favorites_view_referrer})
                    alt_body = extract_body_text(alt_raw)
                    effective_body = alt_body
                    self._debug(f"mutate_favorite: endpoint={alt_url} body={alt_body[:120]}")
                    if looks_rate_limited(alt_body) or self._looks_transient_web_gate(alt_body):
                        raise FlareSolverrError(
                            "Rule34 temporarily rate limited favorite add (HTTP 429). Please retry in a few seconds."
                        )
                    if alt_body == "2":
                        raise FlareSolverrError(
                            "Favorites mutation requires a logged rule34 web session in FlareSolverr (server replied not logged in)."
                        )

                # Verification fetch is required because mutation endpoints can return 200 OK 
                # even if the mutation didn't stick due to session issues FlareSolverr missed.
                after_present = self._favorite_exists_in_view_with_retries(
                    target_id,
                    attempts=2,
                    allow_unknown=False,
                )
                self._debug(f"mutate_favorite: after_present={after_present}")
                if after_present is True:
                    return
                
                raise FlareSolverrError(
                    f"Unable to add account favorite #{target_id}. Latest server response: {effective_body or 'empty response'}"
                )
            return

        # For deletion, we first check if it exists to avoid unnecessary requests
        before_present = self._favorite_exists_in_view(target_id)
        self._debug(f"mutate_favorite: before_present={before_present}")
        if before_present is False:
            self._debug("mutate_favorite: already in desired state")
            return

        web_delete_url = delete_favorite_web_url(target_id)
        for auth_attempt in range(1, 3):
            last_body = self._request_body_with_rate_limit_retries(
                url=web_delete_url,
                headers={"Referer": favorites_view_referrer},
                attempts=2,
            )
            self._debug(f"mutate_favorite: endpoint={web_delete_url} body={last_body[:120]}")
            if last_body == "2":
                if auth_attempt == 1:
                    self._debug("mutate_favorite: delete endpoint reported not logged in, forcing re-login")
                    self._web_session_authenticated = False
                    self._ensure_web_login()
                    continue
                raise FlareSolverrError(
                    "Favorites mutation requires a logged rule34 web session in FlareSolverr (server replied not logged in)."
                )
            
            # Post-mutation check to confirm deletion
            after_present = self._favorite_exists_in_view_with_retries(
                target_id,
                attempts=2,
                allow_unknown=True,
            )
            self._debug(f"mutate_favorite: after_present={after_present}")
            if after_present is False:
                return
            if after_present is None:
                # If we can't verify due to rate limit, we assume it's pending
                self._debug("mutate_favorite: delete verification deferred due to temporary rate limit")
                return
            
            raise FlareSolverrError(
                f"Unable to remove account favorite #{target_id}. Latest server response: {last_body or 'empty response'}"
            )

