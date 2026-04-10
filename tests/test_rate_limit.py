from __future__ import annotations

import unittest

from r34_client.rate_limit import DegradedModeController, is_rate_limited_error_message


class RateLimitTests(unittest.TestCase):
    def test_message_detection(self) -> None:
        self.assertTrue(is_rate_limited_error_message("HTTP 429"))
        self.assertTrue(is_rate_limited_error_message("Too many requests"))
        self.assertFalse(is_rate_limited_error_message("network timeout"))

    def test_backoff_increases_with_streak(self) -> None:
        ctrl = DegradedModeController(base_backoff_seconds=10, max_backoff_seconds=60)
        self.assertEqual(ctrl.mark_rate_limited(100.0), 10)
        self.assertEqual(ctrl.mark_rate_limited(110.0), 20)
        self.assertEqual(ctrl.mark_rate_limited(130.0), 40)
        self.assertEqual(ctrl.mark_rate_limited(170.0), 60)

    def test_remaining_and_success_reset(self) -> None:
        ctrl = DegradedModeController(base_backoff_seconds=10, max_backoff_seconds=60)
        ctrl.mark_rate_limited(100.0)
        self.assertTrue(ctrl.is_active(105.0))
        self.assertEqual(ctrl.remaining_seconds(105.0), 5)
        ctrl.note_success()
        self.assertFalse(ctrl.is_active(105.0))
        self.assertEqual(ctrl.remaining_seconds(105.0), 0)


if __name__ == "__main__":
    unittest.main()
