from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class TimeWindow:
    start_ns: int
    end_ns: int


class NonSlipScheduler:
    """Monotonic nanosecond scheduler using absolute deadlines."""

    def __init__(
        self,
        t0_ns: int | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._clock = clock
        self._t0_ns = t0_ns
        self._cursor_ns = t0_ns

    @property
    def t0_ns(self) -> int | None:
        return self._t0_ns

    def start(self, t0_ns: int | None = None) -> int:
        if t0_ns is None:
            t0_ns = self._clock()
        self._t0_ns = t0_ns
        self._cursor_ns = t0_ns
        return t0_ns

    def now_ns(self) -> int:
        return self._clock()

    def reserve(self, duration_s: float) -> TimeWindow:
        if duration_s < 0:
            raise ValueError("duration_s must be >= 0")
        if self._cursor_ns is None:
            self.start()
        assert self._cursor_ns is not None
        dur_ns = int(duration_s * 1_000_000_000)
        start_ns = self._cursor_ns
        end_ns = start_ns + dur_ns
        self._cursor_ns = end_ns
        return TimeWindow(start_ns=start_ns, end_ns=end_ns)

    def sleep_until(self, target_ns: int, busy_wait_threshold_ns: int = 2_000_000) -> None:
        while True:
            now = self._clock()
            remaining_ns = target_ns - now
            if remaining_ns <= 0:
                return
            if remaining_ns > busy_wait_threshold_ns:
                time.sleep((remaining_ns - busy_wait_threshold_ns) / 1_000_000_000)
            else:
                # Busy wait only for final narrow window to reduce overshoot.
                pass
