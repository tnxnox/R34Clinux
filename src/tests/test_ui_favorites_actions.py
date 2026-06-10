from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call
from threading import Lock
import time

from r34_client.core.models import Post
from r34_client.api.flaresolverr import FlareSolverrError
from r34_client.ui.favorites.bulk import (
    add_multiple_favorites,
    add_multiple_favorites_impl,
    favorite_bulk_add_finished,
    remove_multiple_favorites,
    remove_multiple_favorites_impl,
    favorite_bulk_mutation_finished,
)
from r34_client.ui.favorites.pending import (
    restore_pending_remote_mutations,
    process_pending_remote_mutations,
    process_pending_remote_mutations_impl,
    pending_remote_mutations_finished,
    pending_remote_mutations_failed,
)


class FavoritesActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = MagicMock()
        self.window.local_favorites = MagicMock()
        self.window.favorite_ids = set()
        self.window._mutation_token = 10
        self.window._pending_state_lock = Lock()
        self.window._pending_remote_add_ids = set()
        self.window._pending_remote_add_meta = {}
        self.window._pending_remote_remove_ids = set()
        self.window._pending_remote_remove_meta = {}
        self.window._pending_sync_worker_active = False
        self.window._pending_sync_started_at = 0.0
        self.window._pending_sync_last_restart_at = 0.0
        
        # Remote mutation bucket mock
        self.window._remote_mutation_bucket = MagicMock()
        self.window._remote_mutation_bucket.consume.return_value = True
        self.window._remote_mutation_bucket.available_tokens.return_value = 10.0
        self.window._remote_mutation_bucket.seconds_until_available.return_value = 0.0

        self.window._degraded_mode_active.return_value = False
        self.window._degraded_mode_remaining.return_value = 0

    @patch("r34_client.ui.favorites.bulk.FunctionWorker")
    def test_add_multiple_favorites_empty(self, mock_worker: MagicMock) -> None:
        add_multiple_favorites(self.window, [])
        mock_worker.assert_not_called()

    @patch("r34_client.ui.favorites.bulk.FunctionWorker")
    def test_add_multiple_favorites_sync_enabled(self, mock_worker_class: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker
        self.window._sync_enabled.return_value = True
        
        posts = [Post.from_payload({"id": 1001}), Post.from_payload({"id": 1002})]
        
        add_multiple_favorites(self.window, posts)
        
        self.assertEqual(self.window._mutation_token, 11)
        self.window._set_status.assert_called_once_with("Adding 2 favorites...")
        mock_worker_class.assert_called_once()
        self.window._start_worker.assert_called_once_with(mock_worker, workload="mutation")

    @patch("r34_client.ui.favorites.bulk.queue_pending_add")
    @patch("r34_client.ui.favorites.bulk.clear_pending_add")
    @patch("r34_client.ui.favorites.bulk.save_pending_state")
    def test_add_multiple_favorites_impl_sync_disabled(
        self, mock_save: MagicMock, mock_clear: MagicMock, mock_queue: MagicMock
    ) -> None:
        posts = [Post.from_payload({"id": 1001})]
        
        res = add_multiple_favorites_impl(
            self.window.local_favorites, posts, sync_enabled=False, window_ref=self.window
        )
        
        self.window.local_favorites.add_favorite.assert_called_once_with(posts[0])
        mock_clear.assert_called_once_with(self.window, 1001, persist=False)
        mock_queue.assert_not_called()
        mock_save.assert_called_once_with(self.window)
        self.assertEqual(res, {"added_ids": [1001], "deferred_sync_ids": []})

    @patch("r34_client.ui.favorites.bulk.queue_pending_add")
    @patch("r34_client.ui.favorites.bulk.save_pending_state")
    def test_add_multiple_favorites_impl_sync_enabled(
        self, mock_save: MagicMock, mock_queue: MagicMock
    ) -> None:
        posts = [Post.from_payload({"id": 1001})]
        
        res = add_multiple_favorites_impl(
            self.window.local_favorites, posts, sync_enabled=True, window_ref=self.window
        )
        
        self.window.local_favorites.add_favorite.assert_called_once_with(posts[0])
        mock_queue.assert_called_once_with(self.window, 1001, "queued optimistic bulk add", persist=False)
        mock_save.assert_called_once_with(self.window)
        self.assertEqual(res, {"added_ids": [1001], "deferred_sync_ids": [1001]})

    @patch("r34_client.ui.favorites.bulk.process_pending_remote_mutations")
    def test_favorite_bulk_add_finished(self, mock_process: MagicMock) -> None:
        self.window._mutation_token = 10
        self.window._sync_enabled.return_value = True

        result = {"added_ids": [1001, 1002], "deferred_sync_ids": [1001, 1002]}
        favorite_bulk_add_finished(self.window, token=10, result=result)

        self.assertEqual(self.window.favorite_ids, {1001, 1002})
        self.window._set_status.assert_called_with(
            "Added 2 favorites locally; queued 2 for background remote sync."
        )
        self.window._refresh_local_favorites.assert_called_once()
        mock_process.assert_called_once_with(self.window)

    @patch("r34_client.ui.favorites.bulk.FunctionWorker")
    def test_remove_multiple_favorites_sync_enabled(self, mock_worker_class: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker
        self.window._sync_enabled.return_value = True
        
        posts = [Post.from_payload({"id": 2001})]
        
        remove_multiple_favorites(self.window, posts)
        
        self.assertEqual(self.window._mutation_token, 11)
        self.window._set_status.assert_called_once()
        mock_worker_class.assert_called_once()

    @patch("r34_client.ui.favorites.bulk.queue_pending_remove")
    @patch("r34_client.ui.favorites.bulk.save_pending_state")
    def test_remove_multiple_favorites_impl(self, mock_save: MagicMock, mock_queue: MagicMock) -> None:
        posts = [Post.from_payload({"id": 2001})]
        self.window.local_favorites.remove_favorites.return_value = 1

        res = remove_multiple_favorites_impl(
            self.window.local_favorites, posts, sync_enabled=True, window_ref=self.window
        )

        self.window.local_favorites.remove_favorites.assert_called_once_with([2001])
        mock_queue.assert_called_once_with(self.window, 2001, "queued optimistic bulk remove", persist=False)
        mock_save.assert_called_once_with(self.window)
        self.assertEqual(res, {
            "requested_ids": [2001],
            "removed_count": 1,
            "deferred_sync_ids": [2001],
        })

    @patch("r34_client.ui.favorites.bulk.process_pending_remote_mutations")
    def test_favorite_bulk_mutation_finished(self, mock_process: MagicMock) -> None:
        self.window._mutation_token = 10
        self.window._sync_enabled.return_value = True
        self.window.favorite_ids = {2001, 2002}

        result = {
            "requested_ids": [2001],
            "removed_count": 1,
            "deferred_sync_ids": [2001],
        }
        favorite_bulk_mutation_finished(self.window, token=10, result=result)

        self.assertEqual(self.window.favorite_ids, {2002})
        self.window._set_status.assert_called_with(
            "Removed 1 favorites locally; queued 1 for background remote sync."
        )
        mock_process.assert_called_once_with(self.window)

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    def test_restore_pending(self, mock_ensure: MagicMock) -> None:
        restore_pending_remote_mutations(self.window)
        mock_ensure.assert_called_once_with(self.window)

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    @patch("r34_client.ui.favorites.pending.FunctionWorker")
    def test_process_pending_remote_mutations_no_work(
        self, mock_worker: MagicMock, mock_ensure: MagicMock
    ) -> None:
        self.window._sync_enabled.return_value = True
        self.window._pending_remote_add_ids = set()
        self.window._pending_remote_remove_ids = set()

        process_pending_remote_mutations(self.window)
        mock_worker.assert_not_called()

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    @patch("r34_client.ui.favorites.pending.FunctionWorker")
    def test_process_pending_remote_mutations_active_watchdog(
        self, mock_worker: MagicMock, mock_ensure: MagicMock
    ) -> None:
        self.window._sync_enabled.return_value = True
        self.window._pending_remote_add_ids = {3001}
        self.window._pending_sync_worker_active = True
        self.window._pending_sync_started_at = time.monotonic() - 10.0 # Active for 10s only

        process_pending_remote_mutations(self.window)
        mock_worker.assert_not_called()

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    @patch("r34_client.ui.favorites.pending.FunctionWorker")
    def test_process_pending_remote_mutations_watchdog_restart_throttle(
        self, mock_worker: MagicMock, mock_ensure: MagicMock
    ) -> None:
        self.window._sync_enabled.return_value = True
        self.window._pending_remote_add_ids = {3001}
        self.window._pending_sync_worker_active = True
        self.window._pending_sync_started_at = time.monotonic() - 200.0 # Exceeded watchdog
        self.window._pending_sync_last_restart_at = time.monotonic() - 20.0 # But restarted 20s ago (throttle)

        process_pending_remote_mutations(self.window)
        
        self.window._set_right_status.assert_called_once_with(
            "Pending sync worker is taking longer than expected; waiting for recovery window."
        )
        mock_worker.assert_not_called()

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    @patch("r34_client.ui.favorites.pending.FunctionWorker")
    def test_process_pending_remote_mutations_runs(
        self, mock_worker_class: MagicMock, mock_ensure: MagicMock
    ) -> None:
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker
        self.window._sync_enabled.return_value = True
        self.window._pending_remote_add_ids = {3001}

        process_pending_remote_mutations(self.window)

        self.assertTrue(self.window._pending_sync_worker_active)
        mock_worker_class.assert_called_once()
        self.window._start_worker.assert_called_once_with(mock_worker, workload="sync")

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    @patch("r34_client.ui.favorites.pending.compute_backoff_seconds")
    @patch("r34_client.ui.favorites.pending.save_pending_state")
    @patch("r34_client.ui.favorites.pending.note_endpoint_success")
    def test_process_pending_remote_mutations_impl_success(
        self, mock_note: MagicMock, mock_save: MagicMock, mock_backoff: MagicMock, mock_ensure: MagicMock
    ) -> None:
        self.window._pending_remote_remove_ids = {4001}
        self.window._pending_remote_add_ids = {5001}

        # Mock sync client
        sync_client = MagicMock()
        self.window._make_sync_client.return_value = sync_client

        res = process_pending_remote_mutations_impl(self.window)

        sync_client.remove_favorite.assert_called_once_with(4001)
        sync_client.add_favorite.assert_called_once_with(5001)

        self.assertEqual(self.window._pending_remote_remove_ids, set())
        self.assertEqual(self.window._pending_remote_add_ids, set())
        mock_save.assert_called_once_with(self.window)

        self.assertEqual(res["processed"], 2)
        self.assertEqual(res["tokens_spent"], 2)

    @patch("r34_client.ui.favorites.pending.ensure_pending_state_loaded")
    @patch("r34_client.ui.favorites.pending.compute_backoff_seconds")
    @patch("r34_client.ui.favorites.pending.save_pending_state")
    def test_process_pending_remote_mutations_impl_flaresolverr_error(
        self, mock_save: MagicMock, mock_backoff: MagicMock, mock_ensure: MagicMock
    ) -> None:
        self.window._pending_remote_add_ids = {5001}
        self.window._pending_remote_add_meta = {5001: {"attempts": 1}}

        sync_client = MagicMock()
        sync_client.add_favorite.side_effect = FlareSolverrError("HTTP 429 Rate Limited")
        self.window._make_sync_client.return_value = sync_client
        mock_backoff.return_value = 60.0

        res = process_pending_remote_mutations_impl(self.window)

        # Should not discard from pending add
        self.assertEqual(self.window._pending_remote_add_ids, {5001})
        # Should record backoff meta
        meta = self.window._pending_remote_add_meta[5001]
        self.assertEqual(meta["attempts"], 2)
        self.assertEqual(meta["last_error"], "HTTP 429 Rate Limited")
        self.assertGreater(meta["next_attempt_at"], time.time())
        self.window._mark_rate_limited_if_needed.assert_called_once_with("pending_remote_add", "HTTP 429 Rate Limited")

    def test_pending_remote_mutations_finished_complete(self) -> None:
        self.window._pending_remote_add_ids = set()
        self.window._pending_remote_remove_ids = set()
        self.window._pending_sync_worker_active = True

        pending_remote_mutations_finished(self.window, {})

        self.assertFalse(self.window._pending_sync_worker_active)
        self.window._set_right_status.assert_called_once_with("Pending sync complete.")

    def test_pending_remote_mutations_finished_remaining_tokens(self) -> None:
        self.window._pending_remote_add_ids = {7001}
        self.window._pending_remote_remove_ids = set()
        self.window._pending_sync_worker_active = True

        result = {
            "tokens_available": 0.0,
            "token_wait_seconds": 15,
            "token_exhausted": 1,
            "tokens_spent": 1,
            "processed": 0,
            "degraded_remaining": 0,
            "next_retry_remaining": 0,
        }

        pending_remote_mutations_finished(self.window, result)

        self.window._set_right_status.assert_called_once_with(
            "Pending sync: 1 add, 0 remove (waiting for tokens, retry in 15s)."
        )

    def test_pending_remote_mutations_failed(self) -> None:
        self.window._pending_sync_worker_active = True
        pending_remote_mutations_failed(self.window, "Network Timeout\nTraceback info")

        self.assertFalse(self.window._pending_sync_worker_active)
        self.window._set_right_status.assert_called_once_with("Pending remote sync failed: Network Timeout")
