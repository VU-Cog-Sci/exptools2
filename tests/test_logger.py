import time
from pathlib import Path

from exptools2.core.logger import RunLogger
from exptools2.core.types import StatusKind


def test_logger_writes_required_artifacts(tmp_path: Path) -> None:
    logger = RunLogger(output_root=tmp_path, bids_stem="sub-001_ses-01_task-roam_run-02", backend="headless")
    t0 = time.monotonic_ns()
    logger.log_status(StatusKind.RUN_STARTED, t0)
    logger.log_event(onset_ns=t0, event_type="stim", trial_nr=0, phase=0, duration_ns=1_000_000)
    logger.finalize(run_start_ns=t0, run_end_ns=t0 + 2_000_000)

    paths = logger.paths
    assert paths.events_tsv.exists()
    assert paths.events_json.exists()
    assert paths.log_h5.exists()
    assert paths.manifest_json.exists()
