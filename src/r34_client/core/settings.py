from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


@dataclass(slots=True)
class AppSettings:
    user_id: str = ""
    api_key: str = ""
    website_username: str = ""
    website_password: str = ""
    download_directory: str = ""
    page_size: int = 50
    flaresolverr_enabled: bool = False
    flaresolverr_url: str = "http://127.0.0.1:8191"
    sync_conflict_strategy: str = "merge"
    background_sync_interval_minutes: int = 0

    @property
    def has_credentials(self) -> bool:
        return bool(self.user_id.strip()) and bool(self.api_key.strip())


class SettingsStore:
    def __init__(self) -> None:
        self._settings = QSettings("R34LinuxClient", "R34LinuxClient")

    @staticmethod
    def _load_string_list(values: object | None, limit: int) -> list[str]:
        if not values:
            return []
        if isinstance(values, list):
            items = values
        else:
            items = [values]

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in items:
            query = str(item).strip()
            if not query or query in seen:
                continue
            seen.add(query)
            cleaned.append(query)
        return cleaned[: max(0, int(limit))]

    def load(self) -> AppSettings:
        return AppSettings(
            user_id=self._settings.value("api/user_id", "", str),
            api_key=self._settings.value("api/api_key", "", str),
            website_username=self._settings.value("sync/website_username", "", str),
            website_password=self._settings.value("sync/website_password", "", str),
            download_directory=self._settings.value("downloads/directory", "", str),
            page_size=self._settings.value("ui/page_size", 50, int),
            flaresolverr_enabled=self._settings.value("sync/flaresolverr_enabled", False, bool),
            flaresolverr_url=self._settings.value("sync/flaresolverr_url", "http://127.0.0.1:8191", str),
            sync_conflict_strategy=self._settings.value("sync/conflict_strategy", "merge", str),
            background_sync_interval_minutes=self._settings.value("sync/background_interval_minutes", 0, int),
        )

    def save(self, settings: AppSettings) -> None:
        self._settings.setValue("api/user_id", settings.user_id)
        self._settings.setValue("api/api_key", settings.api_key)
        self._settings.setValue("sync/website_username", settings.website_username)
        self._settings.setValue("sync/website_password", settings.website_password)
        self._settings.setValue("downloads/directory", settings.download_directory)
        self._settings.setValue("ui/page_size", settings.page_size)
        self._settings.setValue("sync/flaresolverr_enabled", settings.flaresolverr_enabled)
        self._settings.setValue("sync/flaresolverr_url", settings.flaresolverr_url)
        self._settings.setValue("sync/conflict_strategy", settings.sync_conflict_strategy)
        self._settings.setValue("sync/background_interval_minutes", settings.background_sync_interval_minutes)
        self._settings.sync()

    def load_search_history(self, limit: int = 12) -> list[str]:
        raw_history = self._settings.value("search/history", [], list)
        history = [str(item).strip() for item in (raw_history or []) if str(item).strip()]
        unique_history: list[str] = []
        seen: set[str] = set()
        for query in history:
            if query in seen:
                continue
            seen.add(query)
            unique_history.append(query)
        return unique_history[: max(0, int(limit))]

    def save_search_history(self, queries: list[str], limit: int = 12) -> None:
        cleaned_queries = [query.strip() for query in queries if query and query.strip()]
        self._settings.setValue("search/history", cleaned_queries[: max(0, int(limit))])
        self._settings.sync()

    def load_saved_searches(self, limit: int = 12) -> list[str]:
        return self._load_string_list(self._settings.value("search/saved_queries", [], list), limit)

    def save_saved_searches(self, queries: list[str], limit: int = 12) -> None:
        cleaned_queries = [query.strip() for query in queries if query and query.strip()]
        self._settings.setValue("search/saved_queries", cleaned_queries[: max(0, int(limit))])
        self._settings.sync()

    def load_pinned_filters(self, limit: int = 12) -> list[str]:
        return self._load_string_list(self._settings.value("search/pinned_queries", [], list), limit)

    def save_pinned_filters(self, queries: list[str], limit: int = 12) -> None:
        cleaned_queries = [query.strip() for query in queries if query and query.strip()]
        self._settings.setValue("search/pinned_queries", cleaned_queries[: max(0, int(limit))])
        self._settings.sync()

    @staticmethod
    def default_download_directory() -> str:
        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if location:
            return location
        return str(Path.home() / "Downloads")
