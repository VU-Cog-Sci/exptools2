from __future__ import annotations

import json
from pathlib import Path

from exptools2.core.types import RunEndStatus
from exptools2.triggerio import TriggerIORecorder, TriggerIORecorderConfig


def test_triggerio_dry_run_writes_artifacts(tmp_path: Path) -> None:
    cfg = TriggerIORecorderConfig.from_mapping(
        {
            "enabled": True,
            "mode": "parallel",
            "dry_run": True,
            "pulse_width_ms": 0.0,
            "codes": {"run_started": 5, "run_ended_ok": 250, "response": 20},
            "phase_codes": {"stim": 2},
        }
    )
    rec = TriggerIORecorder(cfg)
    rec.start(stem="sub-001_ses-01_task-demo_run-01", output_dir=tmp_path)
    rec.on_run_started(1)
    rec.on_phase_started(0, 0, "stim", 1, 2)
    rec.on_input("a", 3, "response", 0, 0)
    rec.on_run_ended(4, RunEndStatus.OK, None)
    rec.stop()

    records = rec.artifact_records()
    kinds = [k for k, _ in records]
    assert "trigger_io_events" in kinds
    assert "trigger_io_metadata" in kinds

    meta_path = [p for k, p in records if k == "trigger_io_metadata"][0]
    meta = json.loads(meta_path.read_text(encoding="utf8"))
    assert meta["dry_run"] is True
    assert meta["mode"] == "parallel"
    assert meta["n_emitted"] >= 4


def test_triggerio_parse_hex_address() -> None:
    cfg = TriggerIORecorderConfig.from_mapping(
        {"enabled": True, "parallel": {"address": "0x0378"}, "dry_run": True}
    )
    assert int(cfg.parallel.address) == 0x0378

