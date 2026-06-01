from __future__ import annotations

from dataclasses import dataclass, replace as replace_dataclass
from urllib.parse import urlparse


def _as_int(value: object | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def _split_tags(value: object | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [tag for tag in str(value).split() if tag]


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _extract_count(label: str) -> int | None:
    start = label.rfind("(")
    end = label.rfind(")")
    if start == -1 or end == -1 or end <= start + 1:
        return None
    try:
        return int(label[start + 1 : end])
    except ValueError:
        return None


@dataclass(slots=True)
class Post:
    id: int
    tags: list[str]
    rating: str
    score: int | None
    width: int | None
    height: int | None
    file_size: int | None
    source: str
    md5: str
    preview_url: str
    sample_url: str
    file_url: str
    created_at: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> Post:
        return cls(
            id=_as_int(payload.get("id"), 0) or 0,
            tags=_split_tags(payload.get("tags")),
            rating=_as_str(payload.get("rating")),
            score=_as_int(payload.get("score")),
            width=_as_int(payload.get("width")),
            height=_as_int(payload.get("height")),
            file_size=_as_int(payload.get("file_size")),
            source=_as_str(payload.get("source")),
            md5=_as_str(payload.get("md5")),
            preview_url=_as_str(payload.get("preview_url")),
            sample_url=_as_str(payload.get("sample_url")),
            file_url=_as_str(payload.get("file_url")),
            created_at=_as_str(payload.get("change") or payload.get("created_at") or payload.get("date")),
        )

    @property
    def page_url(self) -> str:
        return f"https://rule34.xxx/index.php?page=post&s=view&id={self.id}"

    @property
    def best_preview_url(self) -> str:
        return _first_non_empty(self.sample_url, self.preview_url, self.file_url)

    @property
    def download_url(self) -> str:
        return _first_non_empty(self.file_url, self.sample_url, self.preview_url)

    @property
    def dimensions(self) -> str:
        if self.width and self.height:
            return f"{self.width} x {self.height}"
        return "Unknown size"

    @property
    def file_name(self) -> str:
        url = self.download_url
        if not url:
            return f"post-{self.id}"
        path = urlparse(url).path
        name = path.rsplit("/", 1)[-1]
        return name or f"post-{self.id}"

    def merge_with(self, other: Post) -> Post:
        return replace_dataclass(
            other,
            tags=other.tags or self.tags,
            rating=other.rating or self.rating,
            score=other.score if other.score is not None else self.score,
            width=other.width if other.width is not None else self.width,
            height=other.height if other.height is not None else self.height,
            file_size=other.file_size if other.file_size is not None else self.file_size,
            source=other.source or self.source,
            md5=other.md5 or self.md5,
            preview_url=other.preview_url or self.preview_url,
            sample_url=other.sample_url or self.sample_url,
            file_url=other.file_url or self.file_url,
            created_at=other.created_at or self.created_at,
        )

    @property
    def tags_text(self) -> str:
        return " ".join(self.tags)


@dataclass(slots=True)
class TagSuggestion:
    value: str
    label: str
    count: int | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> TagSuggestion:
        label = _as_str(payload.get("label"))
        value = _as_str(payload.get("value"))
        return cls(
            value=value,
            label=label,
            count=_extract_count(label),
        )

    @property
    def display_text(self) -> str:
        return self.label or self.value
