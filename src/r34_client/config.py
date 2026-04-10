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

    @property
    def has_credentials(self) -> bool:
        return bool(self.user_id.strip()) and bool(self.api_key.strip())


class SettingsStore:
    def __init__(self) -> None:
        self._settings = QSettings("R34LinuxClient", "R34LinuxClient")

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
        self._settings.sync()

    @staticmethod
    def default_download_directory() -> str:
        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if location:
            return location
        return str(Path.home() / "Downloads")
