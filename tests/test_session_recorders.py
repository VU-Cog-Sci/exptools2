from __future__ import annotations

import json
import time
from pathlib import Path

from exptools2.backends.headless import HeadlessDisplayBackend
from exptools2.core import DisplayConfig, Phase, RunLogger, RunRequest, ScannerTriggerMode, Session
from exptools2.core.trial import ConditionTrial


class DummyRecorder:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.run_started = False
        self.run_ended = False
        self._artifact: Path | None = None

    def start(self, stem: str, output_dir: Path) -> None:
        self.started = True
        self._artifact = output_dir / f"{stem}_dummy.txt"
        self._artifact.write_text("dummy", encoding="utf8")

    def on_run_started(self, run_start_ns: int) -> None:  # noqa: ARG002
        self.run_started = True

    def on_run_ended(self, run_end_ns, status, error) -> None:  # noqa: ANN001, ARG002
        self.run_ended = True

    def stop(self) -> None:
        self.stopped = True

    def artifact_records(self) -> list[tuple[str, Path]]:
        if self._artifact is None:
            return []
        return [("dummy_recorder_artifact", self._artifact)]


def test_session_starts_stops_recorders_and_registers_artifacts(tmp_path: Path) -> None:
    request = RunRequest(
        bids_stem="sub-001_ses-01_task-demo_run-01",
        condition_row={"demo": True},
        seed=1,
        t0_ns=time.monotonic_ns(),
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )
    logger = RunLogger(output_root=tmp_path / "out", bids_stem=request.bids_stem, backend="headless")
    backend = HeadlessDisplayBackend()
    recorder = DummyRecorder()

    session = Session(
        request=request,
        backend=backend,
        logger=logger,
        display_config=DisplayConfig(fullscreen=False, refresh_hz=60.0),
        recorders=[recorder],
    )
    session.add_trial(
        ConditionTrial(
            trial_nr=0,
            phases=[Phase(name="stim", duration_s=0.01)],
            condition_row={"draw_command": {"kind": "shape", "shape": "circle", "size": (0.1, 0.1)}},
        )
    )

    result = session.run()
    assert result.status.value == "ok"
    assert recorder.started is True
    assert recorder.stopped is True
    assert recorder.run_started is True
    assert recorder.run_ended is True

    manifest = json.loads(logger.paths.manifest_json.read_text(encoding="utf8"))
    kinds = [row["kind"] for row in manifest.get("artifacts", [])]
    assert "dummy_recorder_artifact" in kinds

