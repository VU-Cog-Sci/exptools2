from __future__ import annotations

import time

from exptools2.backends.headless import HeadlessDisplayBackend
from exptools2.core import ConditionTrial, DisplayConfig, Phase, RunLogger, RunRequest, ScannerTriggerMode, Session

request = RunRequest(
    bids_stem="sub-001_ses-01_task-test_run-01",
    condition_row={"n_rows": 1},
    seed=1,
    t0_ns=time.monotonic_ns(),
    scanner_trigger_mode=ScannerTriggerMode(mode="none"),
)

backend = HeadlessDisplayBackend()
logger = RunLogger(output_root="logs", bids_stem=request.bids_stem, backend="headless")
session = Session(request=request, backend=backend, logger=logger, display_config=DisplayConfig(fullscreen=False))
session.add_trial(ConditionTrial(trial_nr=0, phases=[Phase(name="stim", duration_s=0.01)]))
result = session.run()
print(result)
