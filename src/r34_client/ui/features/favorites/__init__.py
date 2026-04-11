from __future__ import annotations

from .bulk import (
    add_multiple_favorites,
    add_multiple_favorites_impl,
    favorite_bulk_add_finished,
    favorite_bulk_mutation_finished,
    remove_multiple_favorites,
    remove_multiple_favorites_impl,
)
from .collections import (
    assign_selection_to_collection,
    assign_selection_to_new_collection,
    remove_selection_from_collection,
)
from .pending import (
    pending_remote_mutations_failed,
    pending_remote_mutations_finished,
    process_pending_remote_mutations,
    process_pending_remote_mutations_impl,
    restore_pending_remote_mutations,
)
from .single import (
    add_favorite,
    add_favorite_impl,
    favorite_mutation_finished,
    operation_failed,
    remove_favorite,
    remove_favorite_impl,
    toggle_current_favorite,
)

__all__ = [
    "restore_pending_remote_mutations",
    "process_pending_remote_mutations",
    "process_pending_remote_mutations_impl",
    "pending_remote_mutations_finished",
    "pending_remote_mutations_failed",
    "add_multiple_favorites",
    "add_multiple_favorites_impl",
    "favorite_bulk_add_finished",
    "remove_multiple_favorites",
    "remove_multiple_favorites_impl",
    "favorite_bulk_mutation_finished",
    "assign_selection_to_new_collection",
    "assign_selection_to_collection",
    "remove_selection_from_collection",
    "add_favorite",
    "remove_favorite",
    "add_favorite_impl",
    "remove_favorite_impl",
    "favorite_mutation_finished",
    "operation_failed",
    "toggle_current_favorite",
]
