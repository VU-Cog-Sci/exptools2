from __future__ import annotations

import math
import random
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .contract import validate_run_request
from .interfaces import DisplayBackend
from .logger import RunLogger
from .runtime_priority import (
    RuntimePriorityConfig,
    RuntimePriorityResult,
    apply_runtime_priority,
)
from .scheduler import NonSlipScheduler
from .trial import Trial
from .types import DisplayConfig, DrawBatch, RunEndStatus, RunRequest, StatusKind


@dataclass(slots=True)
class SessionResult:
    run_start_ns: int
    run_end_ns: int
    status: RunEndStatus
    error: str | None = None


class Session:
    """Core run engine that is backend-agnostic and contract-aware."""

    def __init__(
        self,
        request: RunRequest,
        backend: DisplayBackend,
        logger: RunLogger,
        display_config: DisplayConfig | None = None,
        scheduler: NonSlipScheduler | None = None,
        recorders: list[Any] | None = None,
        prelude: dict[str, Any] | None = None,
        runtime_priority: RuntimePriorityConfig | None = None,
    ) -> None:
        validate_run_request(request)
        self.request = request
        self.backend = backend
        self.logger = logger
        self.display_config = display_config or DisplayConfig()
        self.scheduler = scheduler or NonSlipScheduler(t0_ns=request.t0_ns)
        self.recorders = list(recorders or [])
        self.prelude = dict(prelude or {})
        self.runtime_priority = runtime_priority or RuntimePriorityConfig()
        self.runtime_priority_result: RuntimePriorityResult | None = None
        self.trials: list[Trial] = []
        random.seed(request.seed)

    def add_trial(self, trial: Trial) -> None:
        self.trials.append(trial)

    def add_trials(self, trials: list[Trial]) -> None:
        self.trials.extend(trials)

    @staticmethod
    def _fmt_seconds(seconds: float) -> str:
        total = max(0.0, float(seconds))
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        secs = total % 60.0
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int(round((len(ordered) - 1) * max(0.0, min(1.0, p))))
        return float(ordered[idx])

    @staticmethod
    def _safe_mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return float(sum(values) / len(values))

    def _planned_phase_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for trial in self.trials:
            for phase_index, phase in enumerate(trial.phases):
                rows.append(
                    {
                        "trial_nr": int(trial.trial_nr),
                        "phase_index": int(phase_index),
                        "phase_name": str(phase.name),
                        "duration_s": float(phase.duration_s),
                    }
                )
        return rows

    def _build_pre_run_summary(
        self,
        planned_t0_ns: int,
        planned_phase_rows: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        planned_duration_s = float(
            sum(float(row.get("duration_s", 0.0)) for row in planned_phase_rows)
        )
        phase_counts: Counter[str] = Counter(
            str(row.get("phase_name", "unknown")) for row in planned_phase_rows
        )
        phase_durations: dict[str, float] = {}
        for row in planned_phase_rows:
            key = str(row.get("phase_name", "unknown"))
            phase_durations[key] = phase_durations.get(key, 0.0) + float(
                row.get("duration_s", 0.0)
            )

        monitor_desc = (
            f"index={self.display_config.monitor_index}"
            if self.display_config.monitor_index is not None
            else f"name={self.display_config.monitor_name}"
        )
        frame_period_s = 1.0 / max(self.display_config.refresh_hz, 1.0)
        est_frames = int(math.ceil(planned_duration_s / frame_period_s))

        instruction_cfg = self._prelude_section("instruction")
        fixation_cfg = self._prelude_section("fixation_wait")
        prelude_enabled = bool(self.prelude.get("enabled", False))
        prelude_text = "yes" if (instruction_cfg.get("text") or self.prelude.get("instruction_text")) else "no"
        prelude_image = "yes" if (instruction_cfg.get("image") or self.prelude.get("instruction_image")) else "no"
        fixation_wait_enabled = bool(
            fixation_cfg.get("enabled", self.prelude.get("show_fixation_wait", True))
        )

        lines: list[str] = []
        lines.append("=== exptools2 Run Plan ===")
        lines.append(f"Run ID: {self.request.bids_stem}")
        lines.append(f"Backend: {self.logger.backend}")
        lines.append(f"Seed: {self.request.seed}")
        lines.append(
            "Display: "
            f"{self.display_config.width}x{self.display_config.height} @ {self.display_config.refresh_hz:.3f} Hz, "
            f"fullscreen={self.display_config.fullscreen}, vsync={self.display_config.vsync}, "
            f"monitor({monitor_desc})"
        )
        lines.append(
            "Runtime priority request: "
            f"enabled={self.runtime_priority.enabled}, "
            f"linux_policy={self.runtime_priority.linux_policy}, "
            f"linux_priority={self.runtime_priority.linux_priority}, "
            f"macos_qos={self.runtime_priority.macos_qos}, "
            f"nice_fallback={self.runtime_priority.allow_nice_fallback}, "
            f"nice_value={self.runtime_priority.nice_value}"
        )
        lines.append(
            "Scanner trigger mode: "
            f"{self.request.scanner_trigger_mode.mode} "
            f"{self.request.scanner_trigger_mode.params}"
        )
        lines.append(
            "Prelude: "
            f"enabled={prelude_enabled}, instruction_text={prelude_text}, "
            f"instruction_image={prelude_image}, fixation_wait={fixation_wait_enabled}"
        )
        lines.append(
            f"Planned trials/phases: {len(self.trials)} trials, {len(planned_phase_rows)} phases"
        )
        lines.append(
            "Planned duration: "
            f"{self._fmt_seconds(planned_duration_s)} ({planned_duration_s:.3f} s)"
        )
        lines.append(
            "Frame target: "
            f"{frame_period_s * 1000.0:.3f} ms ({self.display_config.refresh_hz:.3f} Hz), "
            f"estimated flips={est_frames}"
        )
        lines.append(f"Requested t0_ns: {int(planned_t0_ns)}")
        lines.append("Phase breakdown:")
        for phase_name in sorted(phase_counts.keys()):
            lines.append(
                f"  - {phase_name}: n={phase_counts[phase_name]}, "
                f"total={phase_durations.get(phase_name, 0.0):.3f} s"
            )
        lines.append("Outputs:")
        lines.append(f"  - events: {self.logger.paths.events_tsv}")
        lines.append(f"  - events sidecar: {self.logger.paths.events_json}")
        lines.append(f"  - run log: {self.logger.paths.log_h5}")
        lines.append(f"  - report: {self.logger.report_path}")
        lines.append(f"  - manifest: {self.logger.paths.manifest_json}")
        text = "\n".join(lines)
        payload = {
            "n_trials": len(self.trials),
            "n_phases": len(planned_phase_rows),
            "planned_duration_s": planned_duration_s,
            "estimated_flips": est_frames,
            "refresh_hz": float(self.display_config.refresh_hz),
        }
        return text, payload

    def _build_post_run_summary(
        self,
        run_start_ns: int,
        run_end_ns: int,
        status: RunEndStatus,
        error: str | None,
        planned_phase_rows: list[dict[str, Any]],
        planned_t0_ns: int,
    ) -> tuple[str, dict[str, Any]]:
        run_duration_s = max(0.0, (int(run_end_ns) - int(run_start_ns)) / 1_000_000_000.0)
        planned_duration_s = float(
            sum(float(row.get("duration_s", 0.0)) for row in planned_phase_rows)
        )
        drift_ms = (run_duration_s - planned_duration_s) * 1000.0
        start_adjust_ms = (int(run_start_ns) - int(planned_t0_ns)) / 1_000_000.0

        event_types = Counter(str(row.get("event_type", "")) for row in self.logger.events)
        response_keys = Counter(
            str(row.get("response"))
            for row in self.logger.events
            if row.get("event_type") in {"response", "pulse", "abort"}
            and row.get("response") not in {None, ""}
        )

        flip_count = len(self.logger.flip_records)
        dropped_total = int(
            sum(int(row.get("dropped_frames", 0) or 0) for row in self.logger.flip_records)
        )
        late_ms: list[float] = [
            max(0.0, float(int(row.get("late_ns", 0) or 0)) / 1_000_000.0)
            for row in self.logger.flip_records
        ]
        frame_budget_ms = 1000.0 / max(self.display_config.refresh_hz, 1.0)
        on_time_count = sum(1 for value in late_ms if value <= frame_budget_ms * 0.5)

        interval_ms: list[float] = []
        jitter_ms: list[float] = []
        ts_values = [
            int(row.get("timestamp_ns"))
            for row in self.logger.flip_records
            if row.get("timestamp_ns") is not None
        ]
        for idx in range(1, len(ts_values)):
            delta_ms = (ts_values[idx] - ts_values[idx - 1]) / 1_000_000.0
            interval_ms.append(delta_ms)
            jitter_ms.append(delta_ms - frame_budget_ms)
        rms_jitter_ms = (
            math.sqrt(sum(v * v for v in jitter_ms) / len(jitter_ms)) if jitter_ms else 0.0
        )

        phase_lookup: dict[tuple[int, int], float] = {}
        for row in planned_phase_rows:
            key = (int(row["trial_nr"]), int(row["phase_index"]))
            phase_lookup[key] = float(row["duration_s"])
        phase_start_rows = [
            status_row
            for status_row in self.logger.statuses
            if status_row.kind == StatusKind.PHASE_STARTED
        ]
        phase_abs_error_ms: list[float] = []
        for idx, row in enumerate(phase_start_rows):
            start_ns = int(row.timestamp_ns)
            if idx + 1 < len(phase_start_rows):
                end_ns = int(phase_start_rows[idx + 1].timestamp_ns)
            else:
                if status != RunEndStatus.OK:
                    # On aborted/error runs, the last phase is intentionally truncated.
                    continue
                end_ns = int(run_end_ns)
            observed_s = (end_ns - start_ns) / 1_000_000_000.0
            trial_nr = row.payload.get("trial_nr")
            phase_index = row.payload.get("phase")
            if trial_nr is None or phase_index is None:
                continue
            planned_s = phase_lookup.get((int(trial_nr), int(phase_index)))
            if planned_s is None:
                continue
            phase_abs_error_ms.append(abs((observed_s - planned_s) * 1000.0))

        lines: list[str] = []
        lines.append("=== exptools2 Run Report ===")
        lines.append(f"Run ID: {self.request.bids_stem}")
        lines.append(
            f"Status: {status.value}" + (f" (error={error})" if error else "")
        )
        lines.append(
            "Run timing: "
            f"actual={self._fmt_seconds(run_duration_s)} ({run_duration_s:.3f} s), "
            f"planned={self._fmt_seconds(planned_duration_s)} ({planned_duration_s:.3f} s), "
            f"drift={drift_ms:+.2f} ms"
        )
        if self.runtime_priority_result is not None:
            lines.append(
                "Runtime priority: "
                f"attempted={self.runtime_priority_result.attempted}, "
                f"applied={self.runtime_priority_result.applied}, "
                f"strategy={self.runtime_priority_result.strategy}"
            )
            if self.runtime_priority_result.details:
                lines.append(
                    "Runtime priority details: "
                    + "; ".join(str(item) for item in self.runtime_priority_result.details)
                )
            if self.runtime_priority_result.errors:
                lines.append(
                    "Runtime priority errors: "
                    + "; ".join(str(item) for item in self.runtime_priority_result.errors)
                )
        lines.append(
            f"Run start adjustment: {start_adjust_ms:+.2f} ms (actual_start - requested_t0)"
        )
        lines.append(
            "Behavior: "
            f"responses={event_types.get('response', 0)}, pulses={event_types.get('pulse', 0)}, "
            f"aborts={event_types.get('abort', 0)}"
        )
        if response_keys:
            top_keys = ", ".join(
                f"{key}:{count}" for key, count in response_keys.most_common(10)
            )
            lines.append(f"Behavior key distribution: {top_keys}")
        else:
            lines.append("Behavior key distribution: (none)")
        lines.append(
            "Flip timing: "
            f"n={flip_count}, dropped={dropped_total}, "
            f"on_time(<=0.5 frame)={on_time_count}/{flip_count if flip_count else 1}"
        )
        lines.append(
            "Flip lateness (ms): "
            f"mean={self._safe_mean(late_ms):.3f}, "
            f"p95={self._percentile(late_ms, 0.95):.3f}, "
            f"max={max(late_ms) if late_ms else 0.0:.3f}"
        )
        late_median = self._percentile(late_ms, 0.5)
        late_centered_abs_p95 = self._percentile(
            [abs(value - late_median) for value in late_ms], 0.95
        )
        lines.append(
            "Flip lateness (phase-offset corrected, ms): "
            f"median_offset={late_median:.3f}, "
            f"|late-median|_p95={late_centered_abs_p95:.3f}"
        )
        lines.append(
            "Flip interval/jitter (ms): "
            f"interval_mean={self._safe_mean(interval_ms):.3f}, "
            f"jitter_rms={rms_jitter_ms:.3f}, "
            f"|jitter|_p95={self._percentile([abs(v) for v in jitter_ms], 0.95):.3f}"
        )
        if flip_count > 0 and late_median > (frame_budget_ms * 0.5):
            lines.append(
                "Timing note: absolute lateness includes a mostly constant vblank phase offset; "
                "use jitter and offset-corrected lateness to assess stability."
            )
        lines.append(
            "Phase timing error (abs ms): "
            f"mean={self._safe_mean(phase_abs_error_ms):.3f}, "
            f"p95={self._percentile(phase_abs_error_ms, 0.95):.3f}, "
            f"max={max(phase_abs_error_ms) if phase_abs_error_ms else 0.0:.3f}"
        )
        lines.append(
            "Streams: "
            f"stim_frames={len(self.logger.stim_trace)}, "
            f"video_records={len(self.logger.video_records)}, "
            f"audio_records={len(self.logger.audio_records)}"
        )
        lines.append(f"Report path: {self.logger.report_path}")
        text = "\n".join(lines)
        payload = {
            "status": status.value,
            "run_duration_s": run_duration_s,
            "planned_duration_s": planned_duration_s,
            "run_drift_ms": drift_ms,
            "responses": int(event_types.get("response", 0)),
            "pulses": int(event_types.get("pulse", 0)),
            "abort_events": int(event_types.get("abort", 0)),
            "flip_count": flip_count,
            "flip_late_mean_ms": self._safe_mean(late_ms),
            "flip_late_p95_ms": self._percentile(late_ms, 0.95),
            "flip_late_max_ms": max(late_ms) if late_ms else 0.0,
            "flip_late_median_ms": late_median,
            "flip_late_centered_abs_p95_ms": late_centered_abs_p95,
            "flip_jitter_rms_ms": rms_jitter_ms,
            "phase_timing_abs_mean_ms": self._safe_mean(phase_abs_error_ms),
            "phase_timing_abs_p95_ms": self._percentile(phase_abs_error_ms, 0.95),
            "runtime_priority_applied": bool(
                self.runtime_priority_result.applied if self.runtime_priority_result else False
            ),
            "runtime_priority_strategy": (
                self.runtime_priority_result.strategy if self.runtime_priority_result else "none"
            ),
        }
        return text, payload

    def _event_type_for_key(self, key: str) -> tuple[str, StatusKind]:
        scanner_key = self.request.scanner_trigger_mode.params.get("key", "5")
        if self.request.scanner_trigger_mode.mode in {"key", "ttl"} and key == scanner_key:
            return "pulse", StatusKind.SYNC
        return "response", StatusKind.EVENT

    def _sanitize_stim_params(self, params: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in params.items():
            if key == "image":
                shape = getattr(value, "shape", None)
                dtype = getattr(value, "dtype", None)
                out["image_meta"] = {
                    "shape": list(shape) if shape is not None else None,
                    "dtype": str(dtype) if dtype is not None else type(value).__name__,
                }
                continue
            out[key] = value
        return out

    def _notify_recorders(
        self,
        method: str,
        *args: Any,
        recorders: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        active = self.recorders if recorders is None else recorders
        for recorder in active:
            callback = getattr(recorder, method, None)
            if not callable(callback):
                continue
            try:
                callback(*args, **kwargs)
            except Exception as exc:
                self.logger.log_event(
                    onset_ns=time.monotonic_ns(),
                    event_type="recorder_error",
                    recorder=recorder.__class__.__name__,
                    method=method,
                    message=str(exc),
                )

    def _start_recorders(self) -> list[Any]:
        outdir = self.logger.paths.events_tsv.parent
        started: list[Any] = []
        for recorder in self.recorders:
            recorder.start(stem=self.request.bids_stem, output_dir=outdir)
            started.append(recorder)
        return started

    def _register_recorder_artifacts(self, recorder: Any) -> None:
        records_fn = getattr(recorder, "artifact_records", None)
        if callable(records_fn):
            for kind, path in records_fn():
                self.logger.register_artifact(path=path, kind=str(kind))
            return

        paths_fn = getattr(recorder, "artifact_paths", None)
        if callable(paths_fn):
            for path in paths_fn():
                kind = f"{recorder.__class__.__name__.lower()}_artifact"
                self.logger.register_artifact(path=path, kind=kind)

    def _stop_recorders(self, recorders: list[Any]) -> None:
        for recorder in reversed(recorders):
            try:
                recorder.stop()
            except Exception as exc:
                self.logger.log_event(
                    onset_ns=time.monotonic_ns(),
                    event_type="recorder_error",
                    recorder=recorder.__class__.__name__,
                    method="stop",
                    message=str(exc),
                )
            finally:
                self._register_recorder_artifacts(recorder)

    def _prelude_section(self, name: str) -> dict[str, Any]:
        raw = self.prelude.get(name, {})
        return dict(raw) if isinstance(raw, dict) else {}

    def _framebuffer_size(self) -> tuple[int, int]:
        fn = getattr(self.backend, "framebuffer_size", None)
        if callable(fn):
            try:
                w, h = fn()
                w_i, h_i = int(w), int(h)
                if w_i > 0 and h_i > 0:
                    return w_i, h_i
            except Exception:
                pass
        return max(1, int(self.display_config.width)), max(1, int(self.display_config.height))

    def _as_rgba_float(
        self,
        value: Any,
        default: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        if isinstance(value, (list, tuple)):
            seq = [float(v) for v in value]
        else:
            seq = list(default)
        if len(seq) < 3:
            seq = list(default)
        if len(seq) == 3:
            seq.append(default[3])
        seq = seq[:4]
        if max(abs(v) for v in seq) > 1.0:
            seq = [seq[0] / 255.0, seq[1] / 255.0, seq[2] / 255.0, seq[3] / 255.0 if seq[3] > 1.0 else seq[3]]
        return (
            max(0.0, min(1.0, float(seq[0]))),
            max(0.0, min(1.0, float(seq[1]))),
            max(0.0, min(1.0, float(seq[2]))),
            max(0.0, min(1.0, float(seq[3]))),
        )

    def _as_rgba_u8(
        self,
        value: Any,
        default: tuple[float, float, float, float],
    ) -> tuple[int, int, int, int]:
        rgba = self._as_rgba_float(value, default=default)
        return tuple(int(round(v * 255.0)) for v in rgba)

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _coerce_pair(value: Any, default: tuple[float, float]) -> tuple[float, float]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return float(value[0]), float(value[1])
            except Exception:
                return default
        return default

    @staticmethod
    def _load_font(font_size_px: int, font_path: str | None = None) -> Any:
        from PIL import ImageFont

        candidates: list[str] = []
        if font_path:
            candidates.append(str(font_path))
        candidates.extend(
            [
                "SF Pro Text.ttf",
                "SF Pro Display.ttf",
                "HelveticaNeue.ttc",
                "Arial.ttf",
                "DejaVuSans.ttf",
            ]
        )
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=font_size_px)
            except Exception:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _wrap_text_lines(draw: Any, text: str, font: Any, max_width_px: int) -> list[str]:
        lines: list[str] = []
        for para in str(text).splitlines():
            paragraph = para.strip()
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split()
            cur = words[0]
            for word in words[1:]:
                trial = f"{cur} {word}"
                if draw.textlength(trial, font=font) <= max_width_px:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        return lines or [""]

    @staticmethod
    def _line_height(font: Any) -> int:
        try:
            bbox = font.getbbox("Ag")
            return max(1, int(bbox[3] - bbox[1]))
        except Exception:
            return max(1, int(getattr(font, "size", 16)))

    def _prelude_background_batch(self) -> DrawBatch:
        bg_cfg = self._prelude_section("background")
        bg_val = bg_cfg.get("color", self.prelude.get("background_color", [0.0, 0.0, 0.0, 1.0]))
        bg = self._as_rgba_float(bg_val, default=(0.0, 0.0, 0.0, 1.0))

        batch = DrawBatch()
        batch.add(
            "shape",
            shape="rect",
            center=(0.0, 0.0),
            size=(2.0, 2.0),
            fill_color=bg,
            stroke_width=0.0,
        )
        return batch

    def _render_instruction_text_image(self, text: str, instruction_cfg: dict[str, Any]) -> Any:
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return None
        import numpy as np

        style_cfg = dict(instruction_cfg.get("style", {})) if isinstance(instruction_cfg.get("style"), dict) else {}
        fb_w, fb_h = self._framebuffer_size()
        canvas_w = int(
            instruction_cfg.get(
                "text_width_px",
                self.prelude.get("instruction_text_width_px", fb_w),
            )
        )
        canvas_h = int(
            instruction_cfg.get(
                "text_height_px",
                self.prelude.get("instruction_text_height_px", fb_h),
            )
        )
        canvas_w = max(320, canvas_w)
        canvas_h = max(180, canvas_h)

        render_scale = max(0.75, self._coerce_float(style_cfg.get("render_scale"), 1.0))
        render_w = max(320, int(round(canvas_w * render_scale)))
        render_h = max(180, int(round(canvas_h * render_scale)))

        panel_width_fraction = max(0.3, min(0.95, self._coerce_float(style_cfg.get("panel_width_fraction"), 0.78)))
        panel_height_fraction = max(0.25, min(0.95, self._coerce_float(style_cfg.get("panel_height_fraction"), 0.58)))
        panel_w = int(round(render_w * panel_width_fraction))
        panel_h = int(round(render_h * panel_height_fraction))

        panel_padding_px = max(12, int(round(self._coerce_float(style_cfg.get("panel_padding_px"), 48.0) * render_scale)))
        corner_radius_px = max(0, int(round(self._coerce_float(style_cfg.get("panel_corner_radius_px"), 26.0) * render_scale)))
        border_px = max(0, int(round(self._coerce_float(style_cfg.get("panel_border_px"), 2.0) * render_scale)))
        line_spacing_px = max(2, int(round(self._coerce_float(style_cfg.get("line_spacing_px"), 10.0) * render_scale)))

        panel_fill = self._as_rgba_u8(style_cfg.get("panel_fill"), default=(0.08, 0.10, 0.14, 0.88))
        panel_border = self._as_rgba_u8(style_cfg.get("panel_border"), default=(0.85, 0.88, 0.94, 0.38))
        text_color = self._as_rgba_u8(
            style_cfg.get("text_color", self.prelude.get("instruction_text_fg_rgb", [255, 255, 255])),
            default=(0.96, 0.97, 0.99, 1.0),
        )
        shadow = self._as_rgba_u8(style_cfg.get("panel_shadow"), default=(0.0, 0.0, 0.0, 0.26))
        shadow_offset = max(0, int(round(self._coerce_float(style_cfg.get("panel_shadow_offset_px"), 8.0) * render_scale)))

        x0 = max(0, int((render_w - panel_w) / 2 + self._coerce_float(style_cfg.get("offset_x_px"), 0.0)))
        y0 = max(0, int((render_h - panel_h) / 2 + self._coerce_float(style_cfg.get("offset_y_px"), 0.0)))
        x1 = min(render_w - 1, x0 + panel_w)
        y1 = min(render_h - 1, y0 + panel_h)

        img = Image.new("RGBA", (render_w, render_h), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        if shadow[3] > 0 and shadow_offset > 0:
            draw.rounded_rectangle(
                [x0 + shadow_offset, y0 + shadow_offset, x1 + shadow_offset, y1 + shadow_offset],
                radius=corner_radius_px,
                fill=shadow,
            )
        draw.rounded_rectangle([x0, y0, x1, y1], radius=corner_radius_px, fill=panel_fill)
        if border_px > 0:
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=corner_radius_px,
                outline=panel_border,
                width=border_px,
            )

        text_area_w = max(40, panel_w - 2 * panel_padding_px)
        text_area_h = max(40, panel_h - 2 * panel_padding_px)
        font_size_px = int(round(self._coerce_float(style_cfg.get("font_size_px"), 44.0) * render_scale))
        font_size_min_px = int(round(self._coerce_float(style_cfg.get("font_size_min_px"), 18.0) * render_scale))
        font_size_px = max(font_size_min_px, font_size_px)
        font_path = style_cfg.get("font_path")

        chosen_font = self._load_font(font_size_px, font_path=font_path)
        wrapped_lines = self._wrap_text_lines(draw, text, chosen_font, text_area_w)
        chosen_line_h = self._line_height(chosen_font)
        align = str(style_cfg.get("text_align", "center")).lower()
        text_widths = [int(draw.textlength(line, font=chosen_font)) for line in wrapped_lines]

        for try_size in range(font_size_px, font_size_min_px - 1, -2):
            font = self._load_font(try_size, font_path=font_path)
            lines = self._wrap_text_lines(draw, text, font, text_area_w)
            line_h = self._line_height(font)
            widths = [int(draw.textlength(line, font=font)) for line in lines]
            block_h = len(lines) * line_h + max(0, len(lines) - 1) * line_spacing_px
            if (not widths or max(widths) <= text_area_w) and block_h <= text_area_h:
                chosen_font = font
                wrapped_lines = lines
                chosen_line_h = line_h
                text_widths = widths
                break

        block_h = len(wrapped_lines) * chosen_line_h + max(0, len(wrapped_lines) - 1) * line_spacing_px
        text_y = y0 + int((panel_h - block_h) / 2)
        text_x_left = x0 + panel_padding_px
        text_x_right = x1 - panel_padding_px
        for line, line_w in zip(wrapped_lines, text_widths):
            if align == "left":
                text_x = text_x_left
            elif align == "right":
                text_x = text_x_right - line_w
            else:
                text_x = x0 + int((panel_w - line_w) / 2)
            draw.text((text_x, text_y), line, font=chosen_font, fill=text_color)
            text_y += chosen_line_h + line_spacing_px

        if render_w != canvas_w or render_h != canvas_h:
            img = img.resize((canvas_w, canvas_h), resample=Image.Resampling.LANCZOS)
        return np.ascontiguousarray(img, dtype=np.uint8)

    def _instruction_batch(self) -> DrawBatch:
        batch = self._prelude_background_batch()
        instruction_cfg = self._prelude_section("instruction")
        instruction_image = instruction_cfg.get("image", self.prelude.get("instruction_image"))
        if instruction_image:
            size = instruction_cfg.get("size", self.prelude.get("instruction_image_size", (1.5, 0.9)))
            center = instruction_cfg.get("center", self.prelude.get("instruction_image_center", (0.0, 0.0)))
            batch.add(
                "image",
                source=str(instruction_image),
                center=tuple(center),
                size=tuple(size),
                coord_space="square",
                opacity=1.0,
            )
            return batch

        instruction_text = instruction_cfg.get("text", self.prelude.get("instruction_text"))
        if instruction_text:
            frame = self._render_instruction_text_image(str(instruction_text), instruction_cfg=instruction_cfg)
            if frame is not None:
                center = self._coerce_pair(instruction_cfg.get("center", (0.0, 0.0)), default=(0.0, 0.0))
                size_val = instruction_cfg.get("size", self.prelude.get("instruction_text_size"))
                if size_val is not None:
                    size = self._coerce_pair(size_val, default=(1.45, 0.9))
                else:
                    frame_h, frame_w = frame.shape[0], frame.shape[1]
                    aspect = float(frame_w) / float(max(frame_h, 1))
                    max_h = self._coerce_float(instruction_cfg.get("max_height"), 1.05)
                    max_w = self._coerce_float(instruction_cfg.get("max_width"), 1.65)
                    height = min(max_h, max_w / max(aspect, 1e-6))
                    width = height * aspect
                    size = (width, height)
                batch.add(
                    "video_frame",
                    image=frame,
                    center=center,
                    size=size,
                    coord_space="square",
                    opacity=1.0,
                )
        return batch

    def _fixation_wait_batch(self) -> DrawBatch:
        batch = self._prelude_background_batch()
        wait_cfg = self._prelude_section("fixation_wait")
        fix_color = self._as_rgba_float(
            wait_cfg.get("color", self.prelude.get("fixation_color", [0.8, 0.8, 0.8, 1.0])),
            default=(0.8, 0.8, 0.8, 1.0),
        )
        extent = self._coerce_float(
            wait_cfg.get("extent", self.prelude.get("fixation_extent", 0.03)),
            0.03,
        )
        line_width = self._coerce_float(
            wait_cfg.get("line_width_px", self.prelude.get("fixation_line_width_px", 2.0)),
            2.0,
        )
        batch.add(
            "line",
            start=(-extent, 0.0),
            end=(extent, 0.0),
            width=line_width,
            color=fix_color,
            coord_space="square",
        )
        batch.add(
            "line",
            start=(0.0, -extent),
            end=(0.0, extent),
            width=line_width,
            color=fix_color,
            coord_space="square",
        )
        return batch

    def _normalize_wait_keys(self, keys: Any) -> set[str]:
        if keys is None:
            return set()
        if isinstance(keys, str):
            return {keys.lower()}
        if isinstance(keys, (list, tuple, set)):
            return {str(k).lower() for k in keys}
        return {str(keys).lower()}

    def _wait_stage(
        self,
        batch: DrawBatch,
        wait_keys: set[str],
        timeout_s: float | None,
    ) -> str | None:
        frame_step_ns = int(1_000_000_000 / max(self.display_config.refresh_hz, 1.0))
        stage_start_ns = time.monotonic_ns()
        next_flip_ns = stage_start_ns
        while True:
            self.backend.draw(batch)
            self.backend.flip(target_ns=next_flip_ns)
            for event in self.backend.poll_input():
                key = str(event.key).lower()
                if key == "q":
                    return "q"
                if key in wait_keys:
                    return key

            if timeout_s is not None:
                elapsed_s = (time.monotonic_ns() - stage_start_ns) / 1_000_000_000.0
                if elapsed_s >= float(timeout_s):
                    return None
            next_flip_ns += frame_step_ns

    def _run_prelude(self) -> bool:
        if not bool(self.prelude.get("enabled", False)):
            return True

        instruction_cfg = self._prelude_section("instruction")
        instruction_text = instruction_cfg.get("text", self.prelude.get("instruction_text"))
        instruction_image = instruction_cfg.get("image", self.prelude.get("instruction_image"))
        has_instruction = bool(instruction_text or instruction_image)

        if has_instruction:
            wait_keys = self._normalize_wait_keys(
                instruction_cfg.get("continue_keys", self.prelude.get("instruction_continue_key"))
            )
            timeout_s = instruction_cfg.get("timeout_s", self.prelude.get("instruction_duration_s"))
            if (not wait_keys) and timeout_s is None:
                timeout_s = 2.0
            key = self._wait_stage(
                batch=self._instruction_batch(),
                wait_keys=wait_keys,
                timeout_s=float(timeout_s) if timeout_s is not None else None,
            )
            if key == "q":
                return False

        wait_cfg = self._prelude_section("fixation_wait")
        if bool(wait_cfg.get("enabled", self.prelude.get("show_fixation_wait", True))):
            start_key = wait_cfg.get("start_keys", wait_cfg.get("start_key", self.prelude.get("start_key")))
            if not start_key:
                scanner_key = str(self.request.scanner_trigger_mode.params.get("key", "t"))
                start_key = scanner_key if scanner_key else "t"
            wait_keys = self._normalize_wait_keys(start_key)
            key = self._wait_stage(
                batch=self._fixation_wait_batch(),
                wait_keys=wait_keys,
                timeout_s=None,
            )
            if key == "q":
                return False
        return True

    def run(self) -> SessionResult:
        planned_t0_ns = int(self.request.t0_ns)
        planned_phase_rows = self._planned_phase_rows()
        pre_run_summary_text = ""
        pre_run_summary_payload: dict[str, Any] = {}
        pre_summary_event_logged = False
        post_run_summary_text = ""
        post_run_summary_payload: dict[str, Any] = {}

        run_start_ns = planned_t0_ns
        run_end_ns = run_start_ns
        frame_step_ns = int(1_000_000_000 / max(self.display_config.refresh_hz, 1.0))

        status = RunEndStatus.OK
        error_msg: str | None = None
        abort_requested = False
        abort_reason: str | None = None
        started_recorders: list[Any] = []
        run_started_emitted = False

        try:
            self.runtime_priority_result = apply_runtime_priority(self.runtime_priority)
            self.logger.metadata["runtime_priority"] = self.runtime_priority_result.as_dict()
            self.backend.initialize(self.display_config)
            started_recorders = self._start_recorders()
            pre_run_summary_text, pre_run_summary_payload = self._build_pre_run_summary(
                planned_t0_ns=planned_t0_ns,
                planned_phase_rows=planned_phase_rows,
            )
            print(pre_run_summary_text, flush=True)

            if not self._run_prelude():
                run_end_ns = time.monotonic_ns()
                status = RunEndStatus.ABORTED
                error_msg = "aborted_during_prelude"
                self.logger.log_status(
                    StatusKind.RUN_ENDED,
                    run_end_ns,
                    status=RunEndStatus.ABORTED.value,
                    reason=error_msg,
                )
                return SessionResult(
                    run_start_ns=run_start_ns,
                    run_end_ns=run_end_ns,
                    status=status,
                    error=error_msg,
                )

            now_ns = self.scheduler.now_ns()
            if now_ns > planned_t0_ns:
                run_start_ns = now_ns
                self.logger.log_event(
                    onset_ns=now_ns,
                    event_type="run_start_adjusted",
                    planned_t0_ns=planned_t0_ns,
                    adjusted_t0_ns=run_start_ns,
                )
                self.request.t0_ns = run_start_ns
            else:
                run_start_ns = planned_t0_ns

            run_start_ns = self.scheduler.start(run_start_ns)
            self.logger.log_status(
                StatusKind.RUN_STARTED, run_start_ns, bids_stem=self.request.bids_stem
            )
            self._notify_recorders(
                "on_run_started", run_start_ns, recorders=started_recorders
            )
            for trial in self.trials:
                trial.on_run_start(run_start_ns)
            run_started_emitted = True
            self.logger.log_event(
                onset_ns=run_start_ns,
                event_type="run_plan_summary",
                summary_text=pre_run_summary_text,
                **pre_run_summary_payload,
            )
            pre_summary_event_logged = True

            for trial in self.trials:
                if abort_requested:
                    break
                for phase_index, phase in enumerate(trial.phases):
                    if abort_requested:
                        break
                    window = self.scheduler.reserve(phase.duration_s)

                    self.logger.log_status(
                        StatusKind.PHASE_STARTED,
                        window.start_ns,
                        trial_nr=trial.trial_nr,
                        phase=phase_index,
                        phase_name=phase.name,
                    )
                    self.logger.log_event(
                        onset_ns=window.start_ns,
                        event_type=phase.name,
                        trial_nr=trial.trial_nr,
                        phase=phase_index,
                        duration_ns=window.end_ns - window.start_ns,
                    )
                    self._notify_recorders(
                        "on_phase_started",
                        trial_nr=trial.trial_nr,
                        phase_index=phase_index,
                        phase_name=phase.name,
                        phase_start_ns=window.start_ns,
                        phase_end_ns=window.end_ns,
                        recorders=started_recorders,
                    )

                    next_flip_ns = window.start_ns
                    while next_flip_ns < window.end_ns and not abort_requested:
                        now_ns = self.scheduler.now_ns()
                        if now_ns > next_flip_ns + (2 * frame_step_ns):
                            # Resynchronize to prevent runaway backlog.
                            next_flip_ns = now_ns

                        batch = trial.draw(phase_index=phase_index, now_ns=now_ns)
                        self.backend.draw(batch)

                        flip = self.backend.flip(target_ns=next_flip_ns)
                        self.logger.log_flip(
                            timestamp_ns=flip.timestamp_ns,
                            target_ns=flip.target_ns,
                            frame_index=flip.frame_index,
                            late_ns=flip.late_ns,
                            dropped_frames=flip.dropped_frames,
                            trial_nr=trial.trial_nr,
                            phase=phase_index,
                        )
                        self._notify_recorders(
                            "on_flip",
                            frame_index=flip.frame_index,
                            timestamp_ns=flip.timestamp_ns,
                            trial_nr=trial.trial_nr,
                            phase_index=phase_index,
                            recorders=started_recorders,
                        )

                        for cmd in batch.commands:
                            self.logger.log_stimulus(
                                timestamp_ns=flip.timestamp_ns,
                                trial_nr=trial.trial_nr,
                                phase=phase_index,
                                kind=cmd.kind,
                                params=self._sanitize_stim_params(cmd.params),
                            )

                        for event in self.backend.poll_input():
                            if str(event.key).lower() == "q":
                                abort_requested = True
                                abort_reason = "q_key"
                                self.logger.log_event(
                                    onset_ns=event.timestamp_ns,
                                    event_type="abort",
                                    trial_nr=trial.trial_nr,
                                    phase=phase_index,
                                    response=event.key,
                                )
                                self.logger.log_status(
                                    StatusKind.EVENT,
                                    event.timestamp_ns,
                                    trial_nr=trial.trial_nr,
                                    phase=phase_index,
                                    key=event.key,
                                    event_type="abort",
                                )
                                self._notify_recorders(
                                    "on_input",
                                    key=event.key,
                                    timestamp_ns=event.timestamp_ns,
                                    event_type="abort",
                                    trial_nr=trial.trial_nr,
                                    phase_index=phase_index,
                                    recorders=started_recorders,
                                )
                                break

                            event_type, status_kind = self._event_type_for_key(event.key)
                            self.logger.log_event(
                                onset_ns=event.timestamp_ns,
                                event_type=event_type,
                                trial_nr=trial.trial_nr,
                                phase=phase_index,
                                response=event.key,
                            )
                            self.logger.log_status(
                                status_kind,
                                event.timestamp_ns,
                                trial_nr=trial.trial_nr,
                                phase=phase_index,
                                key=event.key,
                            )
                            trial.on_input(event, phase_index=phase_index)
                            self._notify_recorders(
                                "on_input",
                                key=event.key,
                                timestamp_ns=event.timestamp_ns,
                                event_type=event_type,
                                trial_nr=trial.trial_nr,
                                phase_index=phase_index,
                                recorders=started_recorders,
                            )

                        next_flip_ns += frame_step_ns

            run_end_ns = time.monotonic_ns()
            if abort_requested:
                status = RunEndStatus.ABORTED
                self.logger.log_status(
                    StatusKind.RUN_ENDED,
                    run_end_ns,
                    status=RunEndStatus.ABORTED.value,
                    reason=abort_reason or "abort_requested",
                )
            else:
                self.logger.log_status(
                    StatusKind.RUN_ENDED, run_end_ns, status=RunEndStatus.OK.value
                )

        except Exception as exc:
            run_end_ns = time.monotonic_ns()
            status = RunEndStatus.ERROR
            error_msg = str(exc)
            self.logger.log_status(
                StatusKind.RUN_ENDED,
                run_end_ns,
                status=RunEndStatus.ERROR.value,
                error=error_msg,
            )
            raise

        finally:
            if not pre_run_summary_text:
                pre_run_summary_text, pre_run_summary_payload = self._build_pre_run_summary(
                    planned_t0_ns=planned_t0_ns,
                    planned_phase_rows=planned_phase_rows,
                )
                print(pre_run_summary_text, flush=True)
            if run_started_emitted and not pre_summary_event_logged:
                self.logger.log_event(
                    onset_ns=run_start_ns,
                    event_type="run_plan_summary",
                    summary_text=pre_run_summary_text,
                    **pre_run_summary_payload,
                )
                pre_summary_event_logged = True

            timing_dashboard_path = self.logger.write_timing_dashboard(
                run_start_ns=run_start_ns,
                run_end_ns=run_end_ns,
                refresh_hz=self.display_config.refresh_hz,
            )

            post_run_summary_text, post_run_summary_payload = self._build_post_run_summary(
                run_start_ns=run_start_ns,
                run_end_ns=run_end_ns,
                status=status,
                error=error_msg,
                planned_phase_rows=planned_phase_rows,
                planned_t0_ns=planned_t0_ns,
            )
            if timing_dashboard_path is not None:
                post_run_summary_text = (
                    f"{post_run_summary_text}\nTiming dashboard: {timing_dashboard_path}"
                )
                post_run_summary_payload["timing_dashboard"] = str(timing_dashboard_path)
            else:
                dash_error = str(self.logger.metadata.get("timing_dashboard_error", "")).strip()
                if dash_error:
                    post_run_summary_text = (
                        f"{post_run_summary_text}\n"
                        f"Timing dashboard: not generated ({dash_error})"
                    )
                    post_run_summary_payload["timing_dashboard_error"] = dash_error
            print(post_run_summary_text, flush=True)

            if run_started_emitted:
                self.logger.log_event(
                    onset_ns=run_end_ns,
                    event_type="run_result_summary",
                    duration_ns=max(0, run_end_ns - run_start_ns),
                    summary_text=post_run_summary_text,
                    **post_run_summary_payload,
                )
            self.logger.metadata["run_plan_summary"] = pre_run_summary_payload
            self.logger.metadata["run_result_summary"] = post_run_summary_payload

            if run_started_emitted:
                self._notify_recorders(
                    "on_run_ended",
                    run_end_ns=run_end_ns,
                    status=status,
                    error=error_msg,
                    recorders=started_recorders,
                )
            self._stop_recorders(started_recorders)
            self.backend.shutdown()
            report_sections = [pre_run_summary_text, post_run_summary_text]
            report_text = "\n\n".join(section for section in report_sections if section).strip()
            if report_text:
                report_text += "\n"
            self.logger.write_text_report(report_text)
            self.logger.finalize(run_start_ns=run_start_ns, run_end_ns=run_end_ns)

        return SessionResult(
            run_start_ns=run_start_ns,
            run_end_ns=run_end_ns,
            status=status,
            error=error_msg,
        )
