from __future__ import annotations

import unittest
from r34_client.ui.client_state import AppState


class ClientStateTests(unittest.TestCase):
    def test_default_app_state(self) -> None:
        state = AppState()
        self.assertEqual(state.current_page, 0)
        self.assertEqual(state.current_query, "")
        self.assertEqual(state.search_history, [])
        self.assertEqual(state.favorite_ids, set())
        self.assertFalse(state.favorites_sync_fallback_used)
        self.assertEqual(state.pending_remote_add_ids, set())

    def test_app_state_modification(self) -> None:
        state = AppState()
        state.current_page = 5
        state.search_history.append("pokemon")
        self.assertEqual(state.current_page, 5)
        self.assertEqual(state.search_history, ["pokemon"])
