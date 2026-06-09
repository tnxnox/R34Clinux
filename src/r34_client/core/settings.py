from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

logger = logging.getLogger(__name__)


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
    download_naming_template: str = "{id}"
    download_path_template: str = ""
    download_use_sample: bool = False
    download_sidecar_enabled: bool = False
    download_sidecar_format: str = "json"  # json, txt, both
    download_max_retries: int = 3

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
        settings = AppSettings(
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
            download_naming_template=self._settings.value("downloads/naming_template", "{id}", str),
            download_path_template=self._settings.value("downloads/path_template", "", str),
            download_use_sample=self._settings.value("downloads/use_sample", False, bool),
            download_sidecar_enabled=self._settings.value("downloads/sidecar_enabled", False, bool),
            download_sidecar_format=self._settings.value("downloads/sidecar_format", "json", str),
            download_max_retries=self._settings.value("downloads/max_retries", 3, int),
        )
        self._validate_settings(settings)
        return settings

    def _validate_settings(self, settings: AppSettings) -> None:
        """Validate loaded settings and log warnings for any issues."""
        # Validate download directory exists or can be created
        dl_dir = settings.download_directory
        if dl_dir:
            dl_path = Path(dl_dir)
            if dl_path.exists() and not dl_path.is_dir():
                logger.warning("Download directory '%s' exists but is not a directory", dl_dir)
            elif not dl_path.exists():
                try:
                    dl_path.mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    logger.warning("Cannot create download directory '%s': permission denied", dl_dir)

        # Validate page_size
        if settings.page_size < 1:
            logger.warning("page_size is %d, resetting to default 50", settings.page_size)
            settings.page_size = 50
        elif settings.page_size > 1000:
            logger.warning("page_size is %d (very large), may cause performance issues", settings.page_size)

        # Validate download_max_retries
        if settings.download_max_retries < 0:
            logger.warning("download_max_retries is %d, resetting to 0", settings.download_max_retries)
            settings.download_max_retries = 0

        # Validate sidecar format
        valid_formats = {"json", "txt", "both"}
        if settings.download_sidecar_format.lower() not in valid_formats:
            logger.warning(
                "Unknown sidecar format '%s', valid options: %s. Resetting to 'json'.",
                settings.download_sidecar_format, ", ".join(sorted(valid_formats)),
            )
            settings.download_sidecar_format = "json"

        # Validate sync conflict strategy
        valid_strategies = {"merge", "local_wins", "remote_wins"}
        if settings.sync_conflict_strategy.lower() not in valid_strategies:
            logger.warning(
                "Unknown sync conflict strategy '%s', valid options: %s. Resetting to 'merge'.",
                settings.sync_conflict_strategy, ", ".join(sorted(valid_strategies)),
            )
            settings.sync_conflict_strategy = "merge"

    def save(self, settings: AppSettings) -> None:
        if settings.website_password:
            logger.warning(
                "Website password is stored in plaintext. Consider setting up a system keyring "
                "for secure credential storage instead."
            )
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
        self._settings.setValue("downloads/naming_template", settings.download_naming_template)
        self._settings.setValue("downloads/path_template", settings.download_path_template)
        self._settings.setValue("downloads/use_sample", settings.download_use_sample)
        self._settings.setValue("downloads/sidecar_enabled", settings.download_sidecar_enabled)
        self._settings.setValue("downloads/sidecar_format", settings.download_sidecar_format)
        self._settings.setValue("downloads/max_retries", settings.download_max_retries)
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
