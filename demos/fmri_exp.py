"""Example fMRI-style configuration run with trigger mode enabled."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from exptools2.runner.run import run_from_config


if __name__ == "__main__":
    cfg = {
        "run": {
            "sub": "001",
            "ses": "01",
            "task": "fmri",
            "run": "01",
            "backend": "headless",
            "output_root": "logs",
            "scanner_trigger_mode": {"mode": "key", "params": {"key": "t"}},
        },
        "conditions": {"rows": [{"phase_name": "stim", "duration_s": 0.5}]},
    }

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(yaml.safe_dump(cfg), encoding="utf8")
        print(run_from_config(path))
