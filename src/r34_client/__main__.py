from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from r34_client.core.settings import SettingsStore
from r34_client.ui.main_window import MainWindow

_LOG_LEVEL = os.environ.get("R34_LOG_LEVEL", "").upper()
if _LOG_LEVEL:
    logging.basicConfig(
        level=getattr(logging, _LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
    # Raise the image allocation limit so very tall / high-resolution
    # long-strip images (e.g. 4000×40000) can be decoded without Qt
    # rejecting them.  0 = unlimited.
    os.environ.setdefault("QT_IMAGEIO_MAXALLOC", "0")

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    app = QApplication(sys.argv)
    app.setApplicationName("R34 Linux Client")

    store = SettingsStore()
    window = MainWindow(store)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
