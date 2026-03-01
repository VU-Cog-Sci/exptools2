from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class EyeLinkUnavailableError(RuntimeError):
    """Raised when pylink is unavailable at runtime."""


def _import_pylink():
    try:
        import pylink  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local SR install
        raise EyeLinkUnavailableError(
            "pylink is not available. Install SR Research pylink and ensure it is importable."
        ) from exc
    return pylink


def normalize_remote_edf_name(name: str) -> str:
    """Convert an arbitrary name to an EyeLink-safe remote EDF filename."""
    token = re.sub(r"[^A-Za-z0-9]", "", str(name)).upper()
    if not token:
        token = "EXPRUN01"
    token = token[:8]
    return f"{token}.EDF"


def stem_to_remote_edf(stem: str) -> str:
    return normalize_remote_edf_name(stem)


def _format_command_value(value: Any) -> str:
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (list, tuple)):
        return ",".join(str(x) for x in value)
    return str(value)


@dataclass(slots=True)
class EyeLinkTrackerConfig:
    sample_rate: int | None = None
    options: dict[str, Any] = field(default_factory=dict)
    file_event_filter: str = "LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT"
    link_event_filter: str = "LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON"
    link_sample_data: str = "LEFT,RIGHT,GAZE,GAZERES,AREA,STATUS,HTARGET"

    def as_commands(self) -> dict[str, Any]:
        commands = {
            "file_event_filter": self.file_event_filter,
            "link_event_filter": self.link_event_filter,
            "link_sample_data": self.link_sample_data,
        }
        if self.sample_rate is not None:
            commands["sample_rate"] = int(self.sample_rate)
        commands.update(self.options)
        return commands


class EyeLinkClient:
    """Small wrapper around pylink to keep tracker interactions explicit."""

    def __init__(self, address: str = "100.1.1.1") -> None:
        self.address = address
        self._pylink = None
        self.tracker = None
        self.remote_edf_name: str | None = None

    def connect(self) -> None:
        pylink = _import_pylink()
        self._pylink = pylink
        self.tracker = pylink.EyeLink(self.address)

    @property
    def is_connected(self) -> bool:
        return self.tracker is not None

    def open_data_file(self, remote_edf_name: str) -> None:
        if self.tracker is None:
            raise RuntimeError("EyeLink tracker is not connected")
        remote_edf_name = normalize_remote_edf_name(remote_edf_name)
        self.tracker.openDataFile(remote_edf_name)
        self.remote_edf_name = remote_edf_name

    def configure_tracker(
        self,
        screen_width_px: int,
        screen_height_px: int,
        tracker_config: EyeLinkTrackerConfig | None = None,
    ) -> None:
        if self.tracker is None:
            raise RuntimeError("EyeLink tracker is not connected")

        w = int(screen_width_px)
        h = int(screen_height_px)
        self.send_command(f"screen_pixel_coords = 0 0 {w - 1} {h - 1}")
        self.send_message(f"DISPLAY_COORDS 0 0 {w - 1} {h - 1}")

        cfg = tracker_config or EyeLinkTrackerConfig()
        for key, value in cfg.as_commands().items():
            if value is None:
                continue
            self.send_command(f"{key} = {_format_command_value(value)}")

    def install_core_graphics(self, core_graphics: Any) -> None:
        if self._pylink is None:
            raise RuntimeError("pylink is not loaded")
        self._pylink.openGraphicsEx(core_graphics)

    def calibrate(self) -> None:
        if self.tracker is None:
            raise RuntimeError("EyeLink tracker is not connected")
        self.tracker.doTrackerSetup()

    def drift_correct(
        self,
        x_px: int,
        y_px: int,
        draw: bool = True,
        allow_setup: bool = True,
    ) -> None:
        if self.tracker is None:
            raise RuntimeError("EyeLink tracker is not connected")
        self.tracker.doDriftCorrect(
            int(x_px),
            int(y_px),
            int(draw),
            int(allow_setup),
        )

    def start_recording(self) -> None:
        if self.tracker is None:
            raise RuntimeError("EyeLink tracker is not connected")
        if self._pylink is None:
            raise RuntimeError("pylink is not loaded")
        self.tracker.startRecording(1, 1, 1, 1)
        self._pylink.pumpDelay(100)

    def stop_recording(self) -> None:
        if self.tracker is None:
            return
        self.tracker.stopRecording()

    def send_message(self, message: str) -> None:
        if self.tracker is None:
            return
        self.tracker.sendMessage(str(message))

    def send_command(self, command: str) -> None:
        if self.tracker is None:
            return
        self.tracker.sendCommand(str(command))

    def set_offline_mode(self) -> None:
        if self.tracker is None:
            return
        self.tracker.setOfflineMode()

    def close_data_file(self) -> None:
        if self.tracker is None:
            return
        self.tracker.closeDataFile()

    def receive_data_file(self, local_edf_path: str | Path) -> Path:
        if self.tracker is None:
            raise RuntimeError("EyeLink tracker is not connected")
        if self.remote_edf_name is None:
            raise RuntimeError("Remote EDF name is unknown; call open_data_file first")
        local_path = Path(local_edf_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.tracker.receiveDataFile(self.remote_edf_name, str(local_path))
        return local_path

    def close(self) -> None:
        if self.tracker is None:
            return
        try:
            self.tracker.close()
        finally:
            self.tracker = None

