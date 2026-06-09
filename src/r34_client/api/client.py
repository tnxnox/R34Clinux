from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

import requests

from r34_client.api.autocomplete import AutocompleteClient
from r34_client.core.models import Post, TagSuggestion
from r34_client.api.urls import RULE34_API_BASE_URL

logger = logging.getLogger(__name__)


class Rule34APIError(RuntimeError):
    pass


@dataclass(slots=True)
class Rule34Client:
    user_id: str
    api_key: str
    base_url: str = RULE34_API_BASE_URL
    timeout: int = 30
    max_retries: int = 3
    _session: requests.Session = field(default_factory=requests.Session)
    _autocomplete: AutocompleteClient = field(default_factory=AutocompleteClient)

    def _auth_params(self) -> dict[str, str]:
        if not self.user_id.strip() or not self.api_key.strip():
            raise Rule34APIError("API credentials are required. Open Settings and enter your user ID and API key.")
        return {"user_id": self.user_id.strip(), "api_key": self.api_key.strip()}

    def _request(self, params: dict[str, Any]) -> requests.Response:
        from r34_client.core.worker import check_cancelled, cancellable_sleep
        query = {**self._auth_params(), **params}
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            check_cancelled()
            try:
                response = self._session.get(self.base_url, params=query, timeout=self.timeout)

                # Handle retryable HTTP errors
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < self.max_retries - 1:
                        wait = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                        logger.warning(
                            "API request got HTTP %d (attempt %d/%d). Retrying in %ds...",
                            response.status_code, attempt + 1, self.max_retries, wait,
                        )
                        cancellable_sleep(wait)
                        continue
                    raise Rule34APIError(
                        f"API request failed: HTTP {response.status_code} after {self.max_retries} retries"
                    )

                # Handle auth errors immediately (no retry)
                if response.status_code == 401:
                    raise Rule34APIError("API credentials expired or invalid (HTTP 401)")
                if response.status_code == 403:
                    raise Rule34APIError("Access forbidden (HTTP 403)")

                # Handle other 4xx errors
                if response.status_code >= 400:
                    raise Rule34APIError(f"API request failed with HTTP {response.status_code}")

                return response

            except requests.Timeout as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt
                    logger.warning("API request timed out (attempt %d/%d). Retrying in %ds...", attempt + 1, self.max_retries, wait)
                    cancellable_sleep(wait)
                    continue
                raise Rule34APIError(f"API request timed out after {self.max_retries} retries") from e

            except requests.ConnectionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt
                    logger.warning("API connection error (attempt %d/%d). Retrying in %ds...", attempt + 1, self.max_retries, wait)
                    cancellable_sleep(wait)
                    continue
                raise Rule34APIError(f"API connection failed after {self.max_retries} retries") from e

            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt
                    cancellable_sleep(wait)
                    continue
                raise Rule34APIError(f"API request failed after {self.max_retries} retries: {e}") from e

        raise Rule34APIError(f"API request failed after {self.max_retries} retries") from last_error

    def search_posts(self, tags: str, page: int, limit: int) -> list[Post]:
        response = self._request(
            {
                "page": "dapi",
                "s": "post",
                "q": "index",
                "tags": tags.strip() or "all",
                "pid": page,
                "limit": limit,
                "json": 1,
            }
        )
        return self._extract_posts(response)

    def _extract_posts(self, response: requests.Response) -> list[Post]:
        text = response.text.strip()
        if not text:
            return []

        payload = self._decode_payload(text, response.headers.get("content-type", ""))
        raw_posts: Any

        if isinstance(payload, list):
            raw_posts = payload
        elif isinstance(payload, dict):
            if payload.get("success") is False:
                message = str(payload.get("message") or payload)
                raise Rule34APIError(message)
            raw_posts = payload.get("post") or payload.get("posts") or payload.get("result") or []
        elif isinstance(payload, str):
            raise Rule34APIError(payload)
        else:
            raw_posts = payload.findall(".//post") if isinstance(payload, ET.Element) else []

        if isinstance(raw_posts, dict):
            raw_posts = [raw_posts]

        posts: list[Post] = []
        parse_errors: list[str] = []

        for item in raw_posts:
            try:
                payload_dict: dict[str, object] = {}
                if isinstance(item, ET.Element):
                    payload_dict = dict(item.attrib)
                elif isinstance(item, dict):
                    payload_dict = item
                else:
                    parse_errors.append(f"Skipping item: unexpected type {type(item).__name__}")
                    continue

                posts.append(Post.from_payload(payload_dict))

            except (KeyError, ValueError, TypeError) as e:
                error_msg = f"Failed to parse post payload: {e}"
                parse_errors.append(error_msg)
                logger.warning("Post parse error: %s — payload=%s", e, payload_dict if isinstance(item, dict) else "(xml)")
                continue

        if parse_errors:
            logger.info("Post extraction completed with %d parse error(s): %s", len(parse_errors), parse_errors[:3])

        return posts

    def _decode_payload(self, text: str, content_type: str) -> Any:
        if "json" in content_type or text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        try:
            return ET.fromstring(text)
        except ET.ParseError as exc:
            raise Rule34APIError("The API returned data that could not be parsed.") from exc

    def autocomplete_tags(self, prefix: str) -> list[TagSuggestion]:
        return self._autocomplete.fetch(prefix)
