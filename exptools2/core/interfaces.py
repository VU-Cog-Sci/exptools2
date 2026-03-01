from __future__ import annotations

from typing import Any
from typing import Protocol

from .types import DisplayConfig, DrawBatch, FlipResult, InputEvent


class DisplayBackend(Protocol):
    def initialize(self, config: DisplayConfig) -> None:
        ...

    def draw(self, batch: DrawBatch) -> None:
        ...

    def flip(self, target_ns: int | None = None) -> FlipResult:
        ...

    def set_gamma_lut(self, lut: Any) -> None:
        ...

    def poll_input(self) -> list[InputEvent]:
        ...

    def shutdown(self) -> None:
        ...


class Stimulus(Protocol):
    def update(self, params: dict) -> None:
        ...

    def enqueue(self, batch: DrawBatch) -> None:
        ...


class VideoPlayer(Protocol):
    def open(self, path: str, hwaccel: str = "auto") -> None:
        ...

    def schedule(self, start_ns: int) -> None:
        ...

    def enqueue(self, batch: DrawBatch, now_ns: int) -> None:
        ...

    def status(self):
        ...

    def close(self) -> None:
        ...
