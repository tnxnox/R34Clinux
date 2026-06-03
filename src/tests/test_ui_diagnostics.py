from __future__ import annotations

import unittest

from r34_client.ui.dialogs.diagnostics import DiagnosticsSnapshot, format_diagnostics_report


class DiagnosticsTests(unittest.TestCase):
    def test_report_contains_core_fields(self) -> None:
        snap = DiagnosticsSnapshot(
            sync_enabled=True,
            degraded_mode_active=True,
            degraded_mode_remaining_seconds=12,
            fit_mode="smart",
            active_workers=2,
            current_query="tag_a",
            current_page=1,
            current_results_count=50,
            current_favorites_count=10,
            selected_post_id=123,
            last_sync_failed=True,
            last_sync_error="429",
            sync_debug_log_path="/tmp/sync-debug.log",
        )
        report = format_diagnostics_report(snap)

        self.assertIn("Sync enabled: True", report)
        self.assertIn("Degraded mode remaining (s): 12", report)
        self.assertIn("Image fit mode: smart", report)
        self.assertIn("Selected post id: 123", report)
