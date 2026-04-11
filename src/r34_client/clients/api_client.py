from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

import requests

from .autocomplete_client import AutocompleteClient
from ..core.models import Post, TagSuggestion
from ..core.urls import RULE34_API_BASE_URL


class Rule34APIError(RuntimeError):
    pass


@dataclass(slots=True)
class Rule34Client:
    user_id: str
    api_key: str
    base_url: str = RULE34_API_BASE_URL
    timeout: int = 30

    def _auth_params(self) -> dict[str, str]:
        if not self.user_id.strip() or not self.api_key.strip():
            raise Rule34APIError("API credentials are required. Open Settings and enter your user ID and API key.")
        return {"user_id": self.user_id.strip(), "api_key": self.api_key.strip()}

    def _request(self, params: dict[str, Any]) -> requests.Response:
        query = {**self._auth_params(), **params}
        response = requests.get(self.base_url, params=query, timeout=self.timeout)
        if response.status_code >= 400:
            raise Rule34APIError(f"API request failed with HTTP {response.status_code}")
        return response

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
        for item in raw_posts:
            if isinstance(item, ET.Element):
                payload_dict = dict(item.attrib)
            elif isinstance(item, dict):
                payload_dict = item
            else:
                continue
            posts.append(Post.from_payload(payload_dict))
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
        return AutocompleteClient().fetch(prefix)
