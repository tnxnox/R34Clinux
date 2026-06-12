from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

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
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            self._config_dir = Path(xdg_config) / "R34LinuxClient"
        else:
            self._config_dir = Path.home() / ".config" / "R34LinuxClient"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path = self._config_dir / "settings.json"
        self._data: dict = {}
        self._load_file()

    def _load_file(self) -> None:
        if self._settings_path.exists():
            try:
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.error("Failed to load settings file %s: %s", self._settings_path, e)
                self._data = {}
        else:
            self._data = {}

    def _save_file(self) -> None:
        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save settings file %s: %s", self._settings_path, e)

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
        api = self._data.get("api", {})
        sync = self._data.get("sync", {})
        downloads = self._data.get("downloads", {})
        ui = self._data.get("ui", {})

        settings = AppSettings(
            user_id=str(api.get("user_id", "")),
            api_key=str(api.get("api_key", "")),
            website_username=str(sync.get("website_username", "")),
            website_password=str(sync.get("website_password", "")),
            download_directory=str(downloads.get("directory", "")),
            page_size=int(ui.get("page_size", 50)),
            flaresolverr_enabled=bool(sync.get("flaresolverr_enabled", False)),
            flaresolverr_url=str(sync.get("flaresolverr_url", "http://127.0.0.1:8191")),
            sync_conflict_strategy=str(sync.get("conflict_strategy", "merge")),
            background_sync_interval_minutes=int(sync.get("background_interval_minutes", 0)),
            download_naming_template=str(downloads.get("naming_template", "{id}")),
            download_path_template=str(downloads.get("path_template", "")),
            download_use_sample=bool(downloads.get("use_sample", False)),
            download_sidecar_enabled=bool(downloads.get("sidecar_enabled", False)),
            download_sidecar_format=str(downloads.get("sidecar_format", "json")),
            download_max_retries=int(downloads.get("max_retries", 3)),
        )
        self._validate_settings(settings)
        return settings

    def _validate_settings(self, settings: AppSettings) -> None:
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

        if settings.page_size < 1:
            settings.page_size = 50
        elif settings.page_size > 1000:
            settings.page_size = 1000

        if settings.download_max_retries < 0:
            settings.download_max_retries = 0

        valid_formats = {"json", "txt", "both"}
        if settings.download_sidecar_format.lower() not in valid_formats:
            settings.download_sidecar_format = "json"

        valid_strategies = {"merge", "local_wins", "remote_wins"}
        if settings.sync_conflict_strategy.lower() not in valid_strategies:
            settings.sync_conflict_strategy = "merge"

    def save(self, settings: AppSettings) -> None:
        self._data["api"] = {
            "user_id": settings.user_id,
            "api_key": settings.api_key,
        }
        self._data["sync"] = {
            "website_username": settings.website_username,
            "website_password": settings.website_password,
            "flaresolverr_enabled": settings.flaresolverr_enabled,
            "flaresolverr_url": settings.flaresolverr_url,
            "conflict_strategy": settings.sync_conflict_strategy,
            "background_interval_minutes": settings.background_sync_interval_minutes,
        }
        self._data["downloads"] = {
            "directory": settings.download_directory,
            "naming_template": settings.download_naming_template,
            "path_template": settings.download_path_template,
            "use_sample": settings.download_use_sample,
            "sidecar_enabled": settings.download_sidecar_enabled,
            "sidecar_format": settings.download_sidecar_format,
            "max_retries": settings.download_max_retries,
        }
        self._data["ui"] = {
            "page_size": settings.page_size,
        }
        self._save_file()

    def load_search_history(self, limit: int = 12) -> list[str]:
        search = self._data.get("search", {})
        raw_history = search.get("history", [])
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
        if "search" not in self._data:
            self._data["search"] = {}
        self._data["search"]["history"] = cleaned_queries[: max(0, int(limit))]
        self._save_file()

    def load_saved_searches(self, limit: int = 12) -> list[str]:
        search = self._data.get("search", {})
        return self._load_string_list(search.get("saved_queries", []), limit)

    def save_saved_searches(self, queries: list[str], limit: int = 12) -> None:
        cleaned_queries = [query.strip() for query in queries if query and query.strip()]
        if "search" not in self._data:
            self._data["search"] = {}
        self._data["search"]["saved_queries"] = cleaned_queries[: max(0, int(limit))]
        self._save_file()

    def load_pinned_filters(self, limit: int = 12) -> list[str]:
        search = self._data.get("search", {})
        return self._load_string_list(search.get("pinned_queries", []), limit)

    def save_pinned_filters(self, queries: list[str], limit: int = 12) -> None:
        cleaned_queries = [query.strip() for query in queries if query and query.strip()]
        if "search" not in self._data:
            self._data["search"] = {}
        self._data["search"]["pinned_queries"] = cleaned_queries[: max(0, int(limit))]
        self._save_file()

    @staticmethod
    def default_download_directory() -> str:
        return str(Path.home() / "Downloads")
