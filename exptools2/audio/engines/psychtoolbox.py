from __future__ import annotations

import time
from dataclasses import asdict

import numpy as np

from exptools2.audio.types import AudioConfig, AudioStartResult, AudioStatus

try:
    import psychtoolbox as ptb
    import psychtoolbox.audio as ptb_audio
except Exception:  # pragma: no cover
    ptb = None
    ptb_audio = None


def psychtoolbox_available() -> bool:
    return ptb_audio is not None


class PsychtoolboxAudioDevice:
    """Thin adapter with PsychPortAudio-like semantics."""

    def __init__(self) -> None:
        self.cfg = AudioConfig()
        self._stream = None
        self._status = AudioStatus(backend="psychtoolbox")

    def open(self, cfg: AudioConfig) -> None:
        if ptb_audio is None:
            raise RuntimeError("psychtoolbox is not installed")
        self.cfg = cfg

        # Python psychtoolbox exposes audio.Stream in recent versions.
        self._stream = ptb_audio.Stream(
            freq=cfg.sample_rate,
            channels=cfg.channels,
            latency_class=cfg.latency_class,
            device_id=cfg.device,
        )

    def fill_buffer(self, samples: np.ndarray) -> None:
        if self._stream is None:
            raise RuntimeError("open must be called first")
        arr = np.asarray(samples, dtype=self.cfg.dtype)
        self._stream.fill_buffer(arr.T)

    def start(self, when_ns: int | None = None, repetitions: int = 1) -> AudioStartResult:
        if self._stream is None:
            raise RuntimeError("open must be called first")

        scheduled_ns = when_ns
        if when_ns is not None:
            wait_ns = when_ns - time.monotonic_ns()
            if wait_ns > 0:
                time.sleep(wait_ns / 1_000_000_000)

        # Start immediately after optional monotonic wait.
        self._stream.start(repetitions=repetitions, when=0, wait_for_start=0)
        started_ns = time.monotonic_ns()

        self._status.started = True
        self._status.scheduled_ns = scheduled_ns
        self._status.started_ns = started_ns
        if scheduled_ns is not None:
            self._status.drift_ns = started_ns - scheduled_ns

        return AudioStartResult(
            scheduled_ns=scheduled_ns,
            started_ns=started_ns,
            backend=self._status.backend,
        )

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
        self._status.started = False

    def get_status(self) -> AudioStatus:
        return AudioStatus(**asdict(self._status))

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._status.started = False
