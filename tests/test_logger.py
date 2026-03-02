import time
from pathlib import Path

import h5py

from exptools2.core.logger import RunLogger
from exptools2.core.types import StatusKind


def test_logger_writes_required_artifacts(tmp_path: Path) -> None:
    logger = RunLogger(output_root=tmp_path, bids_stem="sub-001_ses-01_task-roam_run-02", backend="headless")
    t0 = time.monotonic_ns()
    logger.log_status(StatusKind.RUN_STARTED, t0)
    logger.log_event(onset_ns=t0, event_type="stim", trial_nr=0, phase=0, duration_ns=1_000_000)
    logger.log_event(onset_ns=t0 + 500_000, event_type="response", trial_nr=0, phase=0, response="space")
    logger.log_flip(
        timestamp_ns=t0,
        target_ns=t0,
        frame_index=0,
        late_ns=0,
        dropped_frames=0,
        trial_nr=0,
        phase=0,
    )
    logger.log_flip(
        timestamp_ns=t0 + 16_000_000,
        target_ns=t0 + 16_666_667,
        frame_index=1,
        late_ns=1_000_000,
        dropped_frames=0,
        trial_nr=0,
        phase=0,
    )
    dash = logger.write_timing_dashboard(run_start_ns=t0, run_end_ns=t0 + 2_000_000, refresh_hz=60.0)
    logger.finalize(run_start_ns=t0, run_end_ns=t0 + 2_000_000)

    paths = logger.paths
    assert paths.events_tsv.exists()
    assert paths.events_json.exists()
    assert paths.log_h5.exists()
    assert paths.manifest_json.exists()

    with h5py.File(paths.log_h5, "r") as h5f:
        assert "flips" in h5f
        assert "inputs" in h5f
        assert "payload_json" in h5f
        assert h5f["flips/timestamp_ns"].shape[0] == 2
        assert h5f["flips/interval_ms"].shape[0] == 2
        assert h5f["inputs/onset_ns"].shape[0] == 1

    if dash is not None:
        assert dash.exists()
