from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from .contract import validate_run_request
from .interfaces import DisplayBackend
from .logger import RunLogger
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
    ) -> None:
        validate_run_request(request)
        self.request = request
        self.backend = backend
        self.logger = logger
        self.display_config = display_config or DisplayConfig()
        self.scheduler = scheduler or NonSlipScheduler(t0_ns=request.t0_ns)
        self.recorders = list(recorders or [])
        self.prelude = dict(prelude or {})
        self.trials: list[Trial] = []
        random.seed(request.seed)

    def add_trial(self, trial: Trial) -> None:
        self.trials.append(trial)

    def add_trials(self, trials: list[Trial]) -> None:
        self.trials.extend(trials)

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
        run_start_ns = int(self.request.t0_ns)
        run_end_ns = run_start_ns
        frame_step_ns = int(1_000_000_000 / max(self.display_config.refresh_hz, 1.0))

        status = RunEndStatus.OK
        error_msg: str | None = None
        abort_requested = False
        abort_reason: str | None = None
        started_recorders: list[Any] = []
        run_started_emitted = False

        try:
            self.backend.initialize(self.display_config)
            started_recorders = self._start_recorders()
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

            planned_t0_ns = int(self.request.t0_ns)
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
            self.logger.finalize(run_start_ns=run_start_ns, run_end_ns=run_end_ns)

        return SessionResult(
            run_start_ns=run_start_ns,
            run_end_ns=run_end_ns,
            status=status,
            error=error_msg,
        )
