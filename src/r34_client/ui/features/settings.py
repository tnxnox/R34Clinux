from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog

from ..dialogs.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def open_settings(window: MainWindow, initial: bool = False) -> None:
    dialog = SettingsDialog(window.settings, window.store, window)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        if initial and not window.settings.has_credentials:
            window._set_status("Credentials are required to search.")
        return

    previously_enabled = bool(window.settings.flaresolverr_enabled)
    window.settings = dialog.current_settings()
    window.store.save(window.settings)
    window.client = window._make_client(window.settings)
    window._configure_background_sync_timer()
    window._refresh_collection_filter()
    just_enabled = (not previously_enabled) and bool(window.settings.flaresolverr_enabled)
    if window.settings.flaresolverr_enabled:
        window._set_status("Settings saved. FlareSolverr sync is enabled.")
        if just_enabled:
            # First render local cache immediately; avoid an expensive first remote sync
            # right after toggling the setting, which can appear as a permanent hang.
            window._set_right_status("Local favorites loaded. Run Refresh Favorites to sync remote.")
            window._refresh_local_favorites()
            return
    else:
        window._set_status("Settings saved.")
    window._refresh_favorites()
