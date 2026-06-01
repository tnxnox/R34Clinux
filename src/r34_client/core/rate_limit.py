from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    capacity: float
    refill_rate_per_second: float
    tokens: float = 0.0
    last_refill_monotonic: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.capacity = max(1.0, float(self.capacity))
        self.refill_rate_per_second = max(0.0001, float(self.refill_rate_per_second))
        if self.tokens <= 0.0:
            self.tokens = self.capacity

    def _refill(self, now_monotonic: float) -> None:
        now = float(now_monotonic)
        if self.last_refill_monotonic <= 0.0:
            self.last_refill_monotonic = now
            return
        elapsed = max(0.0, now - self.last_refill_monotonic)
        if elapsed <= 0.0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate_per_second)
        self.last_refill_monotonic = now

    def available_tokens(self, now_monotonic: float) -> float:
        with self._lock:
            self._refill(now_monotonic)
            return max(0.0, self.tokens)

    def consume(self, amount: float, now_monotonic: float) -> bool:
        needed = max(0.0, float(amount))
        with self._lock:
            self._refill(now_monotonic)
            if self.tokens + 1e-9 < needed:
                return False
            self.tokens = max(0.0, self.tokens - needed)
            return True

    def seconds_until_available(self, amount: float, now_monotonic: float) -> float:
        needed = max(0.0, float(amount))
        with self._lock:
            self._refill(now_monotonic)
            available = max(0.0, self.tokens)
        if available >= needed:
            return 0.0
        deficit = needed - available
        return deficit / self.refill_rate_per_second


def is_rate_limited_error_message(message: str) -> bool:
    lowered = (message or "").lower()
    return "429" in lowered or "rate limit" in lowered or "too many requests" in lowered


@dataclass
class DegradedModeController:
    base_backoff_seconds: int = 15
    max_backoff_seconds: int = 180
    streak: int = 0
    blocked_until_monotonic: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def mark_rate_limited(self, now_monotonic: float) -> int:
        with self._lock:
            self.streak += 1
            backoff = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** max(0, self.streak - 1)))
            self.blocked_until_monotonic = now_monotonic + backoff
            return int(backoff)

    def note_success(self) -> None:
        with self._lock:
            self.streak = 0
            self.blocked_until_monotonic = 0.0

    def is_active(self, now_monotonic: float) -> bool:
        with self._lock:
            return now_monotonic < self.blocked_until_monotonic

    def remaining_seconds(self, now_monotonic: float) -> int:
        if not self.is_active(now_monotonic):
            return 0
        return int(max(0.0, self.blocked_until_monotonic - now_monotonic))
