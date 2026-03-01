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


if __name__ == "__main__":
    request = RunRequest(
        bids_stem="sub-001_ses-01_task-demo_run-01",
        condition_row={"n_rows": 2},
        seed=42,
        t0_ns=time.monotonic_ns(),
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )

    logger = RunLogger(output_root="logs", bids_stem=request.bids_stem, backend="headless")
    backend = HeadlessDisplayBackend()
    session = Session(
        request=request,
        backend=backend,
        logger=logger,
        display_config=DisplayConfig(fullscreen=False, refresh_hz=60),
    )

    session.add_trials(
        [
            ConditionTrial(trial_nr=0, phases=[Phase(name="stim", duration_s=0.25)]),
            ConditionTrial(trial_nr=1, phases=[Phase(name="stim", duration_s=0.25)]),
        ]
    )

    result = session.run()
    print(result)
