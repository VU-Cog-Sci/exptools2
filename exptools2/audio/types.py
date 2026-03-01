from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AudioConfig:
    sample_rate: int = 48000
    channels: int = 2
    dtype: str = "float32"
    latency_class: int = 1
    device: str | int | None = None
    blocksize: int | None = None


@dataclass(slots=True)
class AudioStartResult:
    scheduled_ns: int | None
    started_ns: int
    backend: str


@dataclass(slots=True)
class AudioStatus:
    backend: str
    started: bool = False
    scheduled_ns: int | None = None
    started_ns: int | None = None
    underruns: int = 0
    drift_ns: int = 0
    device_info: dict[str, Any] = field(default_factory=dict)
