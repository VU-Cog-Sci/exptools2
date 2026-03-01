"""Audio playback example with PTB-like interface and PortAudio fallback."""

from __future__ import annotations

import time

import numpy as np

from exptools2.audio import AudioConfig, create_audio_device


def make_tone(freq_hz: float, duration_s: float, sample_rate: int) -> np.ndarray:
    t = np.arange(0, duration_s, 1 / sample_rate, dtype=np.float32)
    tone = 0.1 * np.sin(2 * np.pi * freq_hz * t)
    return np.column_stack([tone, tone])


def main() -> None:
    cfg = AudioConfig(sample_rate=48000, channels=2, dtype="float32")
    device = create_audio_device(engine="auto")
    device.open(cfg)
    device.fill_buffer(make_tone(freq_hz=440.0, duration_s=1.0, sample_rate=cfg.sample_rate))

    scheduled = time.monotonic_ns() + 300_000_000
    result = device.start(when_ns=scheduled, repetitions=1)
    print("Audio start:", result)

    time.sleep(1.2)
    print("Audio status:", device.get_status())
    device.stop()
    device.close()


if __name__ == "__main__":
    main()
