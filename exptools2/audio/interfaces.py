from __future__ import annotations

from typing import Protocol

import numpy as np

from .types import AudioConfig, AudioStartResult, AudioStatus


class AudioDevice(Protocol):
    def open(self, cfg: AudioConfig) -> None:
        ...

    def fill_buffer(self, samples: np.ndarray) -> None:
        ...

    def start(self, when_ns: int | None = None, repetitions: int = 1) -> AudioStartResult:
        ...

    def stop(self) -> None:
        ...

    def get_status(self) -> AudioStatus:
        ...

    def close(self) -> None:
        ...
