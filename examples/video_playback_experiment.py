"""Video playback example that renders into a GLFW/OpenGL window."""

from __future__ import annotations

import argparse
import time

from exptools2.backends.gl import GLDisplayBackend
from exptools2.core import DisplayConfig
from exptools2.core.types import DrawBatch
from exptools2.media import PyAVVideoPlayer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to a video file")
    parser.add_argument("--duration", type=float, default=10.0, help="Playback duration in seconds")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--refresh-hz", type=float, default=60.0)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--hwaccel", default="auto", choices=["auto", "off", "videotoolbox", "vaapi", "nvdec"])
    args = parser.parse_args()

    player = PyAVVideoPlayer(queue_size=16)
    player.open(args.video, hwaccel=args.hwaccel)
    backend = GLDisplayBackend()
    backend.initialize(
        DisplayConfig(
            width=args.width,
            height=args.height,
            refresh_hz=args.refresh_hz,
            fullscreen=args.fullscreen,
            title="exptools2 video example",
        )
    )

    start = time.monotonic_ns() + 100_000_000
    player.schedule(start)

    frame_step_ns = int(1_000_000_000 / max(args.refresh_hz, 1.0))
    next_flip = start
    deadline = start + int(args.duration * 1_000_000_000)

    try:
        while time.monotonic_ns() < deadline:
            now_ns = time.monotonic_ns()
            batch = DrawBatch()
            player.enqueue(batch, now_ns=now_ns)

            # Leave escape hatch keys for manual stop.
            for ev in backend.poll_input():
                if ev.key in {"q", "Q", "256"}:
                    deadline = 0
                    break

            backend.draw(batch)
            backend.flip(target_ns=next_flip)
            next_flip += frame_step_ns
    finally:
        print("Video status:", player.status())
        player.close()
        backend.shutdown()


if __name__ == "__main__":
    main()
