from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


def now_ns() -> int:
    """Clock helper to centralize monotonic timestamps."""
    import time

    return time.monotonic_ns()


class RunEndStatus(str, Enum):
    OK = "ok"
    ABORTED = "aborted"
    ERROR = "error"


class StatusKind(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    PHASE_STARTED = "PHASE_STARTED"
    EVENT = "EVENT"
    SYNC = "SYNC"
    RUN_ENDED = "RUN_ENDED"


@dataclass(slots=True)
class ScannerTriggerMode:
    mode: str = "none"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunRequest:
    bids_stem: str
    condition_row: dict[str, Any]
    seed: int
    t0_ns: int
    scanner_trigger_mode: ScannerTriggerMode = field(default_factory=ScannerTriggerMode)
    contract_version: str = "1.1"


@dataclass(slots=True)
class RunStatus:
    kind: StatusKind
    timestamp_ns: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactRecord:
    kind: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunArtifactManifest:
    contract_version: str
    bids_stem: str
    backend: str
    output_root: str
    artifacts: list[ArtifactRecord] = field(default_factory=list)


@dataclass(slots=True)
class DisplayConfig:
    width: int = 1440
    height: int = 900
    refresh_hz: float = 60.0
    fullscreen: bool = True
    hide_cursor: bool = True
    title: str = "exptools2"
    vsync: bool = True
    monitor_name: str = "default"
    monitor_index: int | None = None


@dataclass(slots=True)
class InputEvent:
    key: str
    timestamp_ns: int
    source: str = "keyboard"


@dataclass(slots=True)
class FlipResult:
    timestamp_ns: int
    target_ns: int | None
    frame_index: int
    late_ns: int = 0
    dropped_frames: int = 0


@dataclass(slots=True)
class DrawCommand:
    kind: str
    params: dict[str, Any]


@dataclass(slots=True)
class DrawBatch:
    commands: list[DrawCommand] = field(default_factory=list)

    def add(self, kind: str, **params: Any) -> None:
        self.commands.append(DrawCommand(kind=kind, params=params))

    def extend(self, cmds: list[DrawCommand]) -> None:
        self.commands.extend(cmds)


@dataclass(slots=True)
class Phase:
    name: str
    duration_s: float


@dataclass(slots=True)
class ArtifactPaths:
    events_tsv: Path
    events_json: Path
    log_h5: Path
    manifest_json: Path
