"""GLFW/OpenGL example showing gabor + element-array command generation."""

from __future__ import annotations

import time

from exptools2.backends.gl import (
    ElementArraySpec,
    ElementArrayStimulus,
    GaborSpec,
    GaborStimulus,
    GLDisplayBackend,
)
from exptools2.core import DisplayConfig, Phase, RunLogger, RunRequest, ScannerTriggerMode, Session, Trial
from exptools2.core.types import DrawBatch


class VisualTrial(Trial):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gabor = GaborStimulus(
            GaborSpec(center=(0.0, 0.0), size=(0.35, 0.35), orientation_deg=45, spatial_freq=3)
        )
        self.array = ElementArrayStimulus(ElementArraySpec(n_elements=48, seed=7))

    def draw(self, phase_index: int, now_ns: int) -> DrawBatch:
        batch = DrawBatch()
        if phase_index == 0:
            self.gabor.update({"phase": (now_ns % 1_000_000_000) / 1_000_000_000 * 6.28318})
            self.gabor.enqueue(batch)
        else:
            self.array.enqueue(batch)
        return batch


def main() -> None:
    request = RunRequest(
        bids_stem="sub-001_ses-01_task-glvisual_run-01",
        condition_row={"task": "gl_visual"},
        seed=7,
        t0_ns=time.monotonic_ns(),
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )

    logger = RunLogger(output_root="logs", bids_stem=request.bids_stem, backend="gl")

    session = Session(
        request=request,
        backend=GLDisplayBackend(),
        logger=logger,
        display_config=DisplayConfig(width=1280, height=720, fullscreen=False, refresh_hz=60.0),
    )
    session.add_trial(
        VisualTrial(
            trial_nr=0,
            phases=[Phase(name="gabor", duration_s=2.0), Phase(name="array", duration_s=2.0)],
        )
    )

    result = session.run()
    print(result)


if __name__ == "__main__":
    main()
