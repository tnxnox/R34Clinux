from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiagnosticsSnapshot:
    sync_enabled: bool
    degraded_mode_active: bool
    degraded_mode_remaining_seconds: int
    fit_mode: str
    active_workers: int
    current_query: str
    current_page: int
    current_results_count: int
    current_favorites_count: int
    selected_post_id: int | None
    last_sync_failed: bool
    last_sync_error: str
    sync_debug_log_path: str


def format_diagnostics_report(snapshot: DiagnosticsSnapshot) -> str:
    lines = [
        "R34 Linux Client Diagnostics",
        "",
        f"Sync enabled: {snapshot.sync_enabled}",
        f"Degraded mode active: {snapshot.degraded_mode_active}",
        f"Degraded mode remaining (s): {snapshot.degraded_mode_remaining_seconds}",
        f"Image fit mode: {snapshot.fit_mode}",
        f"Active workers: {snapshot.active_workers}",
        f"Current query: {snapshot.current_query or 'n/a'}",
        f"Current page: {snapshot.current_page + 1}",
        f"Search result count: {snapshot.current_results_count}",
        f"Favorites count: {snapshot.current_favorites_count}",
        f"Selected post id: {snapshot.selected_post_id if snapshot.selected_post_id is not None else 'n/a'}",
        f"Last sync failed: {snapshot.last_sync_failed}",
        f"Last sync error: {snapshot.last_sync_error or 'n/a'}",
        f"Sync debug log: {snapshot.sync_debug_log_path}",
    ]
    return "\n".join(lines)
