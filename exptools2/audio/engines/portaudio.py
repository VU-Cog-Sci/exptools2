from __future__ import annotations

import time
from dataclasses import asdict

import numpy as np

from exptools2.audio.types import AudioConfig, AudioStartResult, AudioStatus

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None


class PortAudioDevice:
    def __init__(self) -> None:
        self.cfg = AudioConfig()
        self._samples: np.ndarray | None = None
        self._status = AudioStatus(backend="portaudio")

    def open(self, cfg: AudioConfig) -> None:
        if sd is None:
            raise RuntimeError("sounddevice is required for the PortAudio backend")
        self.cfg = cfg
        self._status.device_info = {
            "sample_rate": cfg.sample_rate,
            "channels": cfg.channels,
            "device": cfg.device,
        }

    def fill_buffer(self, samples: np.ndarray) -> None:
        arr = np.asarray(samples, dtype=self.cfg.dtype)
        if arr.ndim == 1 and self.cfg.channels > 1:
            arr = np.repeat(arr[:, None], repeats=self.cfg.channels, axis=1)
        self._samples = arr

    def start(self, when_ns: int | None = None, repetitions: int = 1) -> AudioStartResult:
        if self._samples is None:
            raise RuntimeError("fill_buffer must be called before start")
        if sd is None:
            raise RuntimeError("sounddevice is required for the PortAudio backend")

        scheduled_ns = when_ns
        if when_ns is not None:
            wait_ns = when_ns - time.monotonic_ns()
            if wait_ns > 0:
                time.sleep(wait_ns / 1_000_000_000)

        samples = self._samples
        if repetitions > 1:
            samples = np.tile(samples, reps=(repetitions, 1))

        sd.play(samples, samplerate=self.cfg.sample_rate, device=self.cfg.device, blocking=False)
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
        if sd is not None:
            sd.stop()
        self._status.started = False

    def get_status(self) -> AudioStatus:
        return AudioStatus(**asdict(self._status))

    def close(self) -> None:
        self.stop()
