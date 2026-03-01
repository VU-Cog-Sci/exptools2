from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from exptools2.core.types import RunEndStatus

from .client import EyeLinkClient, EyeLinkTrackerConfig, stem_to_remote_edf
from .coregraphics_gl import EyeLinkGraphicsConfig, GLEyeLinkCoreGraphics


@dataclass(slots=True)
class EyeLinkRecorderConfig:
    address: str = "100.1.1.1"
    remote_edf: str | None = None
    calibrate_on_start: bool = True
    drift_correct_on_start: bool = False
    drift_check_pos_px: tuple[int, int] | None = None
    send_input_messages: bool = True
    send_flip_messages: bool = False
    flip_message_stride: int = 60
    tracker: EyeLinkTrackerConfig = field(default_factory=EyeLinkTrackerConfig)
    graphics: EyeLinkGraphicsConfig = field(default_factory=EyeLinkGraphicsConfig)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "EyeLinkRecorderConfig":
        def _vec4(value: Any, default: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            if not isinstance(value, (list, tuple)):
                return default
            vals = [float(x) for x in value]
            if len(vals) == 3:
                vals.append(1.0)
            if len(vals) != 4:
                return default
            return (vals[0], vals[1], vals[2], vals[3])

        tracker_cfg = EyeLinkTrackerConfig(
            sample_rate=payload.get("sample_rate"),
            options=dict(payload.get("options", {})),
            file_event_filter=str(
                payload.get(
                    "file_event_filter",
                    "LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT",
                )
            ),
            link_event_filter=str(
                payload.get(
                    "link_event_filter",
                    "LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON",
                )
            ),
            link_sample_data=str(
                payload.get(
                    "link_sample_data",
                    "LEFT,RIGHT,GAZE,GAZERES,AREA,STATUS,HTARGET",
                )
            ),
        )

        graphics = EyeLinkGraphicsConfig(
            background_color=_vec4(
                payload.get("background_color"),
                (0.0, 0.0, 0.0, 1.0),
            ),
            foreground_color=_vec4(
                payload.get("foreground_color"),
                (1.0, 1.0, 1.0, 1.0),
            ),
            target_radius_px=float(payload.get("target_radius_px", 14.0)),
            target_inner_radius_px=float(payload.get("target_inner_radius_px", 3.0)),
            target_stroke_px=float(payload.get("target_stroke_px", 2.0)),
        )

        drift_raw = payload.get("drift_check_pos_px")
        drift_pos = None
        if isinstance(drift_raw, (list, tuple)) and len(drift_raw) == 2:
            drift_pos = (int(drift_raw[0]), int(drift_raw[1]))

        return cls(
            address=str(payload.get("address", "100.1.1.1")),
            remote_edf=payload.get("remote_edf"),
            calibrate_on_start=bool(payload.get("calibrate_on_start", True)),
            drift_correct_on_start=bool(payload.get("drift_correct_on_start", False)),
            drift_check_pos_px=drift_pos,
            send_input_messages=bool(payload.get("send_input_messages", True)),
            send_flip_messages=bool(payload.get("send_flip_messages", False)),
            flip_message_stride=max(int(payload.get("flip_message_stride", 60)), 1),
            tracker=tracker_cfg,
            graphics=graphics,
        )


class EyeLinkRecorder:
    """Session recorder that manages tracker setup, markers, and EDF retrieval."""

    def __init__(
        self,
        backend: Any,
        config: EyeLinkRecorderConfig | None = None,
    ) -> None:
        self.backend = backend
        self.config = config or EyeLinkRecorderConfig()
        self.client = EyeLinkClient(address=self.config.address)
        self.graphics = None

        self._stem: str | None = None
        self._output_dir: Path | None = None
        self._local_edf: Path | None = None
        self._local_meta: Path | None = None
        self._remote_edf: str | None = None
        self._recording_started = False
        self._tracker_prepared = False
        self._run_started_ns: int | None = None
        self._run_ended_ns: int | None = None
        self._run_status: str | None = None

    def _framebuffer_size(self) -> tuple[int, int]:
        if hasattr(self.backend, "framebuffer_size"):
            w, h = self.backend.framebuffer_size()
            return max(int(w), 1), max(int(h), 1)
        cfg = getattr(self.backend, "config", None)
        if cfg is not None:
            return max(int(getattr(cfg, "width", 1)), 1), max(int(getattr(cfg, "height", 1)), 1)
        return (1, 1)

    def start(self, stem: str, output_dir: Path) -> None:
        self._stem = str(stem)
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._local_edf = self._output_dir / f"{stem}_eyetrack.edf"
        self._local_meta = self._output_dir / f"{stem}_eyetrack.json"
        self._remote_edf = self.config.remote_edf or stem_to_remote_edf(stem)

        self.client.connect()
        self.client.open_data_file(self._remote_edf)

        w, h = self._framebuffer_size()
        self.client.configure_tracker(
            screen_width_px=w,
            screen_height_px=h,
            tracker_config=self.config.tracker,
        )

        self.graphics = GLEyeLinkCoreGraphics(self.backend, config=self.config.graphics)
        self.client.install_core_graphics(self.graphics)

        if self.config.calibrate_on_start:
            self.client.calibrate()

        if self.config.drift_correct_on_start:
            if self.config.drift_check_pos_px is None:
                x, y = (w // 2, h // 2)
            else:
                x, y = self.config.drift_check_pos_px
            self.client.drift_correct(int(x), int(y), draw=True, allow_setup=True)

        self._tracker_prepared = True

    def on_run_started(self, run_start_ns: int) -> None:
        if not self._tracker_prepared:
            return
        self._run_started_ns = int(run_start_ns)
        if not self._recording_started:
            self.client.start_recording()
            self._recording_started = True
        self.client.send_message(f"RUN_STARTED {int(run_start_ns)}")
        self.client.send_message("SYNCTIME")

    def on_phase_started(
        self,
        trial_nr: int,
        phase_index: int,
        phase_name: str,
        phase_start_ns: int,
        phase_end_ns: int,
    ) -> None:
        if not self._recording_started:
            return
        self.client.send_message(
            f"PHASE_STARTED trial={int(trial_nr)} phase={int(phase_index)} "
            f"name={phase_name} start_ns={int(phase_start_ns)} end_ns={int(phase_end_ns)}"
        )

    def on_flip(self, frame_index: int, timestamp_ns: int, trial_nr: int, phase_index: int) -> None:
        if not self._recording_started or not self.config.send_flip_messages:
            return
        if frame_index % self.config.flip_message_stride != 0:
            return
        self.client.send_message(
            f"FLIP frame={int(frame_index)} ts_ns={int(timestamp_ns)} "
            f"trial={int(trial_nr)} phase={int(phase_index)}"
        )

    def on_input(
        self,
        key: str,
        timestamp_ns: int,
        event_type: str,
        trial_nr: int,
        phase_index: int,
    ) -> None:
        if not self._recording_started or not self.config.send_input_messages:
            return
        self.client.send_message(
            f"INPUT key={str(key)} ts_ns={int(timestamp_ns)} event={event_type} "
            f"trial={int(trial_nr)} phase={int(phase_index)}"
        )

    def on_run_ended(self, run_end_ns: int, status: RunEndStatus, error: str | None) -> None:
        self._run_ended_ns = int(run_end_ns)
        self._run_status = status.value
        if self._recording_started:
            self.client.send_message(f"RUN_ENDED status={status.value} ts_ns={int(run_end_ns)}")
            if error:
                self.client.send_message(f"RUN_ERROR {error}")

    def stop(self) -> None:
        try:
            if self._recording_started:
                self.client.stop_recording()
                self._recording_started = False
            self.client.set_offline_mode()
            self.client.close_data_file()
            if self._local_edf is not None:
                self.client.receive_data_file(self._local_edf)
        finally:
            self.client.close()
            self._write_metadata()

    def _write_metadata(self) -> None:
        if self._local_meta is None:
            return
        payload = {
            "address": self.config.address,
            "remote_edf": self._remote_edf,
            "local_edf": str(self._local_edf) if self._local_edf is not None else None,
            "run_started_ns": self._run_started_ns,
            "run_ended_ns": self._run_ended_ns,
            "run_status": self._run_status,
            "tracker_config": asdict(self.config.tracker),
            "graphics_config": asdict(self.config.graphics),
            "calibrate_on_start": self.config.calibrate_on_start,
            "drift_correct_on_start": self.config.drift_correct_on_start,
            "drift_check_pos_px": self.config.drift_check_pos_px,
            "written_at_ns": time.monotonic_ns(),
        }
        self._local_meta.write_text(json.dumps(payload, indent=2), encoding="utf8")

    def artifact_records(self) -> list[tuple[str, Path]]:
        artifacts: list[tuple[str, Path]] = []
        if self._local_edf is not None and self._local_edf.exists():
            artifacts.append(("eyetracker_edf", self._local_edf))
        if self._local_meta is not None and self._local_meta.exists():
            artifacts.append(("eyetracker_metadata", self._local_meta))
        return artifacts
