from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .core.settings import SettingsStore
from .ui.windows.main_window import MainWindow


def main() -> int:
    # Keep WebEngine flags conservative: swiftshader + disable-gpu combinations can abort on Linux.
    existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    flag_parts = [part for part in existing_flags.split() if part]
    disallowed_prefixes = ("--use-gl=swiftshader", "--disable-gpu-compositing")
    filtered_flags = [part for part in flag_parts if not part.startswith(disallowed_prefixes)]

    if "--disable-gpu" not in filtered_flags:
        filtered_flags.append("--disable-gpu")

    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(filtered_flags)
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    app = QApplication(sys.argv)
    app.setApplicationName("R34 Linux Client")

    store = SettingsStore()
    window = MainWindow(store)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
