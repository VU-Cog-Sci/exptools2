from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from exptools2.core.types import DrawBatch

from .client import EyeLinkUnavailableError, _import_pylink

try:  # pragma: no cover - depends on local SR install
    _pylink = _import_pylink()
    _EyeLinkDisplayBase = _pylink.EyeLinkCustomDisplay
except Exception:  # pragma: no cover
    _pylink = None

    class _EyeLinkDisplayBase:  # type: ignore[override]
        pass


@dataclass(slots=True)
class EyeLinkGraphicsConfig:
    background_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    foreground_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    target_radius_px: float = 14.0
    target_inner_radius_px: float = 3.0
    target_stroke_px: float = 2.0


class GLEyeLinkCoreGraphics(_EyeLinkDisplayBase):
    """Minimal EyeLink custom display implemented against the GL backend."""

    def __init__(self, backend: Any, config: EyeLinkGraphicsConfig | None = None) -> None:
        if _pylink is None:
            raise EyeLinkUnavailableError("pylink is required for EyeLink calibration graphics")
        super().__init__()
        self.backend = backend
        self.config = config or EyeLinkGraphicsConfig()
        self._camera_size = (384, 320)
        self._palette_r: np.ndarray | None = None
        self._palette_g: np.ndarray | None = None
        self._palette_b: np.ndarray | None = None
        self._camera_idx: np.ndarray | None = None
        self._camera_frame: np.ndarray | None = None
        self._last_target_px = (0, 0)

    def _framebuffer_size(self) -> tuple[int, int]:
        if hasattr(self.backend, "framebuffer_size"):
            w, h = self.backend.framebuffer_size()
            return max(int(w), 1), max(int(h), 1)
        cfg = getattr(self.backend, "config", None)
        if cfg is not None:
            return max(int(getattr(cfg, "width", 1)), 1), max(int(getattr(cfg, "height", 1)), 1)
        return (1, 1)

    def _pixel_to_square(self, x_px: float, y_px: float) -> tuple[float, float]:
        w, h = self._framebuffer_size()
        ndc_x = (float(x_px) / float(w)) * 2.0 - 1.0
        ndc_y = 1.0 - (float(y_px) / float(h)) * 2.0
        square_x_scale = float(h) / float(w)
        if square_x_scale <= 0:
            square_x_scale = 1.0
        return (ndc_x / square_x_scale, ndc_y)

    def _radius_px_to_square(self, radius_px: float) -> float:
        _, h = self._framebuffer_size()
        return (2.0 * float(radius_px)) / float(max(h, 1))

    def _clear_and_flip(self) -> None:
        batch = DrawBatch()
        bg = self.config.background_color
        batch.add(
            "shape",
            shape="rect",
            center=(0.0, 0.0),
            size=(2.0, 2.0),
            fill_color=bg,
            stroke_width=0.0,
        )
        self.backend.draw(batch)
        self.backend.flip()

    def _draw_target(self, x_px: int, y_px: int) -> None:
        sx, sy = self._pixel_to_square(float(x_px), float(y_px))
        r_outer = self._radius_px_to_square(self.config.target_radius_px)
        r_inner = self._radius_px_to_square(self.config.target_inner_radius_px)
        stroke = max(self._radius_px_to_square(self.config.target_stroke_px), 1e-6)

        fg = self.config.foreground_color
        bg = self.config.background_color

        batch = DrawBatch()
        batch.add(
            "shape",
            shape="rect",
            center=(0.0, 0.0),
            size=(2.0, 2.0),
            fill_color=bg,
            stroke_width=0.0,
        )
        batch.add(
            "shape",
            shape="circle",
            center=(sx, sy),
            size=(2.0 * r_outer, 2.0 * r_outer),
            fill_color=(0.0, 0.0, 0.0, 0.0),
            stroke_color=fg,
            line_width=stroke,
            stroke_width=0.001,
            coord_space="square",
        )
        batch.add(
            "shape",
            shape="circle",
            center=(sx, sy),
            size=(2.0 * r_inner, 2.0 * r_inner),
            fill_color=fg,
            stroke_width=0.0,
            coord_space="square",
        )
        self.backend.draw(batch)
        self.backend.flip()

    def setup_cal_display(self) -> None:
        self._clear_and_flip()

    def clear_cal_display(self) -> None:
        self._clear_and_flip()

    def exit_cal_display(self) -> None:
        self._clear_and_flip()

    def record_abort_hide(self) -> None:
        return

    def erase_cal_target(self) -> None:
        self._clear_and_flip()

    def draw_cal_target(self, x: int, y: int) -> None:
        self._last_target_px = (int(x), int(y))
        self._draw_target(int(x), int(y))

    def play_beep(self, beepid: int) -> None:  # noqa: ARG002
        return

    def get_mouse_state(self):
        if hasattr(self.backend, "mouse_state"):
            x_px, y_px, pressed = self.backend.mouse_state()
        else:
            w, h = self._framebuffer_size()
            x_px = w * 0.5
            y_px = h * 0.5
            pressed = 0

        cam_w, cam_h = self._camera_size
        w, h = self._framebuffer_size()
        cam_x = int(np.clip((float(x_px) / float(max(w, 1))) * cam_w, 0, cam_w - 1))
        cam_y = int(np.clip((float(y_px) / float(max(h, 1))) * cam_h, 0, cam_h - 1))
        return ((cam_x, cam_y), int(1 if pressed else 0))

    def _map_key(self, key: str) -> int:
        assert _pylink is not None
        k = str(key).lower()
        mapping = {
            "f1": _pylink.F1_KEY,
            "f2": _pylink.F2_KEY,
            "f3": _pylink.F3_KEY,
            "f4": _pylink.F4_KEY,
            "f5": _pylink.F5_KEY,
            "f6": _pylink.F6_KEY,
            "f7": _pylink.F7_KEY,
            "f8": _pylink.F8_KEY,
            "f9": _pylink.F9_KEY,
            "f10": _pylink.F10_KEY,
            "pageup": _pylink.PAGE_UP,
            "pagedown": _pylink.PAGE_DOWN,
            "up": _pylink.CURS_UP,
            "down": _pylink.CURS_DOWN,
            "left": _pylink.CURS_LEFT,
            "right": _pylink.CURS_RIGHT,
            "backspace": ord("\b"),
            "enter": _pylink.ENTER_KEY,
            "return": _pylink.ENTER_KEY,
            "space": ord(" "),
            "escape": 27,
            "tab": ord("\t"),
            "equal": ord("+"),
            "plus": ord("+"),
            "minus": ord("-"),
        }
        if k in mapping:
            return int(mapping[k])
        if len(k) == 1:
            return ord(k)
        return int(getattr(_pylink, "JUNK_KEY", 0))

    def get_input_key(self):
        if _pylink is None:
            return []
        keys = []
        for event in self.backend.poll_input():
            code = self._map_key(str(event.key))
            if code:
                keys.append(_pylink.KeyInput(code, 0))
        return keys

    def setup_image_display(self, width: int, height: int) -> int:
        self._camera_size = (int(width), int(height))
        self._camera_idx = np.zeros((int(height), int(width)), dtype=np.uint8)
        self._camera_frame = None
        return 1

    def image_title(self, text: str) -> None:  # noqa: ARG002
        return

    def draw_image_line(self, width: int, line: int, totlines: int, buff) -> None:
        if self._camera_idx is None:
            self._camera_idx = np.zeros((int(totlines), int(width)), dtype=np.uint8)

        y = int(line) - 1
        if 0 <= y < self._camera_idx.shape[0]:
            row = np.asarray(buff, dtype=np.uint8)
            self._camera_idx[y, : min(row.shape[0], self._camera_idx.shape[1])] = row[
                : self._camera_idx.shape[1]
            ]

        if int(line) != int(totlines):
            return

        if self._palette_r is None or self._palette_g is None or self._palette_b is None:
            return

        idx = self._camera_idx
        if idx is None:
            return

        r = np.take(self._palette_r, idx)
        g = np.take(self._palette_g, idx)
        b = np.take(self._palette_b, idx)
        frame = np.stack([r, g, b], axis=-1).astype(np.uint8, copy=False)
        self._camera_frame = np.ascontiguousarray(frame)

        h, w = self._camera_frame.shape[0], self._camera_frame.shape[1]
        aspect = float(w) / float(max(h, 1))
        max_span = 1.5
        if aspect >= 1.0:
            size = (max_span, max_span / aspect)
        else:
            size = (max_span * aspect, max_span)

        batch = DrawBatch()
        batch.add("video_frame", image=self._camera_frame, center=(0.0, 0.0), size=size)
        self.backend.draw(batch)
        self.backend.flip()

    def set_image_palette(self, r, g, b) -> None:
        self._palette_r = np.asarray(r, dtype=np.uint8)
        self._palette_g = np.asarray(g, dtype=np.uint8)
        self._palette_b = np.asarray(b, dtype=np.uint8)

    def draw_line(self, x1, y1, x2, y2, colorindex):  # noqa: ARG002
        return

    def draw_lozenge(self, x, y, width, height, colorindex):  # noqa: ARG002
        return

    def exit_image_display(self) -> None:
        self._camera_idx = None
        self._camera_frame = None
        self._clear_and_flip()

    def alert_printf(self, msg: str) -> None:
        print(f"EyeLink alert: {msg}")

