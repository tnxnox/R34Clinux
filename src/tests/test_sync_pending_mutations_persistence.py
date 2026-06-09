from __future__ import annotations

import json
import logging
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from r34_client.sync.pending_mutations import (
    ensure_pending_state_loaded,
    save_pending_state,
    queue_pending_add,
    queue_pending_remove,
    clear_pending_add,
    clear_pending_remove,
)


class _MockWindow:
    """Minimal mock of MainWindow for pending_mutations tests."""

    def __init__(self, sync_debug_log_path: Path | None = None) -> None:
        self._pending_state_lock = threading.Lock()
        self._pending_endpoint_streaks: dict[str, int] = {}
        self._pending_state_loaded = False
        self._pending_remote_add_ids: set[int] = set()
        self._pending_remote_remove_ids: set[int] = set()
        self._pending_remote_add_meta: dict[int, dict] = {}
        self._pending_remote_remove_meta: dict[int, dict] = {}
        self._sync_debug_log_path = sync_debug_log_path or Path("/tmp/__mock_debug_log.txt")


class SavePendingStateTests(unittest.TestCase):
    """Tests for save_pending_state."""

    def setUp(self) -> None:
        self.logger_patcher = patch("r34_client.sync.pending_mutations.logger")
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self) -> None:
        self.logger_patcher.stop()

    def _make_window(self, td: str) -> _MockWindow:
        log_path = Path(td) / "debug" / "sync_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return _MockWindow(sync_debug_log_path=log_path)

    def test_saves_adds_and_removes_as_json(self) -> None:
        """save_pending_state writes add and remove entries as JSON."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            window._pending_state_loaded = True
            window._pending_remote_add_ids = {1, 3}
            window._pending_remote_add_meta[1] = {
                "attempts": 2,
                "first_queued_at": 1000.0,
                "next_attempt_at": 2000.0,
                "last_error": "timeout",
            }
            window._pending_remote_add_meta[3] = {
                "attempts": 0,
                "first_queued_at": 3000.0,
                "next_attempt_at": 0.0,
                "last_error": "",
            }
            window._pending_remote_remove_ids = {5}
            window._pending_remote_remove_meta[5] = {
                "attempts": 1,
                "first_queued_at": 4000.0,
                "next_attempt_at": 5000.0,
                "last_error": "not found",
            }

            save_pending_state(window)

            state_path = Path(td) / "debug" / "pending-mutations.json"
            self.assertTrue(state_path.exists())
            data = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertIn("add", data)
            self.assertIn("remove", data)
            # Check add entries sorted by id
            self.assertEqual(len(data["add"]), 2)
            self.assertEqual(data["add"][0]["id"], 1)
            self.assertEqual(data["add"][0]["attempts"], 2)
            self.assertEqual(data["add"][0]["first_queued_at"], 1000.0)
            self.assertEqual(data["add"][0]["last_error"], "timeout")
            self.assertEqual(data["add"][1]["id"], 3)
            self.assertEqual(data["remove"][0]["id"], 5)
            self.assertEqual(data["remove"][0]["last_error"], "not found")

    def test_writes_empty_arrays_when_no_pending(self) -> None:
        """save_pending_state writes empty add/remove arrays when nothing is pending."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            window._pending_state_loaded = True

            save_pending_state(window)

            state_path = Path(td) / "debug" / "pending-mutations.json"
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data, {"add": [], "remove": []})


