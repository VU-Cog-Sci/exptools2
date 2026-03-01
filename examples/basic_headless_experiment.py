"""Minimal contract-compliant experiment run using the headless backend."""

from __future__ import annotations

import time

from exptools2.backends.headless import HeadlessDisplayBackend
from exptools2.core import (
    ConditionTrial,
    DisplayConfig,
    Phase,
    RunLogger,
    RunRequest,
    ScannerTriggerMode,
    Session,
)


def main() -> None:
    request = RunRequest(
        bids_stem="sub-001_ses-01_task-basic_run-01",
        condition_row={"task": "basic_headless"},
        seed=123,
        t0_ns=time.monotonic_ns(),
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )

    logger = RunLogger(
        output_root="logs",
        bids_stem=request.bids_stem,
        backend="headless",
    )

    session = Session(
        request=request,
        backend=HeadlessDisplayBackend(),
        logger=logger,
        display_config=DisplayConfig(fullscreen=False, refresh_hz=60.0),
    )

    session.add_trials(
        [
            ConditionTrial(
                trial_nr=0,
                phases=[
                    Phase(name="fix", duration_s=0.50),
                    Phase(name="stim", duration_s=0.50),
                ],
                condition_row={
                    "draw_command": {
                        "kind": "shape",
                        "shape": "circle",
                        "center": (0.0, 0.0),
                        "size": (0.10, 0.10),
                    }
                },
            )
        ]
    )

    result = session.run()
    print(result)


if __name__ == "__main__":
    main()
