from __future__ import annotations

import ctypes
import time
from collections import deque
from typing import Any

import numpy as np

from exptools2.core.types import DisplayConfig, DrawBatch, FlipResult, InputEvent

from .shaders import (
    BAR_TEXTURE_FRAGMENT_SHADER,
    GABOR_FRAGMENT_SHADER,
    GABOR_VERTEX_SHADER,
    IMAGE_FRAGMENT_SHADER,
    IMAGE_VERTEX_SHADER,
    LINE_FRAGMENT_SHADER,
    LINE_VERTEX_SHADER,
    SDF_FRAGMENT_SHADER,
)

try:
    import glfw
except Exception:  # pragma: no cover
    glfw = None

try:
    from OpenGL import GL
except Exception:  # pragma: no cover
    GL = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


class GLDisplayBackend:
    """GLFW/OpenGL psychophysics backend."""

    def __init__(self) -> None:
        self.window: Any | None = None
        self.config: DisplayConfig | None = None
        self.frame_index: int = 0
        self._events: deque[InputEvent] = deque()
        self._gamma_lut: np.ndarray | None = None
        self._last_batch: DrawBatch | None = None

        self._quad_vao: int | None = None
        self._quad_vbo: int | None = None
        self._gabor_program: int | None = None
        self._sdf_program: int | None = None
        self._image_program: int | None = None
        self._line_program: int | None = None
        self._bar_texture_program: int | None = None
        self._texture_cache: dict[str, int] = {}
        self._video_texture_id: int | None = None
        self._video_texture_spec: tuple[int, int, int] | None = None
        self._fb_width: int = 0
        self._fb_height: int = 0

    _GLFW_SPECIAL_KEY_NAMES = {
        "KEY_ENTER": "enter",
        "KEY_KP_ENTER": "enter",
        "KEY_ESCAPE": "escape",
        "KEY_TAB": "tab",
        "KEY_BACKSPACE": "backspace",
        "KEY_SPACE": "space",
        "KEY_LEFT": "left",
        "KEY_RIGHT": "right",
        "KEY_UP": "up",
        "KEY_DOWN": "down",
        "KEY_PAGE_UP": "pageup",
        "KEY_PAGE_DOWN": "pagedown",
        "KEY_HOME": "home",
        "KEY_END": "end",
        "KEY_INSERT": "insert",
        "KEY_DELETE": "delete",
        "KEY_F1": "f1",
        "KEY_F2": "f2",
        "KEY_F3": "f3",
        "KEY_F4": "f4",
        "KEY_F5": "f5",
        "KEY_F6": "f6",
        "KEY_F7": "f7",
        "KEY_F8": "f8",
        "KEY_F9": "f9",
        "KEY_F10": "f10",
        "KEY_F11": "f11",
        "KEY_F12": "f12",
    }

    def _all_monitors(self) -> list[Any]:
        if glfw is None:
            return []
        mons = glfw.get_monitors()
        return list(mons) if mons else []

    def _monitor_name(self, monitor: Any) -> str:
        if glfw is None:
            return ""
        try:
            raw = glfw.get_monitor_name(monitor)
        except Exception:
            return ""
        if raw is None:
            return ""
        if isinstance(raw, bytes):
            return raw.decode("utf8", errors="replace")
        return str(raw)

    def _select_monitor(self, config: DisplayConfig) -> Any | None:
        if glfw is None:
            return None
        monitors = self._all_monitors()
        primary = glfw.get_primary_monitor()
        if not monitors:
            return primary

        if config.monitor_index is not None:
            try:
                idx = int(config.monitor_index)
            except Exception:
                idx = 0
            if idx < 0:
                idx = len(monitors) + idx
            if 0 <= idx < len(monitors):
                return monitors[idx]
            print(
                f"[exptools2] monitor_index={config.monitor_index} out of range; using primary monitor."
            )
            return primary

        selector = str(getattr(config, "monitor_name", "default") or "default").strip()
        if not selector:
            return primary

        lower = selector.lower()
        if lower in {"default", "primary", "main"}:
            return primary

        index_token = lower
        if lower.startswith("index:"):
            index_token = lower.split(":", 1)[1].strip()
        if index_token and (
            index_token.isdigit()
            or (index_token.startswith("-") and index_token[1:].isdigit())
        ):
            idx = int(index_token)
            if idx < 0:
                idx = len(monitors) + idx
            if 0 <= idx < len(monitors):
                return monitors[idx]

        name_query = selector
        if lower.startswith("name:"):
            name_query = selector.split(":", 1)[1].strip()
        name_query_lower = name_query.lower()
        for mon in monitors:
            mon_name = self._monitor_name(mon)
            if mon_name and mon_name.lower() == name_query_lower:
                return mon
        for mon in monitors:
            mon_name = self._monitor_name(mon)
            if mon_name and name_query_lower in mon_name.lower():
                return mon

        print(
            f"[exptools2] monitor_name={selector!r} not found; using primary monitor."
        )
        return primary

    def _position_window_on_monitor(self, monitor: Any) -> None:
        if self.window is None or glfw is None or monitor is None:
            return
        try:
            if hasattr(glfw, "get_monitor_workarea"):
                x, y, w, h = glfw.get_monitor_workarea(monitor)
            else:
                x, y = glfw.get_monitor_pos(monitor)
                mode = glfw.get_video_mode(monitor)
                if mode is None:
                    return
                w = mode.size.width
                h = mode.size.height
            ww, wh = glfw.get_window_size(self.window)
            target_x = int(x + max(0, (w - ww) / 2))
            target_y = int(y + max(0, (h - wh) / 2))
            glfw.set_window_pos(self.window, target_x, target_y)
        except Exception:
            return

    def initialize(self, config: DisplayConfig) -> None:
        self.config = config
        self.frame_index = 0
        self._events.clear()

        if glfw is None:
            raise RuntimeError(
                "glfw is required for GLDisplayBackend. Install 'glfw' and 'PyOpenGL'."
            )

        if not glfw.init():
            raise RuntimeError("Failed to initialize GLFW")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

        selected_monitor = self._select_monitor(config)
        monitor = selected_monitor if config.fullscreen else None
        mode = glfw.get_video_mode(monitor) if monitor is not None else None
        width = mode.size.width if mode and config.fullscreen else config.width
        height = mode.size.height if mode and config.fullscreen else config.height

        self.window = glfw.create_window(width, height, config.title, monitor, None)
        if self.window is None:
            glfw.terminate()
            raise RuntimeError("Could not create GLFW window")

        if (not config.fullscreen) and selected_monitor is not None:
            self._position_window_on_monitor(selected_monitor)

        glfw.make_context_current(self.window)
        glfw.swap_interval(1 if config.vsync else 0)

        if getattr(config, "hide_cursor", True):
            try:
                cursor_mode = glfw.CURSOR_DISABLED if config.fullscreen else glfw.CURSOR_HIDDEN
                glfw.set_input_mode(self.window, glfw.CURSOR, cursor_mode)
            except Exception:
                pass

        glfw.set_key_callback(self.window, self._on_key)
        glfw.set_framebuffer_size_callback(self.window, self._on_framebuffer_size)

        if GL is not None:
            fb_width, fb_height = glfw.get_framebuffer_size(self.window)
            self._fb_width = int(fb_width)
            self._fb_height = int(fb_height)
            GL.glViewport(0, 0, int(fb_width), int(fb_height))
            GL.glClearColor(0.0, 0.0, 0.0, 1.0)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            self._init_geometry()
            self._gabor_program = self._compile_program(GABOR_VERTEX_SHADER, GABOR_FRAGMENT_SHADER)
            self._sdf_program = self._compile_program(GABOR_VERTEX_SHADER, SDF_FRAGMENT_SHADER)
            self._image_program = self._compile_program(IMAGE_VERTEX_SHADER, IMAGE_FRAGMENT_SHADER)
            self._line_program = self._compile_program(LINE_VERTEX_SHADER, LINE_FRAGMENT_SHADER)
            self._bar_texture_program = self._compile_program(
                IMAGE_VERTEX_SHADER, BAR_TEXTURE_FRAGMENT_SHADER
            )

    def _init_geometry(self) -> None:
        assert GL is not None
        quad = np.array(
            [
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                1.0,
            ],
            dtype=np.float32,
        )

        self._quad_vao = GL.glGenVertexArrays(1)
        self._quad_vbo = GL.glGenBuffers(1)

        GL.glBindVertexArray(self._quad_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._quad_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, quad.nbytes, quad, GL.GL_STATIC_DRAW)

        stride = 4 * quad.itemsize
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(2 * quad.itemsize)
        )
        GL.glEnableVertexAttribArray(1)

        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)

    def _compile_shader(self, source: str, shader_type: int) -> int:
        assert GL is not None
        shader = GL.glCreateShader(shader_type)
        GL.glShaderSource(shader, source)
        GL.glCompileShader(shader)

        ok = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS)
        if not ok:
            error = GL.glGetShaderInfoLog(shader).decode("utf8", errors="replace")
            raise RuntimeError(f"Shader compilation failed: {error}")
        return shader

    def _compile_program(self, vert_src: str, frag_src: str) -> int:
        assert GL is not None
        vert = self._compile_shader(vert_src, GL.GL_VERTEX_SHADER)
        frag = self._compile_shader(frag_src, GL.GL_FRAGMENT_SHADER)

        program = GL.glCreateProgram()
        GL.glAttachShader(program, vert)
        GL.glAttachShader(program, frag)
        GL.glLinkProgram(program)

        ok = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
        if not ok:
            error = GL.glGetProgramInfoLog(program).decode("utf8", errors="replace")
            raise RuntimeError(f"Program link failed: {error}")

        GL.glDeleteShader(vert)
        GL.glDeleteShader(frag)
        return program

    def _on_key(self, window: Any, key: int, _scancode: int, action: int, _mods: int) -> None:
        if action == glfw.PRESS:
            key_name = glfw.get_key_name(key, 0)
            if key_name is None:
                key_name = str(key)
                for glfw_name, readable in self._GLFW_SPECIAL_KEY_NAMES.items():
                    glfw_value = getattr(glfw, glfw_name, None)
                    if glfw_value is not None and int(key) == int(glfw_value):
                        key_name = readable
                        break
            self._events.append(InputEvent(key=key_name, timestamp_ns=time.monotonic_ns()))

    def _on_framebuffer_size(self, _window: Any, width: int, height: int) -> None:
        if GL is None:
            return
        self._fb_width = int(width)
        self._fb_height = int(height)
        GL.glViewport(0, 0, int(width), int(height))

    def framebuffer_size(self) -> tuple[int, int]:
        if self.window is not None and glfw is not None:
            w, h = glfw.get_framebuffer_size(self.window)
            return int(w), int(h)
        return int(self._fb_width), int(self._fb_height)

    def mouse_state(self) -> tuple[float, float, int]:
        if self.window is None or glfw is None:
            return (0.0, 0.0, 0)
        x, y = glfw.get_cursor_pos(self.window)
        pressed = glfw.get_mouse_button(self.window, glfw.MOUSE_BUTTON_LEFT)
        return (float(x), float(y), int(pressed == glfw.PRESS))

    def _set_uniform_vec2(self, program: int, name: str, x: float, y: float) -> None:
        assert GL is not None
        loc = GL.glGetUniformLocation(program, name)
        if loc >= 0:
            GL.glUniform2f(loc, x, y)

    def _set_uniform_vec3(self, program: int, name: str, x: float, y: float, z: float) -> None:
        assert GL is not None
        loc = GL.glGetUniformLocation(program, name)
        if loc >= 0:
            GL.glUniform3f(loc, x, y, z)

    def _set_uniform_vec4(self, program: int, name: str, x: float, y: float, z: float, w: float) -> None:
        assert GL is not None
        loc = GL.glGetUniformLocation(program, name)
        if loc >= 0:
            GL.glUniform4f(loc, x, y, z, w)

    def _set_uniform_float(self, program: int, name: str, value: float) -> None:
        assert GL is not None
        loc = GL.glGetUniformLocation(program, name)
        if loc >= 0:
            GL.glUniform1f(loc, value)

    def _set_uniform_int(self, program: int, name: str, value: int) -> None:
        assert GL is not None
        loc = GL.glGetUniformLocation(program, name)
        if loc >= 0:
            GL.glUniform1i(loc, value)

    def _draw_quad(self) -> None:
        assert GL is not None
        assert self._quad_vao is not None
        GL.glBindVertexArray(self._quad_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

    def _square_x_scale(self) -> float:
        if self._fb_width > 0 and self._fb_height > 0:
            return float(self._fb_height) / float(self._fb_width)
        return 1.0

    def _load_texture(self, source: str) -> int:
        if GL is None:
            raise RuntimeError("OpenGL context is unavailable")
        if Image is None:
            raise RuntimeError("Pillow is required for image stimulus rendering")

        if source in self._texture_cache:
            return self._texture_cache[source]

        img = Image.open(source).convert("RGBA")
        # OpenGL texture coordinate origin is bottom-left.
        flip_flag = getattr(getattr(Image, "Transpose", Image), "FLIP_TOP_BOTTOM")
        img = img.transpose(flip_flag)
        data = np.asarray(img, dtype=np.uint8)
        width, height = img.size

        tex_id = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_RGBA,
            width,
            height,
            0,
            GL.GL_RGBA,
            GL.GL_UNSIGNED_BYTE,
            data,
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        self._texture_cache[source] = tex_id
        return tex_id

    def _render_gabor(self, params: dict[str, Any]) -> None:
        if GL is None or self._gabor_program is None:
            return

        center = params.get("center", (0.0, 0.0))
        size = params.get("size", (0.2, 0.2))
        color = params.get("color", (1.0, 1.0, 1.0))

        GL.glUseProgram(self._gabor_program)
        self._set_uniform_vec2(self._gabor_program, "u_center", float(center[0]), float(center[1]))
        self._set_uniform_vec2(self._gabor_program, "u_size", float(size[0]), float(size[1]))
        self._set_uniform_float(self._gabor_program, "u_phase", float(params.get("phase", 0.0)))
        self._set_uniform_float(
            self._gabor_program, "u_spatial_freq", float(params.get("spatial_freq", 2.0))
        )
        self._set_uniform_float(self._gabor_program, "u_sigma", float(params.get("sigma", 0.4)))
        self._set_uniform_float(
            self._gabor_program,
            "u_orientation_deg",
            float(params.get("orientation_deg", 0.0)),
        )
        self._set_uniform_float(
            self._gabor_program, "u_contrast", float(params.get("contrast", 1.0))
        )
        self._set_uniform_vec3(
            self._gabor_program,
            "u_color",
            float(color[0]),
            float(color[1]),
            float(color[2]),
        )
        self._draw_quad()
        GL.glUseProgram(0)

    def _render_image(self, params: dict[str, Any]) -> None:
        if GL is None or self._image_program is None:
            return

        source = params.get("source")
        if not source:
            return

        tex_id = self._load_texture(str(source))
        center = params.get("center", (0.0, 0.0))
        size = params.get("size", (0.6, 0.6))
        coord_space = str(params.get("coord_space", "ndc")).lower()
        if coord_space == "square":
            sx = self._square_x_scale()
            center = (float(center[0]) * sx, float(center[1]))
            size = (float(size[0]) * sx, float(size[1]))
        rotation_deg = float(params.get("rotation_deg", 0.0))
        opacity = float(params.get("opacity", 1.0))
        tint = params.get("tint", (1.0, 1.0, 1.0, 1.0))

        GL.glUseProgram(self._image_program)
        self._set_uniform_vec2(
            self._image_program, "u_center", float(center[0]), float(center[1])
        )
        self._set_uniform_vec2(self._image_program, "u_size", float(size[0]), float(size[1]))
        self._set_uniform_float(self._image_program, "u_rotation_deg", rotation_deg)
        self._set_uniform_float(self._image_program, "u_opacity", opacity)
        self._set_uniform_int(self._image_program, "u_flip_y", 0)
        self._set_uniform_vec4(
            self._image_program,
            "u_tint",
            float(tint[0]),
            float(tint[1]),
            float(tint[2]),
            float(tint[3]),
        )

        loc_tex = GL.glGetUniformLocation(self._image_program, "u_tex")
        if loc_tex >= 0:
            GL.glUniform1i(loc_tex, 0)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        self._draw_quad()
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glUseProgram(0)

    def _upload_video_texture(self, frame: np.ndarray) -> int:
        assert GL is not None

        if frame.ndim != 3:
            raise ValueError("video_frame image must be HxWxC")
        height, width, channels = frame.shape
        if channels not in (3, 4):
            raise ValueError("video_frame image channel count must be 3 or 4")

        data = np.ascontiguousarray(frame, dtype=np.uint8)
        fmt = GL.GL_RGB if channels == 3 else GL.GL_RGBA
        spec = (width, height, channels)

        if self._video_texture_id is None:
            self._video_texture_id = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._video_texture_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                fmt,
                width,
                height,
                0,
                fmt,
                GL.GL_UNSIGNED_BYTE,
                data,
            )
            self._video_texture_spec = spec
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            return self._video_texture_id

        GL.glBindTexture(GL.GL_TEXTURE_2D, self._video_texture_id)
        if self._video_texture_spec != spec:
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                fmt,
                width,
                height,
                0,
                fmt,
                GL.GL_UNSIGNED_BYTE,
                data,
            )
            self._video_texture_spec = spec
        else:
            GL.glTexSubImage2D(
                GL.GL_TEXTURE_2D,
                0,
                0,
                0,
                width,
                height,
                fmt,
                GL.GL_UNSIGNED_BYTE,
                data,
            )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return self._video_texture_id

    def _render_video_frame(self, params: dict[str, Any]) -> None:
        if GL is None or self._image_program is None:
            return

        frame = params.get("image")
        if frame is None:
            return
        if not isinstance(frame, np.ndarray):
            frame = np.asarray(frame)

        tex_id = self._upload_video_texture(frame)

        center = params.get("center", (0.0, 0.0))
        if "size" in params:
            size = params["size"]
        else:
            h, w = frame.shape[0], frame.shape[1]
            aspect = float(w) / float(max(h, 1))
            max_span = 1.8
            if aspect >= 1.0:
                size = (max_span, max_span / aspect)
            else:
                size = (max_span * aspect, max_span)
        coord_space = str(params.get("coord_space", "ndc")).lower()
        if coord_space == "square":
            sx = self._square_x_scale()
            center = (float(center[0]) * sx, float(center[1]))
            size = (float(size[0]) * sx, float(size[1]))

        rotation_deg = float(params.get("rotation_deg", 0.0))
        opacity = float(params.get("opacity", 1.0))
        tint = params.get("tint", (1.0, 1.0, 1.0, 1.0))

        GL.glUseProgram(self._image_program)
        self._set_uniform_vec2(
            self._image_program, "u_center", float(center[0]), float(center[1])
        )
        self._set_uniform_vec2(self._image_program, "u_size", float(size[0]), float(size[1]))
        self._set_uniform_float(self._image_program, "u_rotation_deg", rotation_deg)
        self._set_uniform_float(self._image_program, "u_opacity", opacity)
        self._set_uniform_int(self._image_program, "u_flip_y", 1)
        self._set_uniform_vec4(
            self._image_program,
            "u_tint",
            float(tint[0]),
            float(tint[1]),
            float(tint[2]),
            float(tint[3]),
        )
        self._set_uniform_int(self._image_program, "u_tex", 0)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        self._draw_quad()
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glUseProgram(0)

    def _render_bar_texture(self, params: dict[str, Any]) -> None:
        if GL is None or self._bar_texture_program is None:
            return

        frame = params.get("image")
        if frame is None:
            return
        if not isinstance(frame, np.ndarray):
            frame = np.asarray(frame)
        tex_id = self._upload_video_texture(frame)

        bar_center = params.get("bar_center", (0.0, 0.0))
        bar_size = params.get("bar_size", (0.2, 1.8))
        bar_orientation_deg = float(params.get("bar_orientation_deg", 0.0))
        aperture_radius = float(params.get("aperture_radius", 1.0))
        opacity = float(params.get("opacity", 1.0))
        tint = params.get("tint", (1.0, 1.0, 1.0, 1.0))
        if self._fb_width > 0 and self._fb_height > 0:
            square_x_scale = float(self._fb_height) / float(self._fb_width)
        else:
            square_x_scale = 1.0

        GL.glUseProgram(self._bar_texture_program)
        self._set_uniform_vec2(
            self._bar_texture_program, "u_center", 0.0, 0.0
        )
        self._set_uniform_vec2(
            self._bar_texture_program, "u_size", 1.0, 1.0
        )
        self._set_uniform_float(self._bar_texture_program, "u_rotation_deg", 0.0)
        self._set_uniform_vec2(
            self._bar_texture_program,
            "u_bar_center",
            float(bar_center[0]),
            float(bar_center[1]),
        )
        self._set_uniform_vec2(
            self._bar_texture_program,
            "u_bar_size",
            float(bar_size[0]),
            float(bar_size[1]),
        )
        self._set_uniform_float(
            self._bar_texture_program,
            "u_bar_orientation_deg",
            bar_orientation_deg,
        )
        self._set_uniform_float(
            self._bar_texture_program, "u_aperture_radius", aperture_radius
        )
        self._set_uniform_float(self._bar_texture_program, "u_opacity", opacity)
        self._set_uniform_int(self._bar_texture_program, "u_flip_y", 0)
        self._set_uniform_vec4(
            self._bar_texture_program,
            "u_tint",
            float(tint[0]),
            float(tint[1]),
            float(tint[2]),
            float(tint[3]),
        )
        self._set_uniform_float(
            self._bar_texture_program, "u_square_x_scale", square_x_scale
        )
        self._set_uniform_int(self._bar_texture_program, "u_tex", 0)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        self._draw_quad()
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glUseProgram(0)

    def _render_shape(self, params: dict[str, Any]) -> None:
        if GL is None or self._sdf_program is None:
            return

        center = params.get("center", (0.0, 0.0))
        size = params.get("size", (0.2, 0.2))
        coord_space = str(params.get("coord_space", "ndc")).lower()
        if coord_space == "square":
            sx = self._square_x_scale()
            center = (float(center[0]) * sx, float(center[1]))
            size = (float(size[0]) * sx, float(size[1]))
        fill = params.get("fill_color", (1.0, 1.0, 1.0, 1.0))
        if len(fill) == 3:
            fill = (fill[0], fill[1], fill[2], 1.0)
        stroke = max(float(params.get("stroke_width", 0.002)), 1e-6)
        shape = str(params.get("shape", "circle")).lower()
        shape_mode = 1 if shape in {"rect", "rectangle", "box", "square"} else 0
        stroke_color = params.get("stroke_color")
        if stroke_color is not None and len(stroke_color) == 3:
            stroke_color = (
                float(stroke_color[0]),
                float(stroke_color[1]),
                float(stroke_color[2]),
                1.0,
            )

        line_width = params.get("line_width")
        if line_width is None:
            line_width = 0.0
        line_width = float(line_width)
        line_width_px = params.get("line_width_px")
        if line_width_px is not None and self._fb_height > 0:
            ndc_per_px_y = 2.0 / float(self._fb_height)
            local_half_height = max(float(size[1]) * 0.5, 1e-6)
            line_width = (float(line_width_px) * ndc_per_px_y) / local_half_height
        line_width = max(line_width, 0.0)

        draw_fill = float(fill[3]) > 0.0
        draw_stroke = stroke_color is not None and line_width > 0.0
        if not draw_fill and not draw_stroke:
            return

        GL.glUseProgram(self._sdf_program)
        self._set_uniform_vec2(self._sdf_program, "u_center", float(center[0]), float(center[1]))
        self._set_uniform_vec2(self._sdf_program, "u_size", float(size[0]), float(size[1]))
        self._set_uniform_float(self._sdf_program, "u_radius", 1.0)
        self._set_uniform_float(self._sdf_program, "u_stroke", stroke)
        self._set_uniform_int(self._sdf_program, "u_shape_mode", shape_mode)
        self._set_uniform_float(self._sdf_program, "u_line_width", line_width)
        if draw_fill:
            self._set_uniform_int(self._sdf_program, "u_draw_mode", 0)
            self._set_uniform_vec4(
                self._sdf_program,
                "u_color",
                float(fill[0]),
                float(fill[1]),
                float(fill[2]),
                float(fill[3]),
            )
            self._draw_quad()
        if draw_stroke and stroke_color is not None:
            self._set_uniform_int(self._sdf_program, "u_draw_mode", 1)
            self._set_uniform_vec4(
                self._sdf_program,
                "u_color",
                float(stroke_color[0]),
                float(stroke_color[1]),
                float(stroke_color[2]),
                float(stroke_color[3]),
            )
            self._draw_quad()
        GL.glUseProgram(0)

    def _render_line(self, params: dict[str, Any]) -> None:
        if GL is None or self._line_program is None:
            return
        start = params.get("start", (-0.5, 0.0))
        end = params.get("end", (0.5, 0.0))
        coord_space = str(params.get("coord_space", "ndc")).lower()
        if coord_space == "square":
            sx = self._square_x_scale()
            start = (float(start[0]) * sx, float(start[1]))
            end = (float(end[0]) * sx, float(end[1]))
        color = params.get("color", (1.0, 1.0, 1.0, 1.0))
        width = float(params.get("width", 1.0))

        vertices = np.array([start[0], start[1], end[0], end[1]], dtype=np.float32)
        vao = GL.glGenVertexArrays(1)
        vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STREAM_DRAW)

        GL.glUseProgram(self._line_program)
        self._set_uniform_vec4(
            self._line_program,
            "u_color",
            float(color[0]),
            float(color[1]),
            float(color[2]),
            float(color[3]),
        )

        try:
            lw_range = GL.glGetFloatv(GL.GL_ALIASED_LINE_WIDTH_RANGE)
            min_w = float(lw_range[0])
            max_w = float(lw_range[1])
        except Exception:
            min_w = 1.0
            max_w = 1.0
        clamped_width = min(max(width, min_w), max_w)
        GL.glLineWidth(clamped_width)

        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glDrawArrays(GL.GL_LINES, 0, 2)
        GL.glUseProgram(0)
        GL.glBindVertexArray(0)
        GL.glDeleteBuffers(1, [vbo])
        GL.glDeleteVertexArrays(1, [vao])

    def _render_element_array(self, params: dict[str, Any]) -> None:
        centers = params.get("centers", [])
        orientations = params.get("orientations_deg", [])
        phases = params.get("phases", [])
        contrasts = params.get("contrasts", [])
        base = params.get("base_spec", {})

        for i, center in enumerate(centers):
            local = dict(base)
            local["center"] = center
            if i < len(orientations):
                local["orientation_deg"] = orientations[i]
            if i < len(phases):
                local["phase"] = phases[i]
            if i < len(contrasts):
                local["contrast"] = contrasts[i]
            self._render_gabor(local)

    def draw(self, batch: DrawBatch) -> None:
        self._last_batch = batch
        if GL is None:
            return

        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        for command in batch.commands:
            if command.kind == "gabor":
                self._render_gabor(command.params)
            elif command.kind == "shape":
                self._render_shape(command.params)
            elif command.kind == "line":
                self._render_line(command.params)
            elif command.kind == "element_array":
                self._render_element_array(command.params)
            elif command.kind == "image":
                self._render_image(command.params)
            elif command.kind == "video_frame":
                self._render_video_frame(command.params)
            elif command.kind == "bar_texture":
                self._render_bar_texture(command.params)
            elif command.kind in {"text", "video"}:
                # Reserved integration points; rendering paths are backend-specific
                # and can be extended without changing experiment logic.
                pass

    def flip(self, target_ns: int | None = None) -> FlipResult:
        if self.window is None:
            raise RuntimeError("Backend not initialized")

        if target_ns is not None:
            now = time.monotonic_ns()
            wait_ns = target_ns - now
            if wait_ns > 0:
                time.sleep(wait_ns / 1_000_000_000)

        glfw.swap_buffers(self.window)
        glfw.poll_events()

        ts = time.monotonic_ns()
        late_ns = 0
        if target_ns is not None and ts > target_ns:
            late_ns = ts - target_ns

        out = FlipResult(
            timestamp_ns=ts,
            target_ns=target_ns,
            frame_index=self.frame_index,
            late_ns=late_ns,
            dropped_frames=0,
        )
        self.frame_index += 1
        return out

    def set_gamma_lut(self, lut: np.ndarray) -> None:
        self._gamma_lut = np.asarray(lut)
        if self.window is None or glfw is None:
            return

        monitor = glfw.get_window_monitor(self.window)
        if monitor is None:
            return

        if self._gamma_lut.ndim != 2 or self._gamma_lut.shape[1] != 3:
            raise ValueError("lut must have shape (N, 3)")

        if not hasattr(glfw, "set_gamma_ramp"):
            return

        lut_u16 = np.clip(self._gamma_lut, 0, 1)
        lut_u16 = (lut_u16 * 65535).astype(np.uint16)
        ramp = glfw.GammaRamp(lut_u16[:, 0], lut_u16[:, 1], lut_u16[:, 2])
        glfw.set_gamma_ramp(monitor, ramp)

    def poll_input(self) -> list[InputEvent]:
        out = list(self._events)
        self._events.clear()
        return out

    def shutdown(self) -> None:
        if GL is not None:
            if self._gabor_program:
                GL.glDeleteProgram(self._gabor_program)
            if self._sdf_program:
                GL.glDeleteProgram(self._sdf_program)
            if self._image_program:
                GL.glDeleteProgram(self._image_program)
            if self._line_program:
                GL.glDeleteProgram(self._line_program)
            if self._bar_texture_program:
                GL.glDeleteProgram(self._bar_texture_program)
            for tex_id in self._texture_cache.values():
                GL.glDeleteTextures(int(tex_id))
            self._texture_cache.clear()
            if self._video_texture_id is not None:
                GL.glDeleteTextures(int(self._video_texture_id))
                self._video_texture_id = None
                self._video_texture_spec = None
            if self._quad_vbo:
                GL.glDeleteBuffers(1, [self._quad_vbo])
            if self._quad_vao:
                GL.glDeleteVertexArrays(1, [self._quad_vao])

        if self.window is not None and glfw is not None:
            glfw.destroy_window(self.window)
            self.window = None
            glfw.terminate()
