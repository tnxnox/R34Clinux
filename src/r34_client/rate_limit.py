from __future__ import annotations

from dataclasses import dataclass


def is_rate_limited_error_message(message: str) -> bool:
    lowered = (message or "").lower()
    return "429" in lowered or "rate limit" in lowered or "too many requests" in lowered


@dataclass
class DegradedModeController:
    base_backoff_seconds: int = 15
    max_backoff_seconds: int = 180
    streak: int = 0
    blocked_until_monotonic: float = 0.0

    def mark_rate_limited(self, now_monotonic: float) -> int:
        self.streak += 1
        backoff = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** max(0, self.streak - 1)))
        self.blocked_until_monotonic = now_monotonic + backoff
        return int(backoff)

    def note_success(self) -> None:
        self.streak = 0
        self.blocked_until_monotonic = 0.0

    def is_active(self, now_monotonic: float) -> bool:
        return now_monotonic < self.blocked_until_monotonic

    def remaining_seconds(self, now_monotonic: float) -> int:
        if not self.is_active(now_monotonic):
            return 0
        return int(max(0.0, self.blocked_until_monotonic - now_monotonic))
