from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog

from r34_client.ui.dialogs.settings import SettingsDialog

if TYPE_CHECKING:
    from ..main_window import MainWindow


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
    window._configure_pending_sync_timer()
    window._refresh_collection_filter()
    just_enabled = (not previously_enabled) and bool(window.settings.flaresolverr_enabled)
    if window.settings.flaresolverr_enabled:
        window._set_status("Settings saved. FlareSolverr sync is enabled.")
        if just_enabled:
            # First render local cache immediately; avoid an expensive first remote sync
            # right after toggling the setting, which can appear as a permanent hang.
            window._set_right_status("Local favorites loaded. Starting FlareSolverr...")
            window._refresh_local_favorites()

            def start_solver_task() -> bool:
                from r34_client.api.flaresolverr.launcher import start_flaresolverr_container
                return start_flaresolverr_container(window.settings.flaresolverr_url)

            def on_start_finished(success: object) -> None:
                if success:
                    window._set_right_status("FlareSolverr running. Click Refresh Favorites to sync.")
                else:
                    window._set_right_status("Failed to start FlareSolverr.")

            from r34_client.core.worker import FunctionWorker
            worker = FunctionWorker(start_solver_task)
            worker.signals.finished.connect(on_start_finished)
            window._start_worker(worker, workload="general")
            return
    else:
        window._set_status("Settings saved.")
    window._refresh_favorites()
