from __future__ import annotations

import time
from collections import deque
from typing import Any

from exptools2.core.types import DisplayConfig, DrawBatch, FlipResult, InputEvent


class HeadlessDisplayBackend:
    """No-window backend useful for tests and offline contract checks."""

    def __init__(self) -> None:
        self.config: DisplayConfig | None = None
        self.frame_index = 0
        self._events: deque[InputEvent] = deque()
        self._lut: Any = None
        self.last_batch: DrawBatch | None = None

    def initialize(self, config: DisplayConfig) -> None:
        self.config = config
        self.frame_index = 0

    def draw(self, batch: DrawBatch) -> None:
        self.last_batch = batch

    def flip(self, target_ns: int | None = None) -> FlipResult:
        if target_ns is not None:
            delay = target_ns - time.monotonic_ns()
            if delay > 0:
                time.sleep(delay / 1_000_000_000)
        ts = time.monotonic_ns()
        out = FlipResult(
            timestamp_ns=ts,
            target_ns=target_ns,
            frame_index=self.frame_index,
            late_ns=max(0, ts - target_ns) if target_ns is not None else 0,
            dropped_frames=0,
        )
        self.frame_index += 1
        return out

    def set_gamma_lut(self, lut: Any) -> None:
        self._lut = lut

    def poll_input(self) -> list[InputEvent]:
        out = list(self._events)
        self._events.clear()
        return out

    def push_input(self, key: str) -> None:
        self._events.append(InputEvent(key=key, timestamp_ns=time.monotonic_ns()))

    def shutdown(self) -> None:
        return
