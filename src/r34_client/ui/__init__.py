from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from r34_client.ui.main_window import MainWindow
    from r34_client.ui.dialogs.settings import SettingsDialog

__all__ = ["MainWindow", "SettingsDialog"]
