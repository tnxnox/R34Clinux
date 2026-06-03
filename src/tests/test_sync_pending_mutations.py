from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from r34_client.sync.pending_mutations import (
    extract_retry_after_seconds,
    compute_backoff_seconds,
    note_endpoint_success,
)


class ExtractRetryAfterTests(unittest.TestCase):
    def test_extracts_retry_after_value(self) -> None:
        self.assertEqual(extract_retry_after_seconds("retry after 30 seconds"), 30)

    def test_extracts_retry_after_with_various_spelling(self) -> None:
        self.assertEqual(extract_retry_after_seconds("Retry-After: 60"), 60)
        self.assertEqual(extract_retry_after_seconds("retry_after=120"), 120)
        self.assertEqual(extract_retry_after_seconds("RETRY_AFTER 15"), 15)

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(extract_retry_after_seconds("no retry info"))

    def test_empty_message_returns_none(self) -> None:
        self.assertIsNone(extract_retry_after_seconds(""))

    def test_negative_sign_ignored_regex_matches_absolute(self) -> None:
        result = extract_retry_after_seconds("retry after -5")
        self.assertEqual(result, 5)


class _MockWindow:
    def __init__(self) -> None:
        self._pending_state_lock = threading.Lock()
        self._pending_endpoint_streaks: dict[str, int] = {}
        self._pending_state_loaded = True
        self._pending_remote_add_ids: set[int] = set()
        self._pending_remote_remove_ids: set[int] = set()
        self._pending_remote_add_meta: dict[int, dict] = {}
        self._pending_remote_remove_meta: dict[int, dict] = {}


class ComputeBackoffTests(unittest.TestCase):
    @patch("r34_client.sync.pending_mutations.ensure_pending_state_loaded")
    def test_backoff_increases_with_streak(self, mock_ensure) -> None:
        window = _MockWindow()
        with patch("random.uniform", return_value=0.5):
            first = compute_backoff_seconds(window, "sync", 1, "error")
            second = compute_backoff_seconds(window, "sync", 2, "error")
            third = compute_backoff_seconds(window, "sync", 3, "error")
        self.assertLess(first, second)
        self.assertLess(second, third)

    @patch("r34_client.sync.pending_mutations.ensure_pending_state_loaded")
    def test_retry_after_takes_precedence(self, mock_ensure) -> None:
        window = _MockWindow()
        with patch("random.uniform", return_value=1.0):
            backoff = compute_backoff_seconds(window, "sync", 1, "retry after 100")
        self.assertGreaterEqual(backoff, 100)

    @patch("r34_client.sync.pending_mutations.ensure_pending_state_loaded")
    def test_backoff_capped_at_120_seconds_base(self, mock_ensure) -> None:
        window = _MockWindow()
        with patch("random.uniform", return_value=1.0):
            backoff = compute_backoff_seconds(window, "sync", 99, "error")
        self.assertGreater(backoff, 0)
        self.assertLess(backoff, 200)

    @patch("r34_client.sync.pending_mutations.ensure_pending_state_loaded")
    def test_backoff_first_attempt(self, mock_ensure) -> None:
        window = _MockWindow()
        with patch("random.uniform", return_value=0.3):
            backoff = compute_backoff_seconds(window, "sync", 1, "error")
        expected_base = min(120.0, 1.25 * (2 ** 1))
        self.assertAlmostEqual(backoff, expected_base + 0.3)


class NoteEndpointSuccessTests(unittest.TestCase):
    @patch("r34_client.sync.pending_mutations.ensure_pending_state_loaded")
    def test_resets_streak_to_zero(self, mock_ensure) -> None:
        window = _MockWindow()
        window._pending_endpoint_streaks["sync"] = 5
        note_endpoint_success(window, "sync")
        self.assertEqual(window._pending_endpoint_streaks["sync"], 0)

    @patch("r34_client.sync.pending_mutations.ensure_pending_state_loaded")
    def test_handles_missing_endpoint(self, mock_ensure) -> None:
        window = _MockWindow()
        note_endpoint_success(window, "sync")
        self.assertEqual(window._pending_endpoint_streaks["sync"], 0)
