from __future__ import annotations

import unittest

from r34_client.core.rate_limit import DegradedModeController, TokenBucket, is_rate_limited_error_message


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

    def test_token_bucket_consume_and_refill(self) -> None:
        bucket = TokenBucket(capacity=3.0, refill_rate_per_second=1.0)
        self.assertTrue(bucket.consume(1.0, now_monotonic=10.0))
        self.assertTrue(bucket.consume(1.0, now_monotonic=10.0))
        self.assertTrue(bucket.consume(1.0, now_monotonic=10.0))
        self.assertFalse(bucket.consume(1.0, now_monotonic=10.0))

        # After 2 seconds at 1 token/sec, 2 tokens should be available.
        self.assertTrue(bucket.consume(1.0, now_monotonic=12.0))
        self.assertTrue(bucket.consume(1.0, now_monotonic=12.0))
        self.assertFalse(bucket.consume(1.0, now_monotonic=12.0))

    def test_token_bucket_wait_time(self) -> None:
        bucket = TokenBucket(capacity=2.0, refill_rate_per_second=2.0)
        self.assertTrue(bucket.consume(2.0, now_monotonic=20.0))
        self.assertAlmostEqual(bucket.seconds_until_available(1.0, now_monotonic=20.0), 0.5, places=3)
        self.assertAlmostEqual(bucket.seconds_until_available(1.0, now_monotonic=20.5), 0.0, places=3)


if __name__ == "__main__":
    unittest.main()
