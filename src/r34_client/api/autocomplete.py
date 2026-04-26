from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

from r34_client.core.models import TagSuggestion
from r34_client.api.urls import RULE34_AUTOCOMPLETE_URL


class AutocompleteError(RuntimeError):
    pass


_INVALID_VALUE_CHARS = set(";&?")


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sanitize_value(raw: object) -> str:
    value = _normalize_whitespace(html.unescape(str(raw or "")))
    if not value:
        return ""
    if any(char in value for char in _INVALID_VALUE_CHARS):
        return ""
    if " " in value:
        return ""
    return value


@dataclass(slots=True)
class AutocompleteClient:
    base_url: str = RULE34_AUTOCOMPLETE_URL
    timeout: int = 20
    _session: requests.Session = field(default_factory=requests.Session)

    def fetch(self, prefix: str) -> list[TagSuggestion]:
        query = prefix.strip()
        if not query:
            return []

        response = self._session.get(self.base_url, params={"q": query}, timeout=self.timeout)
        if response.status_code >= 400:
            raise AutocompleteError(f"Autocomplete request failed with HTTP {response.status_code}")
        return self._parse(response.text)

    def _parse(self, text: str) -> list[TagSuggestion]:
        if not text.strip():
            return []

        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AutocompleteError("Autocomplete response could not be parsed.") from exc

        if not isinstance(payload, list):
            raise AutocompleteError("Autocomplete response was not a list.")

        suggestions: list[TagSuggestion] = []
        seen_values: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue

            value = _sanitize_value(item.get("value"))
            if not value or value in seen_values:
                continue

            label = _normalize_whitespace(html.unescape(str(item.get("label") or "")))
            suggestion = TagSuggestion.from_payload({"label": label, "value": value})
            suggestions.append(suggestion)
            seen_values.add(value)
        return suggestions
