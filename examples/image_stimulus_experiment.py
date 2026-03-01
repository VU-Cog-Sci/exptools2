"""GL still-image stimulus example rendered with a texture shader."""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np

from exptools2.backends.gl import GLDisplayBackend, ImageSpec, ImageStimulus
from exptools2.core import DisplayConfig, Phase, RunLogger, RunRequest, ScannerTriggerMode, Session, Trial
from exptools2.core.types import DrawBatch

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


class ImageTrial(Trial):
    def __init__(self, *args, image_path: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.image = ImageStimulus(
            ImageSpec(
                source=image_path,
                center=(0.0, 0.0),
                size=(1.0, 1.0),
                rotation_deg=0.0,
                opacity=1.0,
            )
        )

    def draw(self, phase_index: int, now_ns: int) -> DrawBatch:
        batch = DrawBatch()
        # Slow rotation to demonstrate uniform updates.
        angle = ((now_ns // 10_000_000) % 360)
        self.image.update({"rotation_deg": float(angle)})
        self.image.enqueue(batch)
        return batch


def _create_demo_image(path: Path) -> None:
    if Image is None:
        raise RuntimeError("Pillow is required to generate the demo image")

    w, h = 512, 512
    y, x = np.mgrid[0:h, 0:w]
    r = np.clip((x / w) * 255, 0, 255).astype(np.uint8)
    g = np.clip((y / h) * 255, 0, 255).astype(np.uint8)
    b = np.full((h, w), 128, dtype=np.uint8)
    a = np.full((h, w), 255, dtype=np.uint8)
    img = np.dstack([r, g, b, a])
    Image.fromarray(img, mode="RGBA").save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=None, help="Path to image file")
    args = parser.parse_args()

    tmpdir = tempfile.TemporaryDirectory()
    if args.image is None:
        image_path = Path(tmpdir.name) / "demo_image.png"
        _create_demo_image(image_path)
    else:
        image_path = args.image

    request = RunRequest(
        bids_stem="sub-001_ses-01_task-image_run-01",
        condition_row={"task": "image"},
        seed=11,
        t0_ns=time.monotonic_ns(),
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )

    logger = RunLogger(output_root="logs", bids_stem=request.bids_stem, backend="gl")
    session = Session(
        request=request,
        backend=GLDisplayBackend(),
        logger=logger,
        display_config=DisplayConfig(width=1280, height=720, fullscreen=False, refresh_hz=60),
    )

    session.add_trial(
        ImageTrial(
            trial_nr=0,
            phases=[Phase(name="image", duration_s=4.0)],
            image_path=str(image_path),
        )
    )

    print(session.run())


if __name__ == "__main__":
    main()
