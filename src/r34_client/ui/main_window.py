from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

import requests
from PySide6.QtCore import QEvent, QThreadPool, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QImage, QKeyEvent, QPixmap, QShortcut
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCompleter,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    import vlc  # type: ignore
except ImportError:  # pragma: no cover - optional runtime dependency
    vlc = None

from ..api import Rule34Client
from ..concurrency import FunctionWorker
from ..config import AppSettings, SettingsStore
from ..flaresolverr_client import FlareSolverrError, FlareSolverrFavoritesClient
from ..local_favorites import LocalFavoritesStore
from ..models import Post, TagSuggestion
from ..rate_limit import DegradedModeController, is_rate_limited_error_message
from .diagnostics import DiagnosticsSnapshot, format_diagnostics_report
from .image_fit import FitMode, compute_base_render_size
from .preview_fetcher import fetch_preview_bytes
from .post_helpers import (
    download_url_needs_hydration,
    format_millis,
    format_post_metadata,
    format_post_tile,
    is_video_post,
    needs_hydration,
    probe_file_size,
)
from .favorites_sync import sync_remote_favorites
from .settings_dialog import SettingsDialog
from .widgets import ClickSeekSlider, ClickVideoSurface


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("R34 Linux Client")
        self.resize(1320, 840)

        self.store = store
        self.settings = store.load()
        self.client = self._make_client(self.settings)
        self.local_favorites = LocalFavoritesStore()
        self.pool = QThreadPool.globalInstance()

        self.current_posts: list[Post] = []
        self.favorite_posts: list[Post] = []
        self.favorite_ids: set[int] = set()
        self.current_page = 0
        self.current_query = ""
        self._search_token = 0
        self._preview_token = 0
        self._favorites_token = 0
        self._autocomplete_token = 0
        self._last_autocomplete_prefix = ""
        self._autocomplete_cache: dict[str, list[TagSuggestion]] = {}
        self._autocomplete_token_start = 0
        self._autocomplete_token_end = 0
        self._autocomplete_query_snapshot = ""
        self._active_workers: set[FunctionWorker] = set()
        self._favorites_sync_fallback_used = False
        self._metadata_hydrated_ids: set[int] = set()
        self._last_favorite_sync_failed = False
        self._last_favorite_sync_error = ""
        self._last_favorite_sync_debug = ""
        self._sync_debug_log_path = self.local_favorites.database_path.parent / "sync-debug.log"
        self._is_long_strip_image = False

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tags, e.g. character rating:safe")
        self.search_input.returnPressed.connect(self.search)
        self.search_input.textEdited.connect(self._schedule_autocomplete)

        self.autocomplete_timer = QTimer(self)
        self.autocomplete_timer.setSingleShot(True)
        self.autocomplete_timer.setInterval(90)
        self.autocomplete_timer.timeout.connect(self._refresh_autocomplete)

        self.completer_model = QStandardItemModel(self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self.completer.setCompletionRole(Qt.ItemDataRole.UserRole)
        self.completer.activated[str].connect(self._insert_completion)
        self.search_input.setCompleter(self.completer)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search)

        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.previous_page)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)

        self.page_label = QLabel("Page 1")

        self.results_list = QListWidget()
        self.results_list.currentItemChanged.connect(self._handle_selection_change)
        self.results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self._open_results_context_menu)

        self.favorites_list = QListWidget()
        self.favorites_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.favorites_list.currentItemChanged.connect(self._handle_selection_change)
        self.favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self._open_favorites_context_menu)

        self.collection_filter = QComboBox()
        self.collection_filter.addItem("All Favorites", None)
        self.collection_filter.currentIndexChanged.connect(self._on_collection_filter_changed)

        self.manage_collections_button = QPushButton("Collections")
        self.manage_collections_button.clicked.connect(self._open_collection_manager)

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self.results_list, "Search Results")
        self.left_tabs.addTab(self.favorites_list, "Favorites")
        self.left_tabs.currentChanged.connect(self._update_action_state)

        self.preview_label = QLabel("Search for a post to preview it here.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setWordWrap(True)
        self.preview_label.setScaledContents(False)

        self.video_surface = ClickVideoSurface(self)
        self.video_surface.setMinimumHeight(320)
        self.video_surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.clicked.connect(self.toggle_video_playback)
        self.video_surface.hide()

        self._vlc_instance = None
        self._vlc_player = None
        if vlc is not None:
            try:
                self._vlc_instance = vlc.Instance("--no-video-title-show", "--network-caching=300")
                self._vlc_player = self._vlc_instance.media_player_new()
            except Exception:
                self._vlc_instance = None
                self._vlc_player = None

        self._base_preview_pixmap: QPixmap | None = None
        self._image_zoom_percent = 100
        self._fit_mode = FitMode.SMART
        self._image_pan_active = False
        self._image_pan_start_pos: tuple[int, int] = (0, 0)
        self._image_pan_start_scroll: tuple[int, int] = (0, 0)
        self._mutation_token = 0
        self._download_token = 0
        self._hydrate_token = 0
        self._rate_limit = DegradedModeController()

        self.meta_view = QPlainTextEdit()
        self.meta_view.setReadOnly(True)

        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.download_selected_post)

        self.open_button = QPushButton("Open in Browser")
        self.open_button.clicked.connect(self.open_selected_post)

        self.volume_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(140)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)

        self.seek_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setFixedHeight(22)
        self.seek_slider.sliderPressed.connect(self._on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_slider_released)
        self.seek_slider.sliderMoved.connect(self._on_seek_slider_moved)

        self.seek_time_label = QLabel("00:00 / 00:00")

        self._seek_dragging = False
        self._pending_seek_ms = 0

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(250)
        self.playback_timer.timeout.connect(self._refresh_playback_controls)
        self.playback_timer.start()

        self.background_sync_timer = QTimer(self)
        self.background_sync_timer.timeout.connect(self._background_sync_tick)

        self.copy_button = QPushButton("Copy Link")
        self.copy_button.clicked.connect(self.copy_selected_link)

        self._global_shortcuts: list[QShortcut] = []

        self._build_layout()
        self._build_toolbar()
        self._register_global_shortcuts()
        self._refresh_collection_filter()
        self._configure_background_sync_timer()
        self._update_action_state()
        self._refresh_favorites()

        if not self.settings.has_credentials:
            self.statusBar().showMessage("Enter API credentials in Settings before searching.")
            self.open_settings(initial=True)
        else:
            self.statusBar().showMessage("Ready.")

    def _make_client(self, settings: AppSettings) -> Rule34Client:
        return Rule34Client(user_id=settings.user_id, api_key=settings.api_key)

    def _make_sync_client(self, settings: AppSettings) -> FlareSolverrFavoritesClient | None:
        if not settings.flaresolverr_enabled:
            return None
        if not settings.has_credentials:
            return None
        return FlareSolverrFavoritesClient(
            user_id=settings.user_id,
            api_key=settings.api_key,
            solver_url=settings.flaresolverr_url,
            website_username=settings.website_username,
            website_password=settings.website_password,
        )

    def _sync_enabled(self) -> bool:
        return self._make_sync_client(self.settings) is not None

    def _configure_background_sync_timer(self) -> None:
        interval_minutes = max(0, int(self.settings.background_sync_interval_minutes))
        if interval_minutes <= 0 or not self._sync_enabled():
            self.background_sync_timer.stop()
            return
        self.background_sync_timer.setInterval(interval_minutes * 60 * 1000)
        self.background_sync_timer.start()

    def _background_sync_tick(self) -> None:
        if not self._sync_enabled():
            return
        if self._active_workers:
            return
        self._refresh_favorites()

    def _selected_collection_name(self) -> str | None:
        selected = self.collection_filter.currentData()
        if not selected:
            return None
        return str(selected)

    def _refresh_collection_filter(self) -> None:
        selected = self._selected_collection_name()
        collections = self.local_favorites.list_collections()
        self.collection_filter.blockSignals(True)
        self.collection_filter.clear()
        self.collection_filter.addItem("All Favorites", None)
        for collection in collections:
            self.collection_filter.addItem(collection, collection)
        if selected:
            index = self.collection_filter.findData(selected)
            if index >= 0:
                self.collection_filter.setCurrentIndex(index)
        self.collection_filter.blockSignals(False)

    def _on_collection_filter_changed(self, _: int) -> None:
        self._refresh_favorites()

    def _open_collection_manager(self) -> None:
        text, accepted = QInputDialog.getText(self, "New collection", "Collection name")
        if not accepted:
            return
        try:
            name = self.local_favorites.create_collection(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Collections", str(exc))
            return
        self._refresh_collection_filter()
        index = self.collection_filter.findData(name)
        if index >= 0:
            self.collection_filter.setCurrentIndex(index)

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.prev_button)
        search_row.addWidget(self.next_button)
        search_row.addWidget(self.page_label)
        layout.addLayout(search_row)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        collection_row = QHBoxLayout()
        collection_row.addWidget(QLabel("Collection"))
        collection_row.addWidget(self.collection_filter, 1)
        collection_row.addWidget(self.manage_collections_button)
        left_layout.addLayout(collection_row)

        left_layout.addWidget(self.left_tabs)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        media_panel = QWidget()
        media_layout = QVBoxLayout(media_panel)

        self.preview_container = QScrollArea()
        self.preview_container.setWidgetResizable(False)
        self.preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_container.setWidget(self.preview_label)
        self.preview_container.viewport().installEventFilter(self)
        media_layout.addWidget(self.preview_container, 3)

        media_layout.addWidget(self.video_surface, 3)

        meta_row = QHBoxLayout()
        meta_row.addWidget(self.download_button)
        meta_row.addWidget(self.open_button)
        meta_row.addWidget(QLabel("Volume"))
        meta_row.addWidget(self.volume_slider)
        meta_row.addWidget(self.copy_button)
        meta_row.addStretch(1)
        media_layout.addLayout(meta_row)

        playback_row = QHBoxLayout()
        playback_row.addWidget(QLabel("Position"))
        playback_row.addWidget(self.seek_slider, 1)
        playback_row.addWidget(self.seek_time_label)
        media_layout.addLayout(playback_row)

        right_splitter = QSplitter()
        right_splitter.setOrientation(Qt.Orientation.Vertical)
        right_splitter.addWidget(media_panel)
        right_splitter.addWidget(self.meta_view)
        right_splitter.setSizes([620, 220])
        right_layout.addWidget(right_splitter, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([460, 860])
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)

        search_action = QAction("Search", self)
        search_action.triggered.connect(self.search)
        toolbar.addAction(search_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        refresh_favorites_action = QAction("Refresh Favorites", self)
        refresh_favorites_action.triggered.connect(self._refresh_favorites)
        toolbar.addAction(refresh_favorites_action)

        toolbar.addSeparator()

        fit_group = QActionGroup(self)
        fit_group.setExclusive(True)

        fit_smart_action = QAction("Fit: Smart", self)
        fit_smart_action.setCheckable(True)
        fit_smart_action.setChecked(True)
        fit_smart_action.triggered.connect(lambda: self._set_fit_mode(FitMode.SMART))
        fit_group.addAction(fit_smart_action)
        toolbar.addAction(fit_smart_action)

        fit_width_action = QAction("Fit: Width", self)
        fit_width_action.setCheckable(True)
        fit_width_action.triggered.connect(lambda: self._set_fit_mode(FitMode.FIT_WIDTH))
        fit_group.addAction(fit_width_action)
        toolbar.addAction(fit_width_action)

        fit_height_action = QAction("Fit: Height", self)
        fit_height_action.setCheckable(True)
        fit_height_action.triggered.connect(lambda: self._set_fit_mode(FitMode.FIT_HEIGHT))
        fit_group.addAction(fit_height_action)
        toolbar.addAction(fit_height_action)

        fit_original_action = QAction("Fit: 1:1", self)
        fit_original_action.setCheckable(True)
        fit_original_action.triggered.connect(lambda: self._set_fit_mode(FitMode.ORIGINAL))
        fit_group.addAction(fit_original_action)
        toolbar.addAction(fit_original_action)

        toolbar.addSeparator()

        cancel_action = QAction("Cancel", self)
        cancel_action.setShortcut("Esc")
        cancel_action.triggered.connect(self._cancel_current_operations)
        toolbar.addAction(cancel_action)

        controls_action = QAction("Controls", self)
        controls_action.triggered.connect(self._open_controls)
        toolbar.addAction(controls_action)

        diagnostics_action = QAction("Diagnostics", self)
        diagnostics_action.triggered.connect(self._open_diagnostics)
        toolbar.addAction(diagnostics_action)

        self.addToolBar(toolbar)

    def _register_global_shortcuts(self) -> None:
        shortcut_specs = [
            ("Esc", self._cancel_current_operations),
            ("J", lambda: self._invoke_global_navigation(lambda: self._move_selection(+1))),
            ("K", lambda: self._invoke_global_navigation(lambda: self._move_selection(-1))),
            ("F", lambda: self._invoke_global_navigation(self._toggle_current_favorite)),
            ("O", lambda: self._invoke_global_navigation(self.open_selected_post)),
            ("D", lambda: self._invoke_global_navigation(self.download_selected_post)),
        ]

        for key_sequence, callback in shortcut_specs:
            shortcut = QShortcut(key_sequence, self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(callback)
            self._global_shortcuts.append(shortcut)

    def _invoke_global_navigation(self, callback) -> None:
        if isinstance(self.focusWidget(), QLineEdit):
            return
        callback()

    def _update_action_state(self) -> None:
        has_selection = self._current_post() is not None
        self.download_button.setEnabled(has_selection)
        self.open_button.setEnabled(has_selection)
        self.copy_button.setEnabled(has_selection)
        self.volume_slider.setEnabled(self._vlc_player is not None)
        self.seek_slider.setEnabled(self._vlc_player is not None and has_selection and self._current_post_is_video())

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _set_fit_mode(self, mode: FitMode) -> None:
        self._fit_mode = mode
        self._update_preview_scaling()
        self._set_status(f"Image fit mode: {mode.value}")

    def _cancel_current_operations(self) -> None:
        # Workers keep running in background, but incrementing tokens prevents stale results from mutating UI state.
        self._search_token += 1
        self._preview_token += 1
        self._favorites_token += 1
        self._autocomplete_token += 1
        self._mutation_token += 1
        self._download_token += 1
        self._hydrate_token += 1
        self._set_status("Cancelled current operations.")

    def _diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        remaining = self._rate_limit.remaining_seconds(time.monotonic())
        selected = self._current_post()
        return DiagnosticsSnapshot(
            sync_enabled=self._sync_enabled(),
            degraded_mode_active=remaining > 0,
            degraded_mode_remaining_seconds=remaining,
            fit_mode=self._fit_mode.value,
            active_workers=len(self._active_workers),
            current_query=self.current_query,
            current_page=self.current_page,
            current_results_count=len(self.current_posts),
            current_favorites_count=len(self.favorite_posts),
            selected_post_id=(selected.id if selected is not None else None),
            last_sync_failed=self._last_favorite_sync_failed,
            last_sync_error=self._last_favorite_sync_error,
            sync_debug_log_path=str(self._sync_debug_log_path),
        )

    def _open_diagnostics(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Diagnostics")
        dialog.resize(860, 540)

        layout = QVBoxLayout(dialog)
        report = QPlainTextEdit(dialog)
        report.setReadOnly(True)
        report.setPlainText(format_diagnostics_report(self._diagnostics_snapshot()))
        layout.addWidget(report, 1)

        close_button = QPushButton("Close", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def _open_controls(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Controls")
        dialog.resize(760, 480)

        layout = QVBoxLayout(dialog)
        report = QPlainTextEdit(dialog)
        report.setReadOnly(True)
        report.setPlainText(
            "R34 Linux Client Controls\n\n"
            "Keyboard shortcuts\n"
            "- Esc: cancel ongoing operations\n"
            "- j: move to the next post\n"
            "- k: move to the previous post\n"
            "- f: toggle favorite on the selected post\n"
            "- o: open the selected post in the browser\n"
            "- d: download the selected post\n\n"
            "Toolbar actions\n"
            "- Search: run the current search query\n"
            "- Settings: edit account and sync settings\n"
            "- Refresh Favorites: reload the favorites tab\n"
            "- Fit buttons: switch image fitting mode\n"
            "- Cancel: stop applying stale results from running tasks\n"
            "- Diagnostics: open the live diagnostics panel\n\n"
            "Viewer hints\n"
            "- Use the mouse wheel or zoom controls to change preview scale\n"
            "- Click and drag on zoomed previews to pan around long images\n"
        )
        layout.addWidget(report, 1)

        close_button = QPushButton("Close", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def _mark_rate_limited_if_needed(self, context: str, error_message: str) -> None:
        if not is_rate_limited_error_message(error_message):
            return
        backoff = self._rate_limit.mark_rate_limited(time.monotonic())
        self._log_sync_debug(
            f"Rate limit degraded mode ({context})",
            f"Backoff seconds: {backoff}\nError: {error_message}",
        )

    def _degraded_mode_remaining(self) -> int:
        return self._rate_limit.remaining_seconds(time.monotonic())

    def _degraded_mode_active(self) -> bool:
        return self._degraded_mode_remaining() > 0

    def _log_sync_debug(self, title: str, details: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._sync_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._sync_debug_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {title}\n")
            handle.write((details or "(no details)").strip() + "\n\n")

    def search(self) -> None:
        query = self.search_input.text().strip()
        self.current_query = query
        self.current_page = 0
        self._run_search()

    def next_page(self) -> None:
        if not self.current_query:
            return
        self.current_page += 1
        self._run_search()

    def previous_page(self) -> None:
        if self.current_page <= 0 or not self.current_query:
            return
        self.current_page -= 1
        self._run_search()

    def _run_search(self) -> None:
        if not self.settings.has_credentials:
            self.open_settings(initial=True)
            return

        self.page_label.setText(f"Page {self.current_page + 1}")
        self.results_list.clear()
        self.preview_label.setText("Loading results...")
        self.meta_view.clear()
        self.current_posts = []
        self._update_action_state()
        self._set_status("Searching...")

        self._search_token += 1
        token = self._search_token

        worker = FunctionWorker(
            lambda: self.client.search_posts(self.current_query, self.current_page, self.settings.page_size)
        )
        worker.signals.finished.connect(lambda result: self._search_finished(token, result))
        worker.signals.failed.connect(self._operation_failed)
        self._start_worker(worker)

    def _search_finished(self, token: int, result: object) -> None:
        if token != self._search_token:
            return
        posts = list(result) if isinstance(result, list) else []
        self.current_posts = posts
        self.results_list.clear()

        for post in posts:
            item = QListWidgetItem(self._format_post_tile(post))
            item.setData(Qt.ItemDataRole.UserRole, post)
            self.results_list.addItem(item)

        if posts:
            self.results_list.setCurrentRow(0)
            self._set_status(f"Loaded {len(posts)} posts.")
        else:
            self.preview_label.setText("No posts matched the search query.")
            self.meta_view.setPlainText("No results.")
            self._set_status("Search completed with no results.")

        self._update_action_state()

    def _refresh_favorites(self) -> None:
        self._refresh_favorites_impl(local_only=False)

    def _refresh_local_favorites(self) -> None:
        self._refresh_favorites_impl(local_only=True)

    def _refresh_favorites_impl(self, local_only: bool) -> None:
        self._favorites_token += 1
        token = self._favorites_token
        if self._sync_enabled() and not local_only:
            self._set_status("Syncing favorites via FlareSolverr...")
            worker = FunctionWorker(self._sync_remote_favorites)
        else:
            self._set_status("Refreshing local favorites...")
            worker = FunctionWorker(
                lambda: self.local_favorites.list_favorites(collection_name=self._selected_collection_name())
            )

        worker.signals.finished.connect(lambda result: self._favorites_loaded(token, result))
        worker.signals.failed.connect(lambda error_text: self._favorites_failed(token, error_text))
        self._start_worker(worker)

    def _sync_remote_favorites(self) -> tuple[list[Post], bool]:
        if self._degraded_mode_active():
            remaining = self._degraded_mode_remaining()
            self._log_sync_debug(
                "Favorites sync skipped (degraded mode)",
                f"Remaining cooldown seconds: {remaining}",
            )
            return (self.local_favorites.list_favorites(), bool(self.local_favorites.list_favorites()))

        return sync_remote_favorites(
            settings=self.settings,
            local_favorites=self.local_favorites,
            make_sync_client=self._make_sync_client,
            log_sync_debug=self._log_sync_debug,
            on_sync_error=lambda message: self._mark_rate_limited_if_needed("favorites_sync", message),
        )

    def _favorites_loaded(self, token: int, result: object) -> None:
        if token != self._favorites_token:
            return

        loaded_posts: list[Post]
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], list):
            loaded_posts = result[0]
            self._favorites_sync_fallback_used = bool(result[1])
        elif isinstance(result, list):
            loaded_posts = result
            self._favorites_sync_fallback_used = False
        else:
            return

        selected_collection = self._selected_collection_name()
        if selected_collection is not None:
            loaded_posts = self.local_favorites.list_favorites(collection_name=selected_collection)

        self.favorite_posts = [item for item in loaded_posts if isinstance(item, Post)]
        self.favorite_ids = {post.id for post in self.favorite_posts}
        self._refresh_collection_filter()

        self.favorites_list.clear()
        for post in self.favorite_posts:
            item = QListWidgetItem(self._format_post_tile(post))
            item.setData(Qt.ItemDataRole.UserRole, post)
            self.favorites_list.addItem(item)

        if self._sync_enabled():
            if self._favorites_sync_fallback_used:
                if self._degraded_mode_active():
                    self._set_status(
                        "Favorites sync temporarily degraded due to rate limiting; "
                        f"showing local cache ({len(self.favorite_posts)} posts)."
                    )
                else:
                    self._set_status(
                        f"Favorites sync returned empty data; showing local cache ({len(self.favorite_posts)} posts)."
                    )
            else:
                self._rate_limit.note_success()
                self._set_status(f"Favorites synced ({len(self.favorite_posts)} posts).")
        else:
            self._set_status(f"Local favorites loaded ({len(self.favorite_posts)} posts).")
        self._update_action_state()

    def _favorites_failed(self, token: int, error_text: str) -> None:
        if token != self._favorites_token:
            return
        first_line = error_text.splitlines()[0] if error_text else "unknown error"
        self._log_sync_debug("Favorites refresh failure", error_text)
        if self._sync_enabled():
            self._set_status(f"Favorites sync failed: {first_line} (see {self._sync_debug_log_path})")
        else:
            self._set_status(f"Local favorites refresh failed: {first_line}")

    def _open_results_context_menu(self, position) -> None:
        item = self.results_list.itemAt(position)
        if item is None:
            return
        post = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(post, Post):
            return

        menu = QMenu(self)
        if post.id in self.favorite_ids:
            action = menu.addAction("Remove from favorites")
            action.triggered.connect(lambda: self._remove_favorite(post))
        else:
            action = menu.addAction("Add to favorites")
            action.triggered.connect(lambda: self._add_favorite(post))
        menu.exec(self.results_list.viewport().mapToGlobal(position))

    def _open_favorites_context_menu(self, position) -> None:
        item = self.favorites_list.itemAt(position)
        if item is None:
            return
        if item not in self.favorites_list.selectedItems():
            self.favorites_list.setCurrentItem(item)
            item.setSelected(True)

        selected_posts = self._selected_favorite_posts()
        if not selected_posts:
            return

        menu = QMenu(self)

        if len(selected_posts) > 1:
            remove_action = menu.addAction(f"Remove {len(selected_posts)} selected from favorites")
            remove_action.triggered.connect(lambda: self._remove_multiple_favorites(selected_posts))

            download_action = menu.addAction(f"Download {len(selected_posts)} selected")
            download_action.triggered.connect(lambda: self._download_multiple_posts(selected_posts))

            open_action = menu.addAction(f"Open {len(selected_posts)} selected in browser")
            open_action.triggered.connect(lambda: self._open_multiple_posts(selected_posts))
        else:
            remove_action = menu.addAction("Remove from favorites")
            remove_action.triggered.connect(lambda: self._remove_favorite(selected_posts[0]))

        menu.addSeparator()
        assign_submenu = menu.addMenu("Add selected to collection")
        new_collection_action = assign_submenu.addAction("New collection...")
        new_collection_action.triggered.connect(lambda: self._assign_selection_to_new_collection(selected_posts))

        for collection in self.local_favorites.list_collections():
            action = assign_submenu.addAction(collection)
            action.triggered.connect(
                lambda _checked=False, c=collection: self._assign_selection_to_collection(selected_posts, c)
            )

        current_collection = self._selected_collection_name()
        if current_collection:
            remove_collection_action = menu.addAction(f"Remove selected from '{current_collection}'")
            remove_collection_action.triggered.connect(
                lambda: self._remove_selection_from_collection(selected_posts, current_collection)
            )

        menu.exec(self.favorites_list.viewport().mapToGlobal(position))

    def _selected_favorite_posts(self) -> list[Post]:
        posts: list[Post] = []
        selected_items = self.favorites_list.selectedItems()
        for item in selected_items:
            post = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(post, Post):
                posts.append(post)
        if posts:
            return posts
        current = self._current_post()
        return [current] if current is not None else []

    def _remove_multiple_favorites(self, posts: list[Post]) -> None:
        unique_posts = {post.id: post for post in posts}
        if not unique_posts:
            return

        self._set_status(f"Removing {len(unique_posts)} favorites...")
        self._mutation_token += 1
        token = self._mutation_token

        worker = FunctionWorker(lambda: self._remove_multiple_favorites_impl(list(unique_posts.values())))
        worker.signals.finished.connect(lambda result: self._favorite_bulk_mutation_finished(token, result))
        worker.signals.failed.connect(self._operation_failed)
        self._start_worker(worker)

    def _remove_multiple_favorites_impl(self, posts: list[Post]) -> list[int]:
        removed_ids: list[int] = []
        for post in posts:
            self._remove_favorite_impl(post)
            removed_ids.append(post.id)
        return removed_ids

    def _favorite_bulk_mutation_finished(self, token: int, result: object) -> None:
        if token != self._mutation_token:
            return
        removed_ids = [int(item) for item in result] if isinstance(result, list) else []
        for post_id in removed_ids:
            self.favorite_ids.discard(post_id)
        self._set_status(f"Removed {len(removed_ids)} favorites.")
        if self._sync_enabled() and not self._last_favorite_sync_failed:
            self._refresh_favorites()
        else:
            self._refresh_local_favorites()

    def _assign_selection_to_new_collection(self, posts: list[Post]) -> None:
        text, accepted = QInputDialog.getText(self, "New collection", "Collection name")
        if not accepted:
            return
        self._assign_selection_to_collection(posts, text)

    def _assign_selection_to_collection(self, posts: list[Post], collection_name: str) -> None:
        post_ids = [post.id for post in posts]
        try:
            assigned = self.local_favorites.assign_posts_to_collection(post_ids, collection_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Collections", str(exc))
            return
        self._refresh_collection_filter()
        self._set_status(f"Added {assigned} favorites to collection '{collection_name.strip()}'.")

    def _remove_selection_from_collection(self, posts: list[Post], collection_name: str) -> None:
        removed = self.local_favorites.remove_posts_from_collection([post.id for post in posts], collection_name)
        self._set_status(f"Removed {removed} favorites from '{collection_name}'.")
        self._refresh_favorites()

    def _add_favorite(self, post: Post) -> None:
        if self._sync_enabled():
            self._set_status(f"Adding #{post.id} to account favorites via FlareSolverr...")
        else:
            self._set_status(f"Adding #{post.id} to local favorites...")

        self._mutation_token += 1
        token = self._mutation_token

        worker = FunctionWorker(lambda: self._add_favorite_impl(post))
        worker.signals.finished.connect(lambda _: self._favorite_mutation_finished(token, post.id, True))
        worker.signals.failed.connect(self._operation_failed)
        self._start_worker(worker)

    def _remove_favorite(self, post: Post) -> None:
        if self._sync_enabled():
            self._set_status(f"Removing #{post.id} from account favorites via FlareSolverr...")
        else:
            self._set_status(f"Removing #{post.id} from local favorites...")

        self._mutation_token += 1
        token = self._mutation_token

        worker = FunctionWorker(lambda: self._remove_favorite_impl(post))
        worker.signals.finished.connect(lambda _: self._favorite_mutation_finished(token, post.id, False))
        worker.signals.failed.connect(self._operation_failed)
        self._start_worker(worker)

    def _add_favorite_impl(self, post: Post) -> int:
        self._last_favorite_sync_failed = False
        self._last_favorite_sync_error = ""
        self._last_favorite_sync_debug = ""
        sync_client = self._make_sync_client(self.settings)
        if sync_client is not None:
            if self._degraded_mode_active():
                self._last_favorite_sync_failed = True
                self._last_favorite_sync_error = (
                    "Rate-limited degraded mode active; remote add skipped temporarily. "
                    f"Retry in {self._degraded_mode_remaining()}s."
                )
                self._last_favorite_sync_debug = ""
            else:
                try:
                    sync_client.add_favorite(post.id)
                    self._rate_limit.note_success()
                except FlareSolverrError as exc:
                    self._last_favorite_sync_failed = True
                    self._last_favorite_sync_error = str(exc)
                    self._last_favorite_sync_debug = sync_client.debug_summary()
                    self._mark_rate_limited_if_needed("favorite_add", self._last_favorite_sync_error)
                    self._log_sync_debug(
                        f"Favorite add sync failure for #{post.id}",
                        f"Error: {self._last_favorite_sync_error}\n\n{self._last_favorite_sync_debug}",
                    )

        self.local_favorites.add_favorite(post)
        return post.id

    def _remove_favorite_impl(self, post: Post) -> int:
        self._last_favorite_sync_failed = False
        self._last_favorite_sync_error = ""
        self._last_favorite_sync_debug = ""
        sync_client = self._make_sync_client(self.settings)
        if sync_client is not None:
            if self._degraded_mode_active():
                self._last_favorite_sync_failed = True
                self._last_favorite_sync_error = (
                    "Rate-limited degraded mode active; remote remove skipped temporarily. "
                    f"Retry in {self._degraded_mode_remaining()}s."
                )
                self._last_favorite_sync_debug = ""
            else:
                try:
                    sync_client.remove_favorite(post.id)
                    self._rate_limit.note_success()
                except FlareSolverrError as exc:
                    self._last_favorite_sync_failed = True
                    self._last_favorite_sync_error = str(exc)
                    self._last_favorite_sync_debug = sync_client.debug_summary()
                    self._mark_rate_limited_if_needed("favorite_remove", self._last_favorite_sync_error)
                    self._log_sync_debug(
                        f"Favorite remove sync failure for #{post.id}",
                        f"Error: {self._last_favorite_sync_error}\n\n{self._last_favorite_sync_debug}",
                    )

        self.local_favorites.remove_favorite(post.id)
        return post.id

    def _favorite_mutation_finished(self, token: int, post_id: int, favorited: bool) -> None:
        if token != self._mutation_token:
            return
        if favorited:
            self.favorite_ids.add(post_id)
        else:
            self.favorite_ids.discard(post_id)
        if self._last_favorite_sync_failed:
            self._set_status(
                f"Saved locally for #{post_id}; account sync unavailable. Debug log: {self._sync_debug_log_path}"
            )
            lines = [
                f"Account sync failed for post #{post_id}.",
                "",
                f"Error: {self._last_favorite_sync_error}",
                "",
                f"Debug log file: {self._sync_debug_log_path}",
            ]
            if self._last_favorite_sync_debug:
                lines.extend(["", "Last sync trace:", self._last_favorite_sync_debug])
            QMessageBox.warning(self, "Favorites Sync Warning", "\n".join(lines))
            self._refresh_local_favorites()
        elif self._sync_enabled():
            self._set_status(f"Favorite updated for post #{post_id}.")
            self._refresh_favorites()
        else:
            self._set_status(f"Local favorite updated for post #{post_id}.")
            self._refresh_local_favorites()

    def _operation_failed(self, error_text: str) -> None:
        self.preview_label.setText("Unable to load content.")
        self.meta_view.setPlainText(error_text)
        self._mark_rate_limited_if_needed("operation_failed", error_text)
        self._set_status("Operation failed.")
        QMessageBox.critical(self, "R34 Linux Client", error_text)

    def _handle_selection_change(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        self._update_action_state()
        if current is None:
            return
        post = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(post, Post):
            self._show_post(post)

    def _show_post(self, post: Post, allow_hydrate: bool = True) -> None:
        if allow_hydrate and self._needs_hydration(post):
            self.meta_view.setPlainText("Loading post details...")
            self.preview_label.setText("Loading preview...")

            self._hydrate_token += 1
            token = self._hydrate_token

            worker = FunctionWorker(lambda: self._hydrate_post(post))
            worker.signals.finished.connect(lambda hydrated: self._show_hydrated_post(token, post, hydrated))
            worker.signals.failed.connect(lambda error_text: self._show_hydration_failed(token, post, error_text))
            self._start_worker(worker)
            return

        if self._is_video_post(post):
            self._show_video_preview(post)
            return

        self.meta_view.setPlainText(self._format_post_metadata(post))
        self.preview_label.setText("Loading preview...")

        self._preview_token += 1
        token = self._preview_token
        if not post.best_preview_url:
            self.preview_label.setText("This post does not expose a preview URL.")
            return

        def fetch_preview() -> bytes:
            return fetch_preview_bytes(post, user_id=self.settings.user_id)

        worker = FunctionWorker(fetch_preview)
        worker.signals.finished.connect(lambda data: self._preview_loaded(token, data, post))
        worker.signals.failed.connect(lambda error_text: self._preview_failed_with_context(post, error_text))
        self._start_worker(worker)

    @staticmethod
    def _is_video_post(post: Post) -> bool:
        return is_video_post(post)

    def _current_post_is_video(self) -> bool:
        post = self._current_post()
        return self._is_video_post(post) if post is not None else False

    def _show_video_preview(self, post: Post) -> None:
        self._base_preview_pixmap = None
        self._is_long_strip_image = False
        self._image_zoom_percent = 100
        self.meta_view.setPlainText(self._format_post_metadata(post))
        source_url = post.file_url or post.sample_url or post.preview_url
        if not source_url:
            self._hide_video_view()
            self.preview_label.setText("This video post does not expose a playable URL.")
            self._set_status("Video post selected.")
            return

        if self._vlc_player is None or self._vlc_instance is None:
            self._hide_video_view()
            self.preview_label.setText("In-app video is unavailable on this build. Click 'Play Video' to open externally.")
            self._set_status("In-app video backend unavailable; using external playback.")
            return

        self.preview_container.hide()
        self.video_surface.show()

        try:
            media = self._vlc_instance.media_new(source_url)
            self._vlc_player.set_media(media)
            window_id = int(self.video_surface.winId())
            if hasattr(self._vlc_player, "set_xwindow"):
                self._vlc_player.set_xwindow(window_id)
            elif hasattr(self._vlc_player, "set_hwnd"):
                self._vlc_player.set_hwnd(window_id)
            elif hasattr(self._vlc_player, "set_nsobject"):
                self._vlc_player.set_nsobject(window_id)

            result = self._vlc_player.play()
            if result == -1:
                raise RuntimeError("VLC could not start playback")
            self._on_volume_changed(self.volume_slider.value())
            self._set_status("Playing video preview in-app.")
        except Exception as exc:
            self._hide_video_view()
            self.preview_label.setText("Unable to play this video in-app. Click 'Play Video' again to open externally.")
            self._set_status(str(exc))

    def _hide_video_view(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
        self.seek_slider.blockSignals(True)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)
        self.seek_time_label.setText("00:00 / 00:00")
        self.video_surface.hide()
        self.preview_container.show()
        self._set_preview_cursor()

    def toggle_video_playback(self) -> None:
        post = self._current_post()
        if post is None:
            return
        if not self._is_video_post(post):
            self._set_status("Selected post is not a video.")
            return

        if self._vlc_player is not None and vlc is not None and self.video_surface.isVisible():
            try:
                state = self._vlc_player.get_state()
                if state == vlc.State.Playing:
                    self._vlc_player.pause()
                    self._set_status("Video paused.")
                    return
                if state in (vlc.State.Paused, vlc.State.Stopped, vlc.State.Ended):
                    self._vlc_player.play()
                    self._set_status("Video playing.")
                    return
            except Exception:
                pass

        self._show_video_preview(post)

    def _on_volume_changed(self, value: int) -> None:
        if self._vlc_player is None:
            return
        try:
            self._vlc_player.audio_set_volume(int(value))
        except Exception:
            return

    def _on_seek_slider_pressed(self) -> None:
        self._seek_dragging = True
        self._pending_seek_ms = self.seek_slider.value()

    def _on_seek_slider_moved(self, value: int) -> None:
        self._pending_seek_ms = value
        total_ms = max(self.seek_slider.maximum(), 0)
        self.seek_time_label.setText(f"{self._format_millis(value)} / {self._format_millis(total_ms)}")

    def _on_seek_slider_released(self) -> None:
        self._seek_dragging = False
        if self._vlc_player is None:
            return
        target = int(self._pending_seek_ms)
        try:
            self._vlc_player.set_time(target)
        except Exception:
            return

    def _refresh_playback_controls(self) -> None:
        if self._vlc_player is None:
            self.seek_slider.setEnabled(False)
            return

        post = self._current_post()
        is_video = post is not None and self._is_video_post(post)
        if not is_video:
            self.seek_slider.setEnabled(False)
            return

        try:
            total_ms = max(int(self._vlc_player.get_length()), 0)
            current_ms = max(int(self._vlc_player.get_time()), 0)
        except Exception:
            self.seek_slider.setEnabled(False)
            return

        self.seek_slider.setEnabled(total_ms > 0)
        self.seek_slider.blockSignals(True)
        self.seek_slider.setRange(0, total_ms)
        if not self._seek_dragging:
            self.seek_slider.setValue(min(current_ms, total_ms))
        self.seek_slider.blockSignals(False)
        shown_ms = self.seek_slider.value() if self._seek_dragging else current_ms
        self.seek_time_label.setText(f"{self._format_millis(shown_ms)} / {self._format_millis(total_ms)}")

    @staticmethod
    def _format_millis(value: int) -> str:
        return format_millis(value)

    def _needs_hydration(self, post: Post) -> bool:
        return needs_hydration(post, self._metadata_hydrated_ids)

    def _hydrate_post(self, post: Post) -> Post:
        candidates = self.client.search_posts(f"id:{post.id}", 0, 1)
        if candidates:
            hydrated = candidates[0]
            if not hydrated.source:
                hydrated.source = hydrated.page_url
            if hydrated.file_size is None and hydrated.file_url:
                probed = self._probe_file_size(hydrated.file_url, hydrated.page_url)
                if probed is not None:
                    hydrated.file_size = probed
            return hydrated
        return post

    @staticmethod
    def _probe_file_size(url: str, referer: str) -> int | None:
        return probe_file_size(url, referer)

    def _show_hydrated_post(self, token: int, fallback: Post, hydrated: object) -> None:
        if token != self._hydrate_token:
            return
        chosen = hydrated if isinstance(hydrated, Post) else fallback
        if isinstance(chosen, Post):
            self._metadata_hydrated_ids.add(chosen.id)
            if self.left_tabs.currentWidget() is self.favorites_list:
                current_item = self.favorites_list.currentItem()
                if current_item is not None:
                    current_item.setData(Qt.ItemDataRole.UserRole, chosen)
                    current_item.setText(self._format_post_tile(chosen))
                self.favorite_posts = [chosen if item.id == chosen.id else item for item in self.favorite_posts]
                self.local_favorites.add_favorite(chosen)
            else:
                current_item = self.results_list.currentItem()
                if current_item is not None:
                    current_item.setData(Qt.ItemDataRole.UserRole, chosen)
                    current_item.setText(self._format_post_tile(chosen))
                self.current_posts = [chosen if item.id == chosen.id else item for item in self.current_posts]
            self._update_action_state()
        self._show_post(chosen, allow_hydrate=False)

    def _show_hydration_failed(self, token: int, fallback: Post, error_text: str) -> None:
        if token != self._hydrate_token:
            return
        first_line = error_text.splitlines()[-1] if error_text else "Unable to load post details"
        self._set_status(first_line)
        self._show_post(fallback, allow_hydrate=False)

    def _preview_failed(self, error_text: str) -> None:
        first_line = error_text.splitlines()[-1] if error_text else "Preview unavailable"
        self._base_preview_pixmap = None
        self._is_long_strip_image = False
        self._image_zoom_percent = 100
        self._image_pan_active = False
        self._hide_video_view()
        self.preview_label.setText("Preview unavailable for this item.")
        self._set_status(first_line)

    def _preview_failed_with_context(self, post: Post, error_text: str) -> None:
        if self.left_tabs.currentWidget() is self.favorites_list or post.id in self.favorite_ids:
            self._log_sync_debug(
                f"Favorites preview fetch failure for #{post.id}",
                "\n".join(
                    [
                        f"Error: {error_text.splitlines()[-1] if error_text else 'unknown error'}",
                        f"Post page: {post.page_url}",
                        f"Sample URL: {post.sample_url or 'n/a'}",
                        f"Preview URL: {post.preview_url or 'n/a'}",
                        f"File URL: {post.file_url or 'n/a'}",
                    ]
                ),
            )
        self._preview_failed(error_text)

    def _preview_loaded(self, token: int, data: object, post: Post) -> None:
        if token != self._preview_token or not isinstance(data, (bytes, bytearray)):
            return

        image = QImage.fromData(bytes(data))
        if image.isNull():
            self.preview_label.setText("Preview image could not be decoded.")
            return

        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.preview_label.setText("Preview image could not be loaded.")
            return

        self._base_preview_pixmap = pixmap
        self._is_long_strip_image = pixmap.height() >= (pixmap.width() * 2.2)
        self._image_zoom_percent = 100
        self._hide_video_view()
        self.preview_label.setText("")
        self._update_preview_scaling()
        if self._is_long_strip_image:
            self.preview_container.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.preview_container.verticalScrollBar().setValue(0)
        else:
            self.preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setToolTip(post.file_name)

    def _update_preview_scaling(self) -> None:
        if self._base_preview_pixmap is None:
            self._set_preview_cursor()
            return
        viewport = self.preview_container.viewport()
        target_size = viewport.size()
        if target_size.width() <= 1 or target_size.height() <= 1:
            self._set_preview_cursor()
            return

        source = self._base_preview_pixmap
        if source.width() <= 0 or source.height() <= 0:
            return

        base_width, base_height = compute_base_render_size(
            source_width=source.width(),
            source_height=source.height(),
            viewport_width=target_size.width(),
            viewport_height=target_size.height(),
            is_long_strip=self._is_long_strip_image,
            fit_mode=self._fit_mode,
        )

        zoom_factor = max(self._image_zoom_percent, 25) / 100.0
        render_width = max(1, round(base_width * zoom_factor))
        render_height = max(1, round(base_height * zoom_factor))

        scaled = source.scaled(
            render_width,
            render_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.resize(scaled.size())
        self.preview_label.setMinimumSize(scaled.size())
        self.preview_label.setPixmap(scaled)
        self._set_preview_cursor()

    def _set_image_zoom(self, value: int) -> None:
        self._image_zoom_percent = max(25, min(300, int(value)))
        self._update_preview_scaling()

    def _can_pan_image(self) -> bool:
        if self._base_preview_pixmap is None or self.video_surface.isVisible():
            return False
        horizontal = self.preview_container.horizontalScrollBar()
        vertical = self.preview_container.verticalScrollBar()
        return horizontal.maximum() > 0 or vertical.maximum() > 0

    def _set_preview_cursor(self) -> None:
        viewport = self.preview_container.viewport()
        if self._image_pan_active:
            viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._can_pan_image():
            viewport.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        viewport.unsetCursor()

    def _schedule_autocomplete(self, *_: object) -> None:
        self.autocomplete_timer.start()

    def _current_token_context(self) -> tuple[int, int, str]:
        text = self.search_input.text()
        cursor = self.search_input.cursorPosition()
        start = cursor
        while start > 0 and not text[start - 1].isspace():
            start -= 1

        end = cursor
        while end < len(text) and not text[end].isspace():
            end += 1

        return (start, end, text[start:cursor])

    def _refresh_autocomplete(self) -> None:
        start, end, prefix = self._current_token_context()
        self._autocomplete_token_start = start
        self._autocomplete_token_end = end
        self._autocomplete_query_snapshot = self.search_input.text()

        if len(prefix) < 2:
            self.completer_model.clear()
            self.completer.popup().hide()
            return

        cached = self._cached_suggestions(prefix)
        if cached:
            self._apply_autocomplete(prefix, cached)

        if prefix == self._last_autocomplete_prefix:
            return

        self._last_autocomplete_prefix = prefix

        self._autocomplete_token += 1
        token = self._autocomplete_token

        worker = FunctionWorker(lambda: self.client.autocomplete_tags(prefix))
        worker.signals.finished.connect(lambda result: self._autocomplete_finished(token, prefix, result))
        worker.signals.failed.connect(lambda error_text: self._autocomplete_failed(token, error_text))
        self._start_worker(worker)

    def _autocomplete_finished(self, token: int, prefix: str, result: object) -> None:
        if token != self._autocomplete_token or not isinstance(result, list):
            return

        suggestions = [item for item in result if isinstance(item, TagSuggestion)]
        self._autocomplete_cache[prefix] = suggestions
        self._apply_autocomplete(prefix, suggestions)

    def _autocomplete_failed(self, token: int, error_text: str) -> None:
        if token != self._autocomplete_token:
            return
        self._set_status(f"Autocomplete unavailable: {error_text.splitlines()[0]}")

    def _cached_suggestions(self, prefix: str) -> list[TagSuggestion]:
        if prefix in self._autocomplete_cache:
            return self._autocomplete_cache[prefix]

        matching_prefixes = [key for key in self._autocomplete_cache if prefix.startswith(key)]
        if not matching_prefixes:
            return []

        nearest_prefix = max(matching_prefixes, key=len)
        return [item for item in self._autocomplete_cache[nearest_prefix] if item.value.startswith(prefix)]

    def _apply_autocomplete(self, prefix: str, suggestions: list[TagSuggestion]) -> None:
        start, end, active_prefix = self._current_token_context()
        if active_prefix != prefix:
            return

        self._autocomplete_token_start = start
        self._autocomplete_token_end = end
        self._autocomplete_query_snapshot = self.search_input.text()

        self.completer_model.clear()
        for suggestion in suggestions:
            item = QStandardItem(suggestion.display_text)
            item.setData(suggestion.value, Qt.ItemDataRole.UserRole)
            self.completer_model.appendRow(item)

        if self.completer_model.rowCount() <= 0:
            self.completer.popup().hide()
            return

        self.completer.setCompletionPrefix(prefix)
        self.completer.complete()

    def _insert_completion(self, completion: str) -> None:
        value = completion.strip()
        if not value:
            return

        snapshot = self._autocomplete_query_snapshot or self.search_input.text()
        start = self._autocomplete_token_start
        end = self._autocomplete_token_end
        QTimer.singleShot(0, lambda: self._apply_completion_to_token(value, snapshot, start, end))

    def _apply_completion_to_token(self, value: str, snapshot: str, start: int, end: int) -> None:
        text = snapshot
        if start < 0 or end < start or end > len(text):
            live_text = self.search_input.text()
            start, end, _ = self._current_token_context()
            text = live_text
            if start < 0 or end < start or end > len(text):
                return

        new_text = f"{text[:start]}{value}{text[end:]}"
        cursor_pos = start + len(value)

        if cursor_pos >= len(new_text):
            new_text = f"{new_text} "
            cursor_pos = len(new_text)

        self.search_input.setText(new_text)
        self.search_input.setCursorPosition(cursor_pos)
        self.completer.popup().hide()
        self._schedule_autocomplete()

    def _format_post_metadata(self, post: Post) -> str:
        return format_post_metadata(post)

    @staticmethod
    def _format_post_tile(post: Post) -> str:
        return format_post_tile(post)

    def _current_post(self) -> Post | None:
        if self.left_tabs.currentWidget() is self.favorites_list:
            item = self.favorites_list.currentItem()
        else:
            item = self.results_list.currentItem()
        if item is None:
            return None
        post = item.data(Qt.ItemDataRole.UserRole)
        return post if isinstance(post, Post) else None

    def _active_posts_list(self) -> QListWidget:
        return self.favorites_list if self.left_tabs.currentWidget() is self.favorites_list else self.results_list

    def _move_selection(self, delta: int) -> None:
        target_list = self._active_posts_list()
        if target_list.count() <= 0:
            return
        current_row = target_list.currentRow()
        if current_row < 0:
            current_row = 0
        new_row = max(0, min(target_list.count() - 1, current_row + delta))
        target_list.setCurrentRow(new_row)

    def _toggle_current_favorite(self) -> None:
        post = self._current_post()
        if post is None:
            return
        if post.id in self.favorite_ids:
            self._remove_favorite(post)
        else:
            self._add_favorite(post)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        super().keyPressEvent(event)

    def open_selected_post(self) -> None:
        post = self._current_post()
        if post is None:
            return
        QDesktopServices.openUrl(QUrl(post.page_url))

    def _open_multiple_posts(self, posts: list[Post]) -> None:
        unique_posts = {post.id: post for post in posts}
        if not unique_posts:
            return
        for post in unique_posts.values():
            QDesktopServices.openUrl(QUrl(post.page_url))
        self._set_status(f"Opened {len(unique_posts)} posts in browser.")

    def copy_selected_link(self) -> None:
        post = self._current_post()
        if post is None:
            return
        QApplication.clipboard().setText(post.page_url)
        self._set_status("Post link copied to clipboard.")

    def download_selected_post(self) -> None:
        post = self._current_post()
        if post is None:
            return

        target_directory = self.settings.download_directory or self.store.default_download_directory()
        if not target_directory:
            target_directory = QFileDialog.getExistingDirectory(self, "Choose download folder")
        if not target_directory:
            return

        self._set_status(f"Downloading {post.file_name}...")

        def download() -> Path:
            return self._download_post_to_directory(post, target_directory)

        self._download_token += 1
        token = self._download_token

        worker = FunctionWorker(download)
        worker.signals.finished.connect(lambda result: self._download_finished(token, result))
        worker.signals.failed.connect(self._operation_failed)
        self._start_worker(worker)

    def _download_multiple_posts(self, posts: list[Post]) -> None:
        unique_posts = list({post.id: post for post in posts}.values())
        if not unique_posts:
            return

        target_directory = self.settings.download_directory or self.store.default_download_directory()
        if not target_directory:
            target_directory = QFileDialog.getExistingDirectory(self, "Choose download folder")
        if not target_directory:
            return

        self._set_status(f"Downloading {len(unique_posts)} selected favorites...")

        def download_many() -> list[Path]:
            output: list[Path] = []
            for post in unique_posts:
                output.append(self._download_post_to_directory(post, target_directory))
            return output

        self._download_token += 1
        token = self._download_token

        worker = FunctionWorker(download_many)
        worker.signals.finished.connect(lambda result: self._download_many_finished(token, result))
        worker.signals.failed.connect(self._operation_failed)
        self._start_worker(worker)

    def _download_post_to_directory(self, post: Post, target_directory: str) -> Path:
        resolved = self._resolve_download_post(post)
        url = resolved.download_url
        if not url:
            raise RuntimeError("This post does not expose a downloadable file URL.")

        destination = Path(target_directory) / resolved.file_name
        if destination.exists():
            destination = destination.with_name(f"{destination.stem}-{resolved.id}{destination.suffix}")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": resolved.page_url,
            "Accept": "*/*",
        }
        response = requests.get(url, timeout=60, stream=True, headers=headers)
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    file_handle.write(chunk)
        return destination

    @staticmethod
    def _download_url_needs_hydration(url: str) -> bool:
        return download_url_needs_hydration(url)

    def _resolve_download_post(self, post: Post) -> Post:
        if not self._download_url_needs_hydration(post.download_url):
            return post
        candidates = self.client.search_posts(f"id:{post.id}", 0, 1)
        if not candidates:
            return post
        hydrated = candidates[0]
        if self._download_url_needs_hydration(hydrated.download_url):
            return post
        return hydrated

    def _start_worker(self, worker: FunctionWorker) -> None:
        self._active_workers.add(worker)

        def release_worker(*_: object) -> None:
            self._active_workers.discard(worker)

        worker.signals.finished.connect(release_worker)
        worker.signals.failed.connect(release_worker)
        self.pool.start(worker)

    def _download_finished(self, token: int, result: object) -> None:
        if token != self._download_token:
            return
        if isinstance(result, Path):
            self._set_status(f"Saved to {result}")

    def _download_many_finished(self, token: int, result: object) -> None:
        if token != self._download_token:
            return
        paths = [item for item in result if isinstance(item, Path)] if isinstance(result, list) else []
        self._set_status(f"Saved {len(paths)} files.")

    def open_settings(self, initial: bool = False) -> None:
        dialog = SettingsDialog(self.settings, self.store, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            if initial and not self.settings.has_credentials:
                self._set_status("Credentials are required to search.")
            return

        self.settings = dialog.current_settings()
        self.store.save(self.settings)
        self.client = self._make_client(self.settings)
        self._configure_background_sync_timer()
        self._refresh_collection_filter()
        if self.settings.flaresolverr_enabled:
            self._set_status("Settings saved. FlareSolverr sync is enabled.")
        else:
            self._set_status("Settings saved.")
        self._refresh_favorites()

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._update_preview_scaling()

    def eventFilter(self, watched, event):  # type: ignore[override]
        if watched is self.preview_container.viewport():
            if event.type() == QEvent.Type.Resize:
                self._update_preview_scaling()
            elif event.type() == QEvent.Type.MouseButtonPress:
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and self._can_pan_image()
                    and not bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                ):
                    self._image_pan_active = True
                    position = event.position()
                    self._image_pan_start_pos = (int(position.x()), int(position.y()))
                    horizontal = self.preview_container.horizontalScrollBar()
                    vertical = self.preview_container.verticalScrollBar()
                    self._image_pan_start_scroll = (horizontal.value(), vertical.value())
                    self._set_preview_cursor()
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                if self._image_pan_active:
                    position = event.position()
                    current_x = int(position.x())
                    current_y = int(position.y())
                    delta_x = current_x - self._image_pan_start_pos[0]
                    delta_y = current_y - self._image_pan_start_pos[1]
                    horizontal = self.preview_container.horizontalScrollBar()
                    vertical = self.preview_container.verticalScrollBar()
                    horizontal.setValue(self._image_pan_start_scroll[0] - delta_x)
                    vertical.setValue(self._image_pan_start_scroll[1] - delta_y)
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._image_pan_active and event.button() == Qt.MouseButton.LeftButton:
                    self._image_pan_active = False
                    self._set_preview_cursor()
                    return True
            elif event.type() == QEvent.Type.Leave:
                if self._image_pan_active:
                    self._image_pan_active = False
                self._set_preview_cursor()
            elif event.type() == QEvent.Type.Wheel:
                if (
                    self._base_preview_pixmap is not None
                    and not self.video_surface.isVisible()
                    and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                ):
                    delta = event.angleDelta().y()
                    if delta > 0:
                        self._set_image_zoom(self._image_zoom_percent + 10)
                    elif delta < 0:
                        self._set_image_zoom(self._image_zoom_percent - 10)
                    self._set_status(f"Zoom {self._image_zoom_percent}%")
                    return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):  # type: ignore[override]
        self.store.save(self.settings)
        super().closeEvent(event)
