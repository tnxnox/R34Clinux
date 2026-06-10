from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call
from threading import Lock

from r34_client.core.models import Post
from r34_client.ui.search.controller import (
    search,
    next_page,
    previous_page,
    apply_search_query,
    run_search,
    search_finished,
    refresh_favorites,
    refresh_local_favorites,
    favorites_loaded,
    favorites_failed,
    sync_remote,
)


class SearchControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = MagicMock()
        self.window.search_input.text.return_value = "  hello tags  "
        self.window.current_query = ""
        self.window.current_page = 0
        self.window._search_token = 42
        self.window._favorites_token = 100
        self.window.settings.has_credentials = True
        self.window.settings.page_size = 20
        self.window._pending_state_lock = Lock()
        self.window._pending_remote_add_ids = set()
        self.window._pending_remote_remove_ids = set()
        self.window._pending_sync_worker_active = False
        self.window._sync_debug_log_path = "/tmp/sync.log"
        self.window._selected_collection_name.return_value = None

    @patch("r34_client.ui.search.controller.apply_search_query")
    def test_search_reads_input_and_applies(self, mock_apply: MagicMock) -> None:
        search(self.window)
        mock_apply.assert_called_once_with(self.window, "hello tags")

    def test_next_page(self) -> None:
        # If query is empty, next_page does nothing
        self.window.current_query = ""
        self.window.current_page = 1
        with patch("r34_client.ui.search.controller.run_search") as mock_run:
            next_page(self.window)
            self.assertEqual(self.window.current_page, 1)
            mock_run.assert_not_called()

        # If query is not empty, increments page and runs search
        self.window.current_query = "tags"
        self.window.current_page = 1
        with patch("r34_client.ui.search.controller.run_search") as mock_run:
            next_page(self.window)
            self.assertEqual(self.window.current_page, 2)
            mock_run.assert_called_once_with(self.window)

    def test_previous_page(self) -> None:
        # If page <= 0, previous_page does nothing
        self.window.current_query = "tags"
        self.window.current_page = 0
        with patch("r34_client.ui.search.controller.run_search") as mock_run:
            previous_page(self.window)
            self.assertEqual(self.window.current_page, 0)
            mock_run.assert_not_called()

        # If query is empty, does nothing
        self.window.current_query = ""
        self.window.current_page = 2
        with patch("r34_client.ui.search.controller.run_search") as mock_run:
            previous_page(self.window)
            self.assertEqual(self.window.current_page, 2)
            mock_run.assert_not_called()

        # If page > 0 and query is set, decrements page and runs search
        self.window.current_query = "tags"
        self.window.current_page = 2
        with patch("r34_client.ui.search.controller.run_search") as mock_run:
            previous_page(self.window)
            self.assertEqual(self.window.current_page, 1)
            mock_run.assert_called_once_with(self.window)

    @patch("r34_client.ui.search.controller.history_feature.record_search_history")
    @patch("r34_client.ui.search.controller.run_search")
    def test_apply_search_query(self, mock_run: MagicMock, mock_record: MagicMock) -> None:
        # Empty query does nothing
        apply_search_query(self.window, "   ")
        mock_run.assert_not_called()

        # Valid query sets values and runs search
        self.window.current_page = 5
        apply_search_query(self.window, "  hello  ", record_history=True)
        self.assertEqual(self.window.current_query, "hello")
        self.assertEqual(self.window.current_page, 0)
        self.window.search_input.setText.assert_called_once_with("hello")
        self.window._update_action_state.assert_called_once()
        mock_record.assert_called_once_with(self.window, "hello")
        mock_run.assert_called_once_with(self.window)

    def test_run_search_no_credentials(self) -> None:
        self.window.settings.has_credentials = False
        run_search(self.window)
        self.window.open_settings.assert_called_once_with(initial=True)
        self.window._start_worker.assert_not_called()

    @patch("r34_client.ui.search.controller.FunctionWorker")
    def test_run_search_with_credentials(self, mock_worker_class: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker
        self.window.current_query = "mytags"
        self.window.current_page = 2

        run_search(self.window)

        self.assertEqual(self.window.current_posts, [])
        self.window._set_status.assert_called_once_with("Searching...")
        self.assertEqual(self.window._search_token, 43)
        
        # Verify worker is created with search_posts and parameters
        mock_worker_class.assert_called_once_with(
            self.window.client.search_posts, "mytags", 2, 20
        )
        self.window._start_worker.assert_called_once_with(mock_worker, workload="search")

    def test_search_finished(self) -> None:
        posts = [Post.from_payload({"id": 123})]
        
        # Token mismatch - ignored
        search_finished(self.window, token=999, result=posts)
        self.assertNotEqual(self.window.current_posts, posts)

        # Token matches - sets posts
        search_finished(self.window, token=42, result=posts)
        self.assertEqual(self.window.current_posts, posts)

    @patch("r34_client.ui.search.controller.FunctionWorker")
    def test_refresh_favorites_local_only(self, mock_worker_class: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker
        self.window._sync_enabled.return_value = True

        # Local refresh does not sync remote
        refresh_local_favorites(self.window)
        self.assertEqual(self.window._favorites_token, 101)
        mock_worker_class.assert_called_once()
        # Verify it lists from local favorites
        self.assertEqual(mock_worker_class.call_args[0][0], self.window.local_favorites.list_favorites)

    @patch("r34_client.ui.search.controller.FunctionWorker")
    def test_refresh_favorites_remote_sync(self, mock_worker_class: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker
        self.window._sync_enabled.return_value = True

        # Remote sync triggers sync_remote
        refresh_favorites(self.window)
        self.assertEqual(self.window._favorites_token, 101)
        self.window._set_right_status.assert_called_once_with("Syncing favorites via FlareSolverr...")
        # Verify worker target is sync_remote
        from r34_client.ui.search.controller import sync_remote
        self.assertEqual(mock_worker_class.call_args[0][0], sync_remote)

    @patch("r34_client.ui.search.controller.sync_remote_favorites")
    @patch("r34_client.ui.search.controller.save_pending_state")
    def test_sync_remote_executes(self, mock_save: MagicMock, mock_sync: MagicMock) -> None:
        self.window._degraded_mode_active.return_value = False
        self.window._pending_remote_add_ids = {101, 102}
        self.window._pending_remote_remove_ids = {201}
        
        # mock sync_remote_favorites behavior: confirms 101, so 101 is removed from pending adds
        def side_effect(*args, **kwargs):
            kwargs["pending_remote_add_ids"].difference_update({101})
            return ([Post.from_payload({"id": 101})], False)
        mock_sync.side_effect = side_effect

        posts, fallback = sync_remote(self.window)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 101)
        self.assertFalse(fallback)
        mock_save.assert_called_once_with(self.window)
        # 101 was confirmed, so it's removed from live pending adds. 102 remains.
        self.assertEqual(self.window._pending_remote_add_ids, {102})

    @patch("r34_client.ui.search.controller.sync_remote_favorites")
    def test_sync_remote_degraded_mode(self, mock_sync: MagicMock) -> None:
        self.window._degraded_mode_active.return_value = True
        self.window._degraded_mode_remaining.return_value = 15
        self.window.local_favorites.list_favorites.return_value = [Post.from_payload({"id": 500})]

        posts, fallback = sync_remote(self.window)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 500)
        self.window._log_sync_debug.assert_called_once()
        mock_sync.assert_not_called()

    def test_favorites_loaded(self) -> None:
        posts = [Post.from_payload({"id": 900})]

        # Token mismatch
        favorites_loaded(self.window, token=999, result=posts)
        self.assertNotEqual(self.window.favorite_posts, posts)

        # Token matches, list result
        self.window.settings.flaresolverr_enabled = True
        favorites_loaded(self.window, token=100, result=posts)
        self.assertEqual(self.window.favorite_posts, posts)
        self.assertFalse(self.window._favorites_sync_fallback_used)
        self.window._set_right_status.assert_called_with("FlareSolverr running.")

        # Token matches, tuple result with fallback flag
        favorites_loaded(self.window, token=100, result=(posts, True))
        self.assertEqual(self.window.favorite_posts, posts)
        self.assertTrue(self.window._favorites_sync_fallback_used)

    def test_favorites_failed(self) -> None:
        # Token mismatch
        favorites_failed(self.window, token=999, error_text="Some error")
        self.window._log_sync_debug.assert_not_called()

        # Token matches, sync enabled
        self.window._sync_enabled.return_value = True
        favorites_failed(self.window, token=100, error_text="Connection refused\nLine 2")
        self.window._log_sync_debug.assert_called_once_with("Favorites refresh failure", "Connection refused\nLine 2")
        self.window._set_right_status.assert_called_with("Favorites sync failed: Connection refused (see /tmp/sync.log)")

        # Token matches, sync disabled (local only)
        self.window._sync_enabled.return_value = False
        favorites_failed(self.window, token=100, error_text="DB locked\nLine 2")
        self.window._set_right_status.assert_called_with("Local favorites refresh failed: DB locked")
