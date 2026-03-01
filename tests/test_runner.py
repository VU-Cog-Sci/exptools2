from pathlib import Path

import json
import pytest

from exptools2.runner.run import _monitor_index_from_display_cfg, run_from_config


def test_run_from_config_headless(tmp_path: Path) -> None:
    cfg = {
        "run": {
            "backend": "headless",
            "sub": "001",
            "ses": "01",
            "task": "demo",
            "run": "01",
            "output_root": str(tmp_path / "out"),
            "seed": 7,
        },
        "conditions": {"rows": [{"phase_name": "stim", "duration_s": 0.01}]},
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf8")

    result = run_from_config(cfg_path)
    assert result["status"] == "ok"

    out = Path(result["output_root"]) / "sub-001" / "ses-01" / "beh"
    assert (out / "sub-001_ses-01_task-demo_run-01_events.tsv").exists()


def test_run_from_config_rejects_eyelink_with_headless_backend(tmp_path: Path) -> None:
    cfg = {
        "run": {
            "backend": "headless",
            "sub": "001",
            "ses": "01",
            "task": "demo",
            "run": "01",
            "output_root": str(tmp_path / "out"),
            "seed": 7,
        },
        "eyelink": {"enabled": True},
        "conditions": {"rows": [{"phase_name": "stim", "duration_s": 0.01}]},
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf8")

    with pytest.raises(ValueError, match="requires backend: gl"):
        run_from_config(cfg_path)


def test_run_from_config_with_trigger_io_dry_run(tmp_path: Path) -> None:
    cfg = {
        "run": {
            "backend": "headless",
            "sub": "001",
            "ses": "01",
            "task": "demo",
            "run": "01",
            "output_root": str(tmp_path / "out"),
            "seed": 7,
        },
        "trigger_io": {
            "enabled": True,
            "mode": "parallel",
            "dry_run": True,
            "phase_codes": {"stim": 2},
        },
        "conditions": {"rows": [{"phase_name": "stim", "duration_s": 0.01}]},
    }
    cfg_path = tmp_path / "cfg_trigger.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf8")

    result = run_from_config(cfg_path)
    assert result["status"] == "ok"

    out = Path(result["output_root"]) / "sub-001" / "ses-01" / "beh"
    assert (out / "sub-001_ses-01_task-demo_run-01_triggers.json").exists()
    assert (out / "sub-001_ses-01_task-demo_run-01_triggers.jsonl").exists()


def test_monitor_index_parser() -> None:
    assert _monitor_index_from_display_cfg({"monitor_index": 2}) == 2
    assert _monitor_index_from_display_cfg({"monitor_name": "index:3"}) == 3
    assert _monitor_index_from_display_cfg({"monitor_name": "1"}) == 1
    assert _monitor_index_from_display_cfg({"monitor_name": "primary"}) is None
