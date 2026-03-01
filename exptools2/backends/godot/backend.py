from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from exptools2.core.contract import request_to_payload
from exptools2.core.logger import RunLogger
from exptools2.core.types import RunEndStatus, RunRequest, StatusKind

from .ipc import UDPChannel, UDPConfig


@dataclass(slots=True)
class GodotConfig:
    executable: str = "godot4"
    scene: str | None = None
    args: list[str] = field(default_factory=list)
    ipc: UDPConfig = field(default_factory=UDPConfig)


def launch_godot(scene: str, args: list[str], executable: str = "godot4") -> subprocess.Popen:
    cmd = [executable, "--path", str(Path(scene).parent), str(scene), *args]
    return subprocess.Popen(cmd)


def _resolve_artifact_path(path_value: str | None, run_output_dir: Path) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = run_output_dir / candidate
    return candidate


def _convert_world_trace_jsonl_to_h5(trace_jsonl: Path, output_h5: Path) -> bool:
    try:
        import h5py
        import numpy as np
    except Exception:
        return False

    if not trace_jsonl.exists() or not trace_jsonl.is_file():
        return False

    rows: list[dict[str, Any]] = []
    with trace_jsonl.open("r", encoding="utf8") as f_in:
        for raw in f_in:
            line = raw.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)

    if not rows:
        return False

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_h5, "w") as h5f:
        h5f.attrs["source"] = str(trace_jsonl)
        h5f.attrs["n_rows"] = len(rows)

        def _dataset_from_key(name: str, dtype: str = "f8") -> None:
            values: list[float] = []
            for row in rows:
                val = row.get(name)
                if isinstance(val, (int, float)):
                    values.append(float(val))
            if values:
                h5f.create_dataset(name, data=np.asarray(values, dtype=dtype), compression=6)

        for key in ("timestamp_ns", "trial_time_s", "x", "y", "z", "yaw_rad", "speed_m_s", "score"):
            _dataset_from_key(key, dtype="f8")

        h5f.create_dataset(
            "trace_json",
            data=json.dumps(rows, separators=(",", ":")).encode("utf8"),
        )
    return True


class GodotRunner:
    def __init__(self, config: GodotConfig) -> None:
        self.config = config

    def run(self, request: RunRequest, logger: RunLogger, timeout_s: float = 600.0) -> RunEndStatus:
        channel = UDPChannel(self.config.ipc)
        proc: subprocess.Popen | None = None
        start_ns = time.monotonic_ns()

        try:
            if self.config.scene is not None:
                proc = launch_godot(
                    scene=self.config.scene,
                    args=self.config.args,
                    executable=self.config.executable,
                )

            run_output_dir = logger.paths.events_tsv.parent
            run_output_dir.mkdir(parents=True, exist_ok=True)

            logger.log_status(StatusKind.RUN_STARTED, start_ns, bids_stem=request.bids_stem)
            run_payload = request_to_payload(request)
            channel.send(
                {
                    "type": "RUN_START",
                    "payload": run_payload,
                    "run_id": request.bids_stem,
                    "condition_row": request.condition_row,
                    "seed": request.seed,
                    "t0_ns": request.t0_ns,
                    "output_dir": str(run_output_dir),
                }
            )

            run_status = RunEndStatus.OK
            deadline = time.monotonic() + timeout_s

            while time.monotonic() < deadline:
                msg = channel.recv()
                if msg is None:
                    if proc is not None and proc.poll() is not None:
                        run_status = RunEndStatus.ERROR
                        break
                    continue

                msg_type = msg.get("type")
                ts = int(msg.get("timestamp_ns", time.monotonic_ns()))

                if msg_type == "EVENT":
                    payload: dict[str, Any] = msg.get("payload", {})
                    logger.log_event(
                        onset_ns=ts,
                        event_type=payload.get("event_type", "event"),
                        trial_nr=payload.get("trial_nr"),
                        phase=payload.get("phase"),
                        response=payload.get("response"),
                        **{k: v for k, v in payload.items() if k not in {"event_type", "trial_nr", "phase", "response"}},
                    )
                    logger.log_status(StatusKind.EVENT, ts, **payload)
                elif msg_type == "SYNC":
                    logger.log_status(StatusKind.SYNC, ts, **msg.get("payload", {}))
                elif msg_type == "RUN_ENDED":
                    payload = msg.get("payload", {})
                    status = payload.get("status", RunEndStatus.OK.value)
                    try:
                        run_status = RunEndStatus(status)
                    except ValueError:
                        run_status = RunEndStatus.ERROR

                    world_h5 = _resolve_artifact_path(payload.get("world_h5_path"), run_output_dir)
                    world_trace_jsonl = _resolve_artifact_path(
                        payload.get("world_trace_jsonl"), run_output_dir
                    )
                    if world_trace_jsonl is not None and world_trace_jsonl.exists():
                        logger.register_artifact(world_trace_jsonl, kind="world_trace_jsonl")
                    if world_h5 is not None and world_h5.exists():
                        logger.register_artifact(world_h5, kind="world_h5")
                    elif world_trace_jsonl is not None:
                        fallback_h5 = run_output_dir / f"{request.bids_stem}_world.h5"
                        if _convert_world_trace_jsonl_to_h5(world_trace_jsonl, fallback_h5):
                            logger.register_artifact(fallback_h5, kind="world_h5")

                    logger.log_status(StatusKind.RUN_ENDED, ts, **payload)
                    break

            end_ns = time.monotonic_ns()
            if run_status != RunEndStatus.OK:
                logger.log_status(
                    StatusKind.RUN_ENDED,
                    end_ns,
                    status=run_status.value,
                    error="Godot run failed or timed out",
                )

            logger.finalize(run_start_ns=start_ns, run_end_ns=end_ns)
            return run_status

        finally:
            channel.close()
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
