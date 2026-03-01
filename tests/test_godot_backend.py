from __future__ import annotations

import json
from pathlib import Path

import h5py

from exptools2.backends.godot.backend import (
    _convert_world_trace_jsonl_to_h5,
    _resolve_artifact_path,
)


def test_resolve_artifact_path_relative_and_absolute(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)

    rel = _resolve_artifact_path("trace.jsonl", run_dir)
    assert rel == run_dir / "trace.jsonl"

    abs_path = tmp_path / "x.jsonl"
    abs_resolved = _resolve_artifact_path(str(abs_path), run_dir)
    assert abs_resolved == abs_path

    assert _resolve_artifact_path(None, run_dir) is None


def test_convert_world_trace_jsonl_to_h5(tmp_path: Path) -> None:
    trace = tmp_path / "world_trace.jsonl"
    rows = [
        {
            "timestamp_ns": 1_000,
            "trial_time_s": 0.01,
            "x": 1.0,
            "y": 1.65,
            "z": -0.5,
            "yaw_rad": 0.2,
            "speed_m_s": 3.1,
            "score": 0.0,
        },
        {
            "timestamp_ns": 2_000,
            "trial_time_s": 0.02,
            "x": 1.2,
            "y": 1.65,
            "z": -0.4,
            "yaw_rad": 0.25,
            "speed_m_s": 3.0,
            "score": 1.0,
        },
    ]
    trace.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf8")

    out_h5 = tmp_path / "sub-001_ses-01_task-navarena_run-01_world.h5"
    ok = _convert_world_trace_jsonl_to_h5(trace, out_h5)
    assert ok is True
    assert out_h5.exists()

    with h5py.File(out_h5, "r") as h5f:
        assert int(h5f.attrs["n_rows"]) == 2
        assert h5f["x"].shape[0] == 2
        assert h5f["score"].shape[0] == 2
        payload = json.loads(h5f["trace_json"][()].decode("utf8"))
        assert len(payload) == 2
