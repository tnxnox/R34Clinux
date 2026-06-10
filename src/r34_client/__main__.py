from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from r34_client import __version__
from r34_client.core.settings import SettingsStore
from r34_client.ui.main_window import MainWindow

_log = logging.getLogger(__name__)


def _configure_display() -> None:
    """Force XCB on Wayland sessions — VLC doesn't work with Wayland Qt."""
    if os.environ.get("QT_QPA_PLATFORM"):
        return  # user explicitly set it, don't override
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    if session_type == "wayland" or wayland_display:
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        _log.info("Wayland detected, forced QT_QPA_PLATFORM=xcb for VLC compatibility")


def _check_vlc() -> None:
    """Warn if VLC is not installed — video playback won't work."""
    if not shutil.which("vlc"):
        _log.warning(
            "VLC not found on PATH. Video playback won't work. "
            "Install VLC from https://videolan.org or your package manager."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="R34 Linux Client")
    parser.add_argument(
        "--version",
        action="version",
        version=f"r34-client {__version__}",
    )
    # Parse known args only to avoid conflicts with Qt flags
    parsed, _ = parser.parse_known_args(sys.argv[1:])

    _LOG_LEVEL = os.environ.get("R34_LOG_LEVEL", "").upper()
    console_level = getattr(logging, _LOG_LEVEL, logging.INFO)

    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        log_dir = Path(xdg_state) / "r34-client"
    else:
        log_dir = Path.home() / ".local" / "share" / "r34-client"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        verbose_log_file = log_dir / "verbose.log"
    except Exception:
        verbose_log_file = Path("verbose.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(verbose_log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        _log.info("File logging initialized: %s", verbose_log_file)
    except Exception as e:
        sys.stderr.write(f"Failed to initialize file logging: {e}\n")

    # ── Environment setup ──
    _configure_display()
    _check_vlc()

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

    # Allow Ctrl+C to cleanly quit the application instead of being
    # swallowed by Qt's event loop (which causes infinite KeyboardInterrupt
    # spam in timer callbacks).
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Python's signal handler only fires between bytecodes, but Qt's event
    # loop blocks in C code.  A tiny no-op timer forces Python to regain
    # control every 200 ms so the signal handler can actually execute.
    from PySide6.QtCore import QTimer
    _sigint_timer = QTimer()
    _sigint_timer.timeout.connect(lambda: None)
    _sigint_timer.start(200)

    # Load and apply the QSS stylesheet
    try:
        qss_path = Path(__file__).parent / "ui" / "style.qss"
        if qss_path.exists():
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log.warning("Failed to load stylesheet: %s", e)

    store = SettingsStore()
    window = MainWindow(store)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