class EnsurePendingStateLoadedTests(unittest.TestCase):
    """Tests for ensure_pending_state_loaded."""

    def setUp(self) -> None:
        self.logger_patcher = patch("r34_client.sync.pending_mutations.logger")
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self) -> None:
        self.logger_patcher.stop()

    def _make_window(self, td: str) -> _MockWindow:
        log_path = Path(td) / "debug" / "sync_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return _MockWindow(sync_debug_log_path=log_path)

    def test_loads_adds_and_removes_from_json(self) -> None:
        """ensure_pending_state_loaded populates sets and metas from JSON file."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            state_path = Path(td) / "debug" / "pending-mutations.json"
            state_path.write_text(
                json.dumps(
                    {
                        "add": [
                            {"id": 10, "attempts": 1, "first_queued_at": 100.0, "next_attempt_at": 200.0, "last_error": "err1"},
                            {"id": 20, "attempts": 3, "first_queued_at": 300.0, "next_attempt_at": 0.0, "last_error": ""},
                        ],
                        "remove": [
                            {"id": 30, "attempts": 0, "first_queued_at": 500.0, "next_attempt_at": 600.0, "last_error": "removed"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(window._pending_state_loaded)
            ensure_pending_state_loaded(window)

            self.assertTrue(window._pending_state_loaded)
            self.assertIn(10, window._pending_remote_add_ids)
            self.assertIn(20, window._pending_remote_add_ids)
            self.assertIn(30, window._pending_remote_remove_ids)
            self.assertEqual(window._pending_remote_add_meta[10]["attempts"], 1)
            self.assertEqual(window._pending_remote_add_meta[10]["first_queued_at"], 100.0)
            self.assertEqual(window._pending_remote_add_meta[10]["last_error"], "err1")
            self.assertEqual(window._pending_remote_add_meta[20]["attempts"], 3)

    def test_skips_load_if_already_loaded(self) -> None:
        """ensure_pending_state_loaded returns early when already loaded."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            window._pending_state_loaded = True

            # Even with a corrupt/missing file, no error because it's already loaded
            try:
                ensure_pending_state_loaded(window)
            except Exception as e:
                self.fail(f"ensure_pending_state_loaded raised unexpectedly: {e}")

    def test_handles_missing_file_gracefully(self) -> None:
        """ensure_pending_state_loaded does nothing when file doesn't exist."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            # No JSON file written
            ensure_pending_state_loaded(window)
            self.assertTrue(window._pending_state_loaded)
            self.assertEqual(len(window._pending_remote_add_ids), 0)
            self.assertEqual(len(window._pending_remote_remove_ids), 0)

    def test_corrupted_json_logs_warning_and_returns(self) -> None:
        """ensure_pending_state_loaded logs a warning when JSON is corrupted."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            state_path = Path(td) / "debug" / "pending-mutations.json"
            state_path.write_text("this is not valid json {{{", encoding="utf-8")

            # Should not raise
            ensure_pending_state_loaded(window)
            self.assertTrue(window._pending_state_loaded)

    def test_skips_entries_with_invalid_id(self) -> None:
        """ensure_pending_state_loaded skips entries where 'id' is not a valid int."""
        with tempfile.TemporaryDirectory() as td:
            window = self._make_window(td)
            state_path = Path(td) / "debug" / "pending-mutations.json"
            state_path.write_text(
                json.dumps(
                    {
                        "add": [
                            {"id": "not_a_number", "attempts": 0},
                            {"id": 99, "attempts": 1},
                        ],
                        "remove": [
                            {"id": None, "attempts": 0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            ensure_pending_state_loaded(window)
            # Only id=99 should be loaded
            self.assertNotIn("not_a_number", window._pending_remote_add_ids)
            self.assertIn(99, window._pending_remote_add_ids)
            self.assertEqual(len(window._pending_remote_remove_ids), 0)


class QueuePendingAddTests(unittest.TestCase):
    """Tests for queue_pending_add."""

    def setUp(self) -> None:
        self.logger_patcher = patch("r34_client.sync.pending_mutations.logger")
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self) -> None:
        self.logger_patcher.stop()

    def test_adds_to_pending_remote_add_ids(self) -> None:
        """queue_pending_add adds the post id to _pending_remote_add_ids."""
        window = _MockWindow()
        window._pending_state_loaded = True
        queue_pending_add(window, 42, "user request", persist=False)
        self.assertIn(42, window._pending_remote_add_ids)

    def test_removes_from_remove_set(self) -> None:
        """queue_pending_add discards the id from _pending_remote_remove_ids."""
        window = _MockWindow()
        window._pending_state_loaded = True
        window._pending_remote_remove_ids.add(7)
        window._pending_remote_remove_meta[7] = {"attempts": 0}
        queue_pending_add(window, 7, "re-add", persist=False)
        self.assertIn(7, window._pending_remote_add_ids)
        self.assertNotIn(7, window._pending_remote_remove_ids)

    def test_creates_meta_if_missing(self) -> None:
        """queue_pending_add creates default meta when none exists."""
        window = _MockWindow()
        window._pending_state_loaded = True
        queue_pending_add(window, 99, "new item", persist=False)
        self.assertIn(99, window._pending_remote_add_meta)
        self.assertEqual(window._pending_remote_add_meta[99]["attempts"], 0)
        self.assertEqual(window._pending_remote_add_meta[99]["last_error"], "new item")


class QueuePendingRemoveTests(unittest.TestCase):
    """Tests for queue_pending_remove."""

    def setUp(self) -> None:
        self.logger_patcher = patch("r34_client.sync.pending_mutations.logger")
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self) -> None:
        self.logger_patcher.stop()

    def test_adds_to_pending_remote_remove_ids(self) -> None:
        """queue_pending_remove adds the post id to _pending_remote_remove_ids."""
        window = _MockWindow()
        window._pending_state_loaded = True
        queue_pending_remove(window, 17, "user request", persist=False)
        self.assertIn(17, window._pending_remote_remove_ids)

    def test_removes_from_add_set(self) -> None:
        """queue_pending_remove discards the id from _pending_remote_add_ids."""
        window = _MockWindow()
        window._pending_state_loaded = True
        window._pending_remote_add_ids.add(5)
        window._pending_remote_add_meta[5] = {"attempts": 2}
        queue_pending_remove(window, 5, "removing", persist=False)
        self.assertIn(5, window._pending_remote_remove_ids)
        self.assertNotIn(5, window._pending_remote_add_ids)

    def test_creates_meta_if_missing(self) -> None:
        """queue_pending_remove creates default meta when none exists."""
        window = _MockWindow()
        window._pending_state_loaded = True
        queue_pending_remove(window, 33, "remove reason", persist=False)
        self.assertIn(33, window._pending_remote_remove_meta)
        self.assertEqual(window._pending_remote_remove_meta[33]["attempts"], 0)
        self.assertEqual(window._pending_remote_remove_meta[33]["last_error"], "remove reason")


class ClearPendingAddTests(unittest.TestCase):
    """Tests for clear_pending_add."""

    def setUp(self) -> None:
        self.logger_patcher = patch("r34_client.sync.pending_mutations.logger")
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self) -> None:
        self.logger_patcher.stop()

    def test_removes_from_pending_remote_add_ids(self) -> None:
        """clear_pending_add removes the post id from _pending_remote_add_ids."""
        window = _MockWindow()
        window._pending_state_loaded = True
        window._pending_remote_add_ids.add(42)
        window._pending_remote_add_meta[42] = {"attempts": 1}
        clear_pending_add(window, 42, persist=False)
        self.assertNotIn(42, window._pending_remote_add_ids)
        self.assertNotIn(42, window._pending_remote_add_meta)


class ClearPendingRemoveTests(unittest.TestCase):
    """Tests for clear_pending_remove."""

    def setUp(self) -> None:
        self.logger_patcher = patch("r34_client.sync.pending_mutations.logger")
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self) -> None:
        self.logger_patcher.stop()

    def test_removes_from_pending_remote_remove_ids(self) -> None:
        """clear_pending_remove removes the post id from _pending_remote_remove_ids."""
        window = _MockWindow()
        window._pending_state_loaded = True
        window._pending_remote_remove_ids.add(99)
        window._pending_remote_remove_meta[99] = {"attempts": 3}
        clear_pending_remove(window, 99, persist=False)
        self.assertNotIn(99, window._pending_remote_remove_ids)
        self.assertNotIn(99, window._pending_remote_remove_meta)
