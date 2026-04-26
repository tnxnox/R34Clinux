from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.models import Post, TagSuggestion
    from ...core.worker import FunctionWorker
    from .helpers.image_fit import FitMode

@dataclass
class AppState:
    current_posts: list[Post] = field(default_factory=list)
    favorite_posts: list[Post] = field(default_factory=list)
    favorite_ids: set[int] = field(default_factory=set)
    current_page: int = 0
    current_query: str = ""
    
    search_history: list[str] = field(default_factory=list)
    saved_searches: list[str] = field(default_factory=list)
    pinned_filters: list[str] = field(default_factory=list)
    
    search_token: int = 0
    preview_token: int = 0
    favorites_token: int = 0
    autocomplete_token: int = 0
    mutation_token: int = 0
    download_token: int = 0
    hydrate_token: int = 0
    
    last_autocomplete_prefix: str = ""
    autocomplete_cache: dict[str, list[TagSuggestion]] = field(default_factory=dict)
    autocomplete_token_start: int = 0
    autocomplete_token_end: int = 0
    autocomplete_query_snapshot: str = ""
    
    active_workers: set[FunctionWorker] = field(default_factory=set)
    metadata_hydrated_ids: set[int] = field(default_factory=set)
    
    favorites_sync_fallback_used: bool = False
    last_favorite_sync_failed: bool = False
    last_favorite_sync_error: str = ""
    last_favorite_sync_debug: str = ""
    
    pending_remote_add_ids: set[int] = field(default_factory=set)
    pending_remote_remove_ids: set[int] = field(default_factory=set)
    pending_sync_worker_active: bool = False
    
    # Optional fields for holding pending meta
    pending_remote_add_meta: dict[int, dict] = field(default_factory=dict)
    pending_remote_remove_meta: dict[int, dict] = field(default_factory=dict)
    pending_endpoint_streaks: dict[str, int] = field(default_factory=lambda: {"add": 0, "remove": 0})
