from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import QEvent, QThreadPool, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeyEvent, QPixmap, QShortcut
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCompleter,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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

from r34_client.api.client import Rule34Client
from r34_client.core.worker import FunctionWorker
from r34_client.core.settings import AppSettings, SettingsStore
from r34_client.api.flaresolverr import FlareSolverrFavoritesClient
from r34_client.core.db import LocalFavoritesStore
from r34_client.core.state import AppState
from r34_client.core.models import Post, TagSuggestion
from r34_client.core.rate_limit import DegradedModeController, TokenBucket
from r34_client.core.worker_pools import build_worker_pools
from r34_client.ui.dialogs.diagnostics import DiagnosticsSnapshot
from r34_client.ui.helpers.image_fit import FitMode
from r34_client.ui.helpers.post import (
    download_url_needs_hydration,
    format_millis,
    format_post_metadata,
    format_post_tile,
    is_video_post,
    needs_hydration,
    probe_file_size,
)
from r34_client.ui.helpers.prefetch import ImageCache, prefetch_adjacent, prefetch_images_batch, prefetch_metadata_batch
from r34_client.ui.features import autocomplete as autocomplete_feature
from r34_client.ui.features import context_menu as context_menu_feature
from r34_client.ui.dialogs import controls as dialogs_feature
from r34_client.ui.features import downloads as downloads_feature
from r34_client.ui.favorites import controller as favorites_feature
from r34_client.ui.friends import controller as friends_feature
from r34_client.ui.features import media as media_feature
from r34_client.ui.features import navigation as navigation_feature
from r34_client.ui.features import preview as preview_feature
from r34_client.ui.search import controller as search_feature
from r34_client.ui.features import settings_action as settings_feature
from r34_client.ui.features import status as status_feature
from r34_client.ui.widgets.custom import ClickSeekSlider, ClickVideoSurface


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("R34 Linux Client")
        self.resize(1320, 840)

        self.store = store
        self.settings = store.load()
        self.client = self._make_client(self.settings)
        self.local_favorites = LocalFavoritesStore()
        from r34_client.core.download_manager import DownloadManager
        self.download_manager = DownloadManager(self.local_favorites)
        self._worker_pools = build_worker_pools()

        self.state = AppState()
        self.state.search_completed.connect(self._on_search_completed)
        self.state.favorites_updated.connect(self._on_favorites_updated)
        self.state.friend_favorites_updated.connect(self._on_friend_favorites_updated)
        self.state.page_changed.connect(self._on_page_changed)
        self.state.query_changed.connect(self._on_query_changed)
        self._search_history_limit = 12
        self._search_history = self.store.load_search_history(self._search_history_limit)
        self._saved_searches_limit = 12
        self._saved_searches = self.store.load_saved_searches(self._saved_searches_limit)
        self._pinned_filters_limit = 8
        self._pinned_filters = self.store.load_pinned_filters(self._pinned_filters_limit)
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
        self._pending_remote_add_ids: set[int] = set()
        self._pending_remote_remove_ids: set[int] = set()
        self._pending_remote_add_meta: dict[int, dict] = {}
        self._pending_remote_remove_meta: dict[int, dict] = {}
        self._pending_endpoint_streaks: dict[str, int] = {"add": 0, "remove": 0}
        self._pending_state_loaded = False
        self._pending_sync_worker_active = False
        self._sync_active_workers = 0
        self._pending_sync_started_at = 0.0
        self._pending_sync_last_restart_at = 0.0
        import threading
        self._pending_state_lock = threading.Lock()
        self._sync_debug_log_path = self.local_favorites.database_path.parent / "sync-debug.log"
        self._is_long_strip_image = False

        # Image preview cache for prefetching
        self._image_cache = ImageCache(max_size=100)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tags, e.g. character rating:safe")
        self.search_input.returnPressed.connect(self.search)
        self.search_input.textEdited.connect(self._schedule_autocomplete)
        self.search_input.textChanged.connect(self._update_action_state)

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

        self.search_history_combo = QComboBox()
        self.search_history_combo.setMinimumWidth(220)
        self.search_history_combo.activated[int].connect(self._on_search_history_selected)

        self.saved_searches_combo = QComboBox()
        self.saved_searches_combo.setMinimumWidth(220)
        self.saved_searches_combo.activated[int].connect(self._on_saved_search_selected)

        self.pinned_filters_combo = QComboBox()
        self.pinned_filters_combo.setMinimumWidth(220)
        self.pinned_filters_combo.activated[int].connect(self._on_pinned_filter_selected)

        self.save_search_button = QPushButton("Save search")
        self.save_search_button.clicked.connect(self._save_current_search)

        self.pin_filter_button = QPushButton("Pin filter")
        self.pin_filter_button.clicked.connect(self._toggle_current_pinned_filter)

        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.previous_page)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)

        self.page_label = QLabel("Page 1")

        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results_list.currentItemChanged.connect(self._handle_selection_change)
        self.results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self._open_results_context_menu)

        self.favorites_list = QListWidget()
        self.favorites_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.favorites_list.currentItemChanged.connect(self._handle_selection_change)
        self.favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self._open_favorites_context_menu)

        self.friends_list = QListWidget()
        self.friends_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.friends_list.itemClicked.connect(self._on_friend_selected)

        self.add_friend_button = QPushButton("Add Friend")
        self.add_friend_button.clicked.connect(self._add_friend_dialog)

        self.remove_friend_button = QPushButton("Remove Friend")
        self.remove_friend_button.clicked.connect(self._remove_friend_dialog)

        self.friend_posts_list = QListWidget()
        self.friend_posts_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.friend_posts_list.currentItemChanged.connect(self._handle_selection_change)
        self.friend_posts_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.friend_posts_list.customContextMenuRequested.connect(self._open_friend_posts_context_menu)

        self.collection_filter = QComboBox()
        self.collection_filter.addItem("All Favorites", None)
        self.collection_filter.currentIndexChanged.connect(self._on_collection_filter_changed)

        self.manage_collections_button = QPushButton("Collections")
        self.manage_collections_button.clicked.connect(self._open_collection_manager)

        self.related_tags_label = QLabel("Related tags")
        self.related_tags_list = QListWidget()
        self.related_tags_list.setMaximumHeight(140)
        self.related_tags_list.itemClicked.connect(self._related_tag_selected)
        self.related_tags_list.setEnabled(False)

        self.friends_tab = QWidget()
        friends_layout = QVBoxLayout(self.friends_tab)
        friends_layout.setContentsMargins(0, 0, 0, 0)

        friend_buttons = QHBoxLayout()
        friend_buttons.addWidget(self.add_friend_button)
        friend_buttons.addWidget(self.remove_friend_button)
        friends_layout.addLayout(friend_buttons)

        friends_layout.addWidget(QLabel("Friends"))
        friends_layout.addWidget(self.friends_list, 1)

        friends_layout.addWidget(QLabel("Friend's Favorites"))
        self.friend_page_label = QLabel("")
        friends_layout.addWidget(self.friend_page_label)
        friends_layout.addWidget(self.friend_posts_list, 2)

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self.results_list, "Search Results")
        self.left_tabs.addTab(self.favorites_list, "Favorites")
        self.left_tabs.addTab(self.friends_tab, "Friends")
        self.left_tabs.currentChanged.connect(self._on_tab_changed)

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

        from r34_client.ui.widgets.video_player import VideoPlayer
        self.video_player = VideoPlayer(self)

        self._base_preview_pixmap: QPixmap | None = None
        self._image_zoom_percent = 100
        self._fit_mode = FitMode.SMART
        self._image_pan_active = False
        self._image_pan_start_pos: tuple[int, int] = (0, 0)
        self._image_pan_start_scroll: tuple[int, int] = (0, 0)
        self._mutation_token = 0
        self._download_token = 0
        self._single_download_token = 0
        self._bulk_download_token = 0
        self._hydrate_token = 0
        self._friend_fetch_token = 0
        self._prefetch_metadata_token = 0
        self._friend_current_page = 0
        self._friend_user_id: str = ""
        self._friend_has_more = False
        self._rate_limit = DegradedModeController()
        # Keep remote mutation flow paced even under large pending queues.
        self._remote_mutation_bucket = TokenBucket(capacity=8.0, refill_rate_per_second=1.25)

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
        self._seek_was_playing = False
        self._seek_ui_locked = False
        self._seek_ui_unlock_deadline = 0.0
        self._seek_ui_hold_ms = 0
        self._seek_ui_stable_ticks = 0
        self._pending_seek_ms = 0
        self._pending_seek_target_ms: int | None = None
        self._pending_seek_deadline = 0.0
        self._pending_seek_retries = 0

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(250)
        self.playback_timer.timeout.connect(self._refresh_playback_controls)
        self.playback_timer.start()

        self.background_sync_timer = QTimer(self)
        self.background_sync_timer.timeout.connect(self._background_sync_tick)

        self.pending_remote_sync_timer = QTimer(self)
        self.pending_remote_sync_timer.timeout.connect(self._pending_remote_sync_tick)

        self.copy_button = QPushButton("Copy Link")
        self.copy_button.clicked.connect(self.copy_selected_link)

        self._global_shortcuts: list[QShortcut] = []

        self._build_layout()
        self._build_toolbar()
        favorites_feature.restore_pending_remote_mutations(self)
        self._register_global_shortcuts()
        self._refresh_search_history()
        self._refresh_saved_searches()
        self._refresh_pinned_filters()
        self._refresh_collection_filter()
        self._refresh_related_tags([])
        self._configure_background_sync_timer()
        self._configure_pending_sync_timer()
        self._update_action_state()
        # Startup should never block on remote sync; load local cache first.
        self._refresh_local_favorites()
        friends_feature._refresh_friends_list(self)
        self._shutdown_in_progress = False

        if not self.settings.has_credentials:
            self._set_left_status("Enter API credentials in Settings before searching.")
            self.open_settings(initial=True)
        else:
            self._set_left_status("Ready.")

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
            timeout=20,
            max_timeout_ms=20000,
        )

    def _sync_enabled(self) -> bool:
        return self.settings.flaresolverr_enabled and self.settings.has_credentials

    def _configure_background_sync_timer(self) -> None:
        interval_minutes = max(0, int(self.settings.background_sync_interval_minutes))
        if interval_minutes <= 0 or not self._sync_enabled():
            self.background_sync_timer.stop()
            return
        self.background_sync_timer.setInterval(interval_minutes * 60 * 1000)
        self.background_sync_timer.start()

    def _configure_pending_sync_timer(self) -> None:
        if not self._sync_enabled():
            self.pending_remote_sync_timer.stop()
            return
        self.pending_remote_sync_timer.setInterval(4000)
        self.pending_remote_sync_timer.start()

    def _background_sync_tick(self) -> None:
        if not self._sync_enabled():
            return
        if self._sync_active_workers > 0:
            return
        self._sync_active_workers += 1
        self._refresh_favorites()

    def _pending_remote_sync_tick(self) -> None:
        favorites_feature.process_pending_remote_mutations(self)

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

    def _refresh_search_history(self) -> None:
        search_feature.refresh_search_history(self)

    def _on_search_history_selected(self, index: int) -> None:
        search_feature.on_search_history_activated(self, index)

    def _refresh_saved_searches(self) -> None:
        search_feature.refresh_saved_searches(self)

    def _on_saved_search_selected(self, index: int) -> None:
        search_feature.on_saved_search_activated(self, index)

    def _save_current_search(self) -> None:
        search_feature.save_current_search(self)

    def _refresh_pinned_filters(self) -> None:
        search_feature.refresh_pinned_filters(self)

    def _on_pinned_filter_selected(self, index: int) -> None:
        search_feature.on_pinned_filter_activated(self, index)

    def _toggle_current_pinned_filter(self) -> None:
        search_feature.toggle_pinned_filter(self)

    def _refresh_related_tags(self, posts: list[Post]) -> None:
        search_feature.update_related_tags(self, posts)

    def _related_tag_selected(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        query = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(query, str) or not query.strip():
            return
        combined_query = f"{self.current_query} {query}".strip()
        search_feature.apply_search_query(self, combined_query)

    def _on_collection_filter_changed(self, _: int) -> None:
        # Preserve the current selection across the refresh.
        saved = self._current_post()
        saved_id = saved.id if saved is not None else None
        self._refresh_favorites()
        if saved_id is not None:
            for row in range(self.favorites_list.count()):
                item = self.favorites_list.item(row)
                if item is None:
                    continue
                candidate = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(candidate, Post) and candidate.id == saved_id:
                    self.favorites_list.setCurrentItem(item)
                    break

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
        search_row.addWidget(QLabel("Recent"))
        search_row.addWidget(self.search_history_combo)
        search_row.addWidget(self.prev_button)
        search_row.addWidget(self.next_button)
        search_row.addWidget(self.page_label)
        layout.addLayout(search_row)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Pinned"))
        preset_row.addWidget(self.pinned_filters_combo)
        preset_row.addWidget(QLabel("Saved"))
        preset_row.addWidget(self.saved_searches_combo)
        preset_row.addWidget(self.save_search_button)
        preset_row.addWidget(self.pin_filter_button)
        layout.addLayout(preset_row)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        collection_row = QHBoxLayout()
        collection_row.addWidget(QLabel("Collection"))
        collection_row.addWidget(self.collection_filter, 1)
        collection_row.addWidget(self.manage_collections_button)
        left_layout.addLayout(collection_row)

        left_layout.addWidget(self.related_tags_label)
        left_layout.addWidget(self.related_tags_list)

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
        
        # Setup status bar with left (client info) and right (sync info) sections
        status_bar = QStatusBar()
        self.left_status_label = QLabel("Ready.")
        self.right_status_label = QLabel("")
        status_bar.addWidget(self.left_status_label)
        status_bar.addPermanentWidget(self.right_status_label)
        self.setStatusBar(status_bar)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)

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
        navigation_feature.register_global_shortcuts(self)

    def _invoke_global_navigation(self, callback) -> None:
        navigation_feature.invoke_global_navigation(self, callback)

    def _update_action_state(self) -> None:
        status_feature.update_action_state(self)

    def _set_left_status(self, message: str) -> None:
        status_feature.set_left_status(self, message)
    
    def _set_right_status(self, message: str) -> None:
        status_feature.set_right_status(self, message)
    
    def _set_status(self, message: str) -> None:
        status_feature.set_status(self, message)

    def _set_fit_mode(self, mode: FitMode) -> None:
        status_feature.set_fit_mode(self, mode)

    def _cancel_current_operations(self) -> None:
        status_feature.cancel_current_operations(self)

    def _diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        return dialogs_feature.diagnostics_snapshot(self)

    def _open_diagnostics(self) -> None:
        dialogs_feature.open_diagnostics(self)

    def _open_controls(self) -> None:
        dialogs_feature.open_controls(self)

    def _mark_rate_limited_if_needed(self, context: str, error_message: str) -> None:
        status_feature.mark_rate_limited_if_needed(self, context, error_message)

    def _degraded_mode_remaining(self) -> int:
        return status_feature.degraded_mode_remaining(self)

    def _degraded_mode_active(self) -> bool:
        return status_feature.degraded_mode_active(self)

    def _log_sync_debug(self, title: str, details: str) -> None:
        status_feature.log_sync_debug(self, title, details)

    def _update_friend_page_label(self) -> None:
        if self._friend_user_id:
            page_num = self._friend_current_page + 1
            label = f"Page {page_num}"
            if not self._friend_has_more and self.friend_posts:
                label += " (last)"
            elif self._friend_has_more:
                label += "+"
            self.friend_page_label.setText(label)
        else:
            self.friend_page_label.setText("")

    def search(self) -> None:
        search_feature.search(self)

    def next_page(self) -> None:
        if self.left_tabs.currentWidget() is self.friends_tab:
            friends_feature.next_friend_page(self)
        else:
            search_feature.next_page(self)

    def previous_page(self) -> None:
        if self.left_tabs.currentWidget() is self.friends_tab:
            friends_feature.prev_friend_page(self)
        else:
            search_feature.previous_page(self)

    def _run_search(self) -> None:
        search_feature.run_search(self)

    def _search_finished(self, token: int, result: object) -> None:
        search_feature.search_finished(self, token, result)

    def _refresh_favorites(self) -> None:
        search_feature.refresh_favorites(self)

    def _refresh_local_favorites(self) -> None:
        search_feature.refresh_local_favorites(self)

    def _refresh_favorites_impl(self, local_only: bool) -> None:
        search_feature.refresh_favorites_impl(self, local_only)

    def _sync_remote_favorites(self) -> tuple[list[Post], bool]:
        return search_feature.sync_remote(self)

    def _favorites_loaded(self, token: int, result: object) -> None:
        self._sync_active_workers = max(0, self._sync_active_workers - 1)
        search_feature.favorites_loaded(self, token, result)

    def _favorites_failed(self, token: int, error_text: str) -> None:
        self._sync_active_workers = max(0, self._sync_active_workers - 1)
        search_feature.favorites_failed(self, token, error_text)

    def _open_results_context_menu(self, position) -> None:
        context_menu_feature.open_results_context_menu(self, position)

    def _selected_results_posts(self) -> list[Post]:
        return context_menu_feature.selected_results_posts(self)

    def _add_multiple_favorites(self, posts: list[Post]) -> None:
        favorites_feature.add_multiple_favorites(self, posts)

    def _open_favorites_context_menu(self, position) -> None:
        context_menu_feature.open_favorites_context_menu(self, position)

    def _selected_favorite_posts(self) -> list[Post]:
        return context_menu_feature.selected_favorite_posts(self)

    def _remove_multiple_favorites(self, posts: list[Post]) -> None:
        favorites_feature.remove_multiple_favorites(self, posts)

    def _assign_selection_to_new_collection(self, posts: list[Post]) -> None:
        favorites_feature.assign_selection_to_new_collection(self, posts)

    def _assign_selection_to_collection(self, posts: list[Post], collection_name: str) -> None:
        favorites_feature.assign_selection_to_collection(self, posts, collection_name)

    def _remove_selection_from_collection(self, posts: list[Post], collection_name: str) -> None:
        favorites_feature.remove_selection_from_collection(self, posts, collection_name)

    def _add_favorite(self, post: Post) -> None:
        favorites_feature.add_favorite(self, post)

    def _remove_favorite(self, post: Post) -> None:
        favorites_feature.remove_favorite(self, post)

    def _add_favorite_impl(self, post: Post) -> int:
        return favorites_feature.add_favorite_impl(self, post)

    def _remove_favorite_impl(self, post: Post) -> int:
        return favorites_feature.remove_favorite_impl(self, post)

    def _favorite_mutation_finished(self, token: int, post_id: int, favorited: bool) -> None:
        favorites_feature.favorite_mutation_finished(self, token, post_id, favorited)

    def _operation_failed(self, error_text: str) -> None:
        favorites_feature.operation_failed(self, error_text)

    def _add_friend_dialog(self) -> None:
        friends_feature.add_friend_dialog(self)

    def _remove_friend_dialog(self) -> None:
        friends_feature.remove_friend_dialog(self)

    def _on_friend_selected(self, item: QListWidgetItem | None) -> None:
        friends_feature.load_friend_favorites(self, item)

    def _open_friend_posts_context_menu(self, position) -> None:
        context_menu_feature.open_friend_posts_context_menu(self, position)

    def _handle_selection_change(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        preview_feature.handle_selection_change(self, current, _)

    def _on_tab_changed(self, _index: int) -> None:
        self._update_action_state()
        active_list = self._active_posts_list()
        if active_list.count() <= 0:
            self._hide_video_view()
            self._base_preview_pixmap = None
            self.preview_label.clear()
            self.meta_view.clear()
            return
        current = active_list.currentItem()
        if current is None and active_list.count() > 0:
            # This emits currentItemChanged in the normal path and updates the preview there.
            active_list.setCurrentRow(0)
            current = active_list.currentItem()
        if current is not None:
            # Force sync in case currentItemChanged did not fire because the row was already current.
            self._handle_selection_change(current, None)

    def _show_post(self, post: Post, allow_hydrate: bool = True) -> None:
        preview_feature.show_post(self, post, allow_hydrate)

    @staticmethod
    def _is_video_post(post: Post) -> bool:
        return is_video_post(post)

    def _current_post_is_video(self) -> bool:
        return preview_feature.current_post_is_video(self)

    def _show_video_preview(self, post: Post) -> None:
        media_feature.show_video_preview(self, post)

    def _hide_video_view(self) -> None:
        media_feature.hide_video_view(self)

    def toggle_video_playback(self) -> None:
        media_feature.toggle_video_playback(self)

    def _on_volume_changed(self, value: int) -> None:
        media_feature.on_volume_changed(self, value)

    def _on_seek_slider_pressed(self) -> None:
        media_feature.on_seek_slider_pressed(self)

    def _on_seek_slider_moved(self, value: int) -> None:
        media_feature.on_seek_slider_moved(self, value)

    def _on_seek_slider_released(self) -> None:
        media_feature.on_seek_slider_released(self)

    def _refresh_playback_controls(self) -> None:
        media_feature.refresh_playback_controls(self)

    @staticmethod
    def _format_millis(value: int) -> str:
        return format_millis(value)

    def _needs_hydration(self, post: Post) -> bool:
        return needs_hydration(post, self._metadata_hydrated_ids)

    def _hydrate_post(self, post: Post) -> Post:
        return preview_feature.hydrate_post(self, post)

    @staticmethod
    def _probe_file_size(url: str, referer: str) -> int | None:
        return probe_file_size(url, referer)

    def _show_hydrated_post(self, token: int, fallback: Post, hydrated: object) -> None:
        preview_feature.show_hydrated_post(self, token, fallback, hydrated)

    def _show_hydration_failed(self, token: int, fallback: Post, error_text: str) -> None:
        preview_feature.show_hydration_failed(self, token, fallback, error_text)

    def _preview_failed(self, error_text: str) -> None:
        preview_feature.preview_failed(self, error_text)

    def _preview_failed_with_context(self, post: Post, error_text: str) -> None:
        preview_feature.preview_failed_with_context(self, post, error_text)

    def _preview_loaded(self, token: int, data: object, post: Post) -> None:
        preview_feature.preview_loaded(self, token, data, post)

    def _prefetch_images(self, posts: list[Post], *, limit: int = 5) -> None:
        """Prefetch preview images for *posts* in the background.

        Skips posts already cached.  Use after search results load to warm the
        cache for all visible results.  Also triggers a background metadata
        (hydration) prefetch for the same window.
        """
        if not posts or not self.settings.user_id:
            return
        worker = FunctionWorker(
            prefetch_images_batch,
            posts,
            self.settings.user_id,
            self._image_cache,
            limit=limit,
        )
        worker.signals.failed.connect(lambda _: None)  # Silently swallow errors.
        self._start_worker(worker, workload="general")

        # Also prefetch metadata for the first *limit* posts.
        self._prefetch_metadata_for_posts(posts, start=0, count=limit)

    def _prefetch_adjacent(self, post: Post, *, count: int = 5) -> None:
        """Prefetch posts around *post* in the current active list.

        Warms both the image cache and the metadata for upcoming posts so
        J/K navigation is instant.
        """
        # Determine which post list corresponds to the active tab.
        if self.left_tabs.currentWidget() is self.favorites_list:
            posts = self.favorite_posts
        elif self.left_tabs.currentWidget() is self.friends_tab:
            posts = self.friend_posts
        else:
            posts = self.current_posts
        if not posts or not self.settings.user_id:
            return
        worker = FunctionWorker(
            prefetch_adjacent,
            post,
            posts,
            self.settings.user_id,
            self._image_cache,
            count=count,
        )
        worker.signals.failed.connect(lambda _: None)
        self._start_worker(worker, workload="general")

        # Also prefetch metadata for the same range.
        self._prefetch_metadata_for_posts(posts, around=post, count=count)

    def _prefetch_metadata_for_posts(
        self,
        posts: list[Post],
        *,
        around: Post | None = None,
        start: int = 0,
        count: int = 5,
    ) -> None:
        """Hydrate upcoming posts in the background.

        Picks up to *count* posts starting from *start* (or centred on
        *around*), calls the API to fill in missing fields, and updates the
        list items in-place on the main thread.
        """
        if not posts or not self.settings.has_credentials:
            return

        self._prefetch_metadata_token += 1
        token = self._prefetch_metadata_token

        # Pick the slice of posts to prefetch.
        if around is not None:
            try:
                idx = posts.index(around)
            except ValueError:
                return
            candidates = []
            # Next items (most likely navigation targets)
            candidates.extend(posts[idx + 1 : idx + 1 + count])
            # Items before the current one
            start_before = max(0, idx - count)
            candidates.extend(posts[start_before:idx])
        else:
            candidates = posts[start : start + count]

        if not candidates:
            return

        # Filter to only posts that still need hydration.
        todo = [p for p in candidates if needs_hydration(p, self._metadata_hydrated_ids)]
        if not todo:
            return

        worker = FunctionWorker(
            prefetch_metadata_batch,
            todo,
            self.client,
            limit=len(todo),
        )
        worker.signals.finished.connect(lambda result, t=token: self._apply_prefetched_metadata(t, result))
        worker.signals.failed.connect(lambda _: None)
        self._start_worker(worker, workload="general")

    def _apply_prefetched_metadata(self, token: int, result: object) -> None:
        """Callback: apply hydrated Post dict to the active list."""
        if token != self._prefetch_metadata_token:
            return
        if not isinstance(result, dict):
            return

        # Determine which list pair to update.
        if self.left_tabs.currentWidget() is self.favorites_list:
            list_widget = self.favorites_list
            store = self.favorite_posts
        elif self.left_tabs.currentWidget() is self.friends_tab:
            list_widget = self.friend_posts_list
            store = self.friend_posts
        else:
            list_widget = self.results_list
            store = self.current_posts

        # Helper: find item by post id.
        def _find_item(post_id: int):
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item is None:
                    continue
                candidate = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(candidate, Post) and candidate.id == post_id:
                    return item, row
            return None, -1

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem

        changed: set[int] = set()
        for post_id, hydrated in result.items():
            if not isinstance(hydrated, Post):
                continue
            self._metadata_hydrated_ids.add(post_id)
            changed.add(post_id)

            # Update the list item.
            item, _ = _find_item(post_id)
            if item is not None:
                item.setData(Qt.ItemDataRole.UserRole, hydrated)
                item.setText(self._format_post_tile(hydrated))

            # Update the stored list in-place.
            for i, p in enumerate(store):
                if p.id == post_id:
                    store[i] = hydrated
                    break

        # If the currently shown post got hydrated, refresh the preview panel.
        current = self._current_post()
        if current is not None and current.id in changed:
            self._show_post(current, allow_hydrate=False)

    def _update_preview_scaling(self) -> None:
        preview_feature.update_preview_scaling(self)

    def _set_image_zoom(self, value: int) -> None:
        preview_feature.set_image_zoom(self, value)

    def _can_pan_image(self) -> bool:
        return preview_feature.can_pan_image(self)

    def _set_preview_cursor(self) -> None:
        preview_feature.set_preview_cursor(self)

    def _schedule_autocomplete(self, *_: object) -> None:
        autocomplete_feature.schedule_autocomplete(self)

    def _current_token_context(self) -> tuple[int, int, str]:
        return autocomplete_feature.current_token_context(self)

    def _refresh_autocomplete(self) -> None:
        autocomplete_feature.refresh_autocomplete(self)

    def _autocomplete_finished(self, token: int, prefix: str, result: object) -> None:
        autocomplete_feature.autocomplete_finished(self, token, prefix, result)

    def _autocomplete_failed(self, token: int, error_text: str) -> None:
        autocomplete_feature.autocomplete_failed(self, token, error_text)

    def _cached_suggestions(self, prefix: str) -> list[TagSuggestion]:
        return autocomplete_feature.cached_suggestions(self, prefix)

    def _apply_autocomplete(self, prefix: str, suggestions: list[TagSuggestion]) -> None:
        autocomplete_feature.apply_autocomplete(self, prefix, suggestions)

    def _insert_completion(self, completion: str) -> None:
        autocomplete_feature.insert_completion(self, completion)

    def _apply_completion_to_token(self, value: str, snapshot: str, start: int, end: int) -> None:
        autocomplete_feature.apply_completion_to_token(self, value, snapshot, start, end)

    def _format_post_metadata(self, post: Post) -> str:
        return format_post_metadata(post)

    @staticmethod
    def _format_post_tile(post: Post) -> str:
        return format_post_tile(post)

    def _current_post(self) -> Post | None:
        if self.left_tabs.currentWidget() is self.favorites_list:
            item = self.favorites_list.currentItem()
        elif self.left_tabs.currentWidget() is self.friends_tab:
            item = self.friend_posts_list.currentItem()
        else:
            item = self.results_list.currentItem()
        if item is None:
            return None
        post = item.data(Qt.ItemDataRole.UserRole)
        return post if isinstance(post, Post) else None

    def _active_posts_list(self) -> QListWidget:
        return navigation_feature.active_posts_list(self)

    def _move_selection(self, delta: int) -> None:
        navigation_feature.move_selection(self, delta)

    def _extend_selection(self, delta: int) -> None:
        navigation_feature.extend_selection(self, delta)

    def _toggle_current_favorite(self) -> None:
        favorites_feature.toggle_current_favorite(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        super().keyPressEvent(event)

    def open_selected_post(self) -> None:
        downloads_feature.open_selected_post(self)

    def _open_multiple_posts(self, posts: list[Post]) -> None:
        downloads_feature.open_multiple_posts(self, posts)

    def copy_selected_link(self) -> None:
        downloads_feature.copy_selected_link(self)

    def download_selected_post(self) -> None:
        downloads_feature.download_selected_post(self)

    def _download_multiple_posts(self, posts: list[Post]) -> None:
        downloads_feature.download_multiple_posts(self, posts)

    def _download_post_to_directory(self, post: Post, target_directory: str) -> Path:
        return downloads_feature.download_post_to_directory(self, post, target_directory)

    @staticmethod
    def _download_url_needs_hydration(url: str) -> bool:
        return download_url_needs_hydration(url)

    def _resolve_download_post(self, post: Post) -> Post:
        return downloads_feature.resolve_download_post(self, post)

    def _pool_for_workload(self, workload: str) -> QThreadPool:
        return self._worker_pools.get(workload, self._worker_pools["general"])

    def _start_worker(self, worker: FunctionWorker, workload: str = "general") -> None:
        downloads_feature.start_worker(self, worker, workload=workload)

    def _download_finished(self, token: int, result: object) -> None:
        downloads_feature.download_finished(self, token, result)

    def _download_many_finished(self, token: int, result: object) -> None:
        downloads_feature.download_many_finished(self, token, result)

    def open_settings(self, initial: bool = False) -> None:
        settings_feature.open_settings(self, initial)

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
        if self._shutdown_in_progress:
            super().closeEvent(event)
            return

        self._shutdown_in_progress = True
        self.store.save(self.settings)
        self.autocomplete_timer.stop()
        self.playback_timer.stop()
        self.background_sync_timer.stop()
        self.pending_remote_sync_timer.stop()
        self.video_player.stop()
        sync_client = self._make_sync_client(self.settings)
        if sync_client is not None:
            sync_client._destroy_session()

        # Cancel all active workers to interrupt execution loops and sleeps.
        for worker in list(self._active_workers):
            try:
                worker.cancel()
            except Exception:
                pass

        # Let in-flight work finish before clearing queued jobs.
        for pool_name, pool in self._worker_pools.items():
            if pool_name == "general":
                continue
            try:
                pool.waitForDone(2000)
                pool.clear()
            except Exception:
                pass

        super().closeEvent(event)

        if self._active_workers:
            # Some worker functions can block on network calls; force process exit so
            # closing the UI always returns control to the launching terminal.
            QTimer.singleShot(1500, lambda: os._exit(0))

    @property
    def current_posts(self) -> list[Post]:
        return self.state.current_posts

    @current_posts.setter
    def current_posts(self, posts: list[Post]) -> None:
        self.state.current_posts = posts

    @property
    def favorite_posts(self) -> list[Post]:
        return self.state.favorite_posts

    @favorite_posts.setter
    def favorite_posts(self, posts: list[Post]) -> None:
        self.state.favorite_posts = posts

    @property
    def friend_posts(self) -> list[Post]:
        return self.state.friend_posts

    @friend_posts.setter
    def friend_posts(self, posts: list[Post]) -> None:
        self.state.friend_posts = posts

    @property
    def favorite_ids(self) -> set[int]:
        return self.state.favorite_ids

    @favorite_ids.setter
    def favorite_ids(self, value: set[int]) -> None:
        self.state.favorite_ids = value

    @property
    def current_page(self) -> int:
        return self.state.current_page

    @current_page.setter
    def current_page(self, page: int) -> None:
        self.state.current_page = page

    @property
    def current_query(self) -> str:
        return self.state.current_query

    @current_query.setter
    def current_query(self, query: str) -> None:
        self.state.current_query = query

    def _on_search_completed(self, posts: list[Post]) -> None:
        self.results_list.clear()
        for post in posts:
            item = QListWidgetItem(self._format_post_tile(post))
            item.setData(Qt.ItemDataRole.UserRole, post)
            self.results_list.addItem(item)

        search_feature.update_related_tags(self, posts)
        self._update_action_state()

        if posts:
            self._prefetch_images(posts)

        if posts:
            if self.left_tabs.currentWidget() is self.results_list:
                self.results_list.setCurrentRow(0)
            self._set_status(f"Loaded {len(posts)} posts.")
        else:
            self.preview_label.setText("No posts matched the search query.")
            self.meta_view.setPlainText("No results.")
            self._set_status("Search completed with no results.")

    def _on_favorites_updated(self, posts: list[Post]) -> None:
        previous_current_id: int | None = None
        previous_current_item = self.favorites_list.currentItem()
        if previous_current_item is not None:
            previous_post = previous_current_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(previous_post, Post):
                previous_current_id = previous_post.id

        self._refresh_collection_filter()

        self.favorites_list.clear()
        for post in posts:
            item = QListWidgetItem(self._format_post_tile(post))
            item.setData(Qt.ItemDataRole.UserRole, post)
            self.favorites_list.addItem(item)

        if posts:
            self._prefetch_images(posts)

        should_restore_selection = (
            self.left_tabs.currentWidget() is self.favorites_list
            or previous_current_id is not None
        )

        if should_restore_selection and self.favorites_list.count() > 0:
            target_row = 0
            if previous_current_id is not None:
                for index, post in enumerate(posts):
                    if post.id == previous_current_id:
                        target_row = index
                        break

            self.favorites_list.setCurrentRow(target_row)
            selected_item = self.favorites_list.item(target_row)
            if selected_item is not None:
                selected_item.setSelected(True)
                if self.left_tabs.currentWidget() is self.favorites_list:
                    self._handle_selection_change(selected_item, None)

        if self._sync_enabled():
            pending_add = len(self._pending_remote_add_ids)
            pending_remove = len(self._pending_remote_remove_ids)
            if self._favorites_sync_fallback_used:
                if self._degraded_mode_active():
                    self._set_status(
                        "Favorites sync temporarily degraded due to rate limiting; "
                        f"showing local cache ({len(posts)} posts)."
                    )
                else:
                    self._set_status(
                        f"Favorites sync returned empty data; showing local cache ({len(posts)} posts)."
                    )
            else:
                self._rate_limit.note_success()
                if pending_add or pending_remove:
                    self._set_right_status(
                        f"Favorites loaded ({len(posts)} posts). Pending sync: {pending_add} add, {pending_remove} remove."
                    )
                    from r34_client.ui.favorites.pending import process_pending_remote_mutations
                    process_pending_remote_mutations(self)
                else:
                    self._set_right_status(f"Favorites synced ({len(posts)} posts).")
        else:
            self._set_right_status(f"Local favorites loaded ({len(posts)} posts).")
        self._update_action_state()

    def _on_friend_favorites_updated(self, posts: list[Post]) -> None:
        self.friend_posts_list.clear()
        for post in posts:
            item = QListWidgetItem(self._format_post_tile(post))
            item.setData(Qt.ItemDataRole.UserRole, post)
            self.friend_posts_list.addItem(item)

        self._update_friend_page_label()

        if posts:
            self._prefetch_images(posts)
        if posts:
            if self.left_tabs.currentWidget() is self.friends_tab:
                self.friend_posts_list.setCurrentRow(0)
        self._set_status(f"Loaded {len(posts)} favorites")

    def _on_page_changed(self, page: int) -> None:
        self.page_label.setText(f"Page {page + 1}")

    def _on_query_changed(self, query: str) -> None:
        self.search_input.setText(query)
