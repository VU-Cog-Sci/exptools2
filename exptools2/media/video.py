from __future__ import annotations

import queue
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from exptools2.core.types import DrawBatch


@dataclass(slots=True)
class VideoStatus:
    source: str | None = None
    decode_mode: str = "sw"
    decoded_frames: int = 0
    presented_frames: int = 0
    dropped_frames: int = 0
    repeated_frames: int = 0
    started_ns: int | None = None


class VideoPlayer(Protocol):
    def open(self, path: str, hwaccel: str = "auto") -> None:
        ...

    def schedule(self, start_ns: int) -> None:
        ...

    def enqueue(self, batch: DrawBatch, now_ns: int) -> None:
        ...

    def status(self) -> VideoStatus:
        ...

    def close(self) -> None:
        ...


@dataclass(slots=True)
class _DecodedFrame:
    pts_ns: int
    frame_index: int
    image: np.ndarray


class PyAVVideoPlayer:
    def __init__(self, queue_size: int = 12) -> None:
        self.queue_size = queue_size
        self._container: Any = None
        self._stream: Any = None
        self._q: queue.Queue[_DecodedFrame] = queue.Queue(maxsize=queue_size)
        self._decoder_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_frame: _DecodedFrame | None = None
        self._scheduled_ns: int | None = None
        self._status = VideoStatus()

    def open(self, path: str, hwaccel: str = "auto") -> None:
        try:
            import av
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("PyAV is required for video playback") from exc

        self._status = VideoStatus(source=str(Path(path)), decode_mode="sw")
        opts: dict[str, str] = {}
        if hwaccel != "off":
            if hwaccel == "auto":
                # FFmpeg determines best available acceleration.
                opts["hwaccel"] = "auto"
            else:
                opts["hwaccel"] = hwaccel
            self._status.decode_mode = "hw"

        try:
            self._container = av.open(path, options=opts)
        except Exception:
            self._container = av.open(path)
            self._status.decode_mode = "sw"

        self._stream = self._container.streams.video[0]
        self._stop.clear()
        self._decoder_thread = threading.Thread(target=self._decode_loop, daemon=True)
        self._decoder_thread.start()

    def _decode_loop(self) -> None:
        if self._container is None or self._stream is None:
            return

        tb = float(self._stream.time_base) if self._stream.time_base else 1 / 30
        idx = 0
        for frame in self._container.decode(self._stream):
            if self._stop.is_set():
                break
            pts = frame.pts if frame.pts is not None else idx
            pts_ns = int(pts * tb * 1_000_000_000)
            rgb = frame.to_ndarray(format="rgb24")
            decoded = _DecodedFrame(pts_ns=pts_ns, frame_index=idx, image=rgb)
            idx += 1
            self._status.decoded_frames = idx

            while not self._stop.is_set():
                try:
                    self._q.put(decoded, timeout=0.05)
                    break
                except queue.Full:
                    pass

    def schedule(self, start_ns: int) -> None:
        self._scheduled_ns = start_ns
        self._status.started_ns = start_ns

    def enqueue(self, batch: DrawBatch, now_ns: int) -> None:
        if self._scheduled_ns is None:
            self._scheduled_ns = now_ns

        elapsed_ns = max(0, now_ns - self._scheduled_ns)
        frame_to_show = self._last_frame

        while True:
            try:
                candidate = self._q.get_nowait()
            except queue.Empty:
                break

            if candidate.pts_ns <= elapsed_ns:
                frame_to_show = candidate
            else:
                # Keep next frame for future display.
                try:
                    self._q.put_nowait(candidate)
                except queue.Full:
                    self._status.dropped_frames += 1
                break

        if frame_to_show is None:
            if self._last_frame is not None:
                self._status.repeated_frames += 1
                frame_to_show = self._last_frame
            else:
                return

        self._last_frame = frame_to_show
        self._status.presented_frames += 1
        batch.add(
            "video_frame",
            frame_index=frame_to_show.frame_index,
            pts_ns=frame_to_show.pts_ns,
            image=frame_to_show.image,
            decode_mode=self._status.decode_mode,
        )

    def status(self) -> VideoStatus:
        return VideoStatus(**asdict(self._status))

    def close(self) -> None:
        self._stop.set()
        if self._decoder_thread is not None:
            self._decoder_thread.join(timeout=1.0)
        if self._container is not None:
            self._container.close()
        self._container = None
        self._stream = None
