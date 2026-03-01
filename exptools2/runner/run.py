from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Any

from exptools2.backends.godot import GodotConfig, GodotRunner, UDPConfig
from exptools2.backends.headless import HeadlessDisplayBackend
from exptools2.core import (
    ConditionTrial,
    ConditionsLoader,
    DisplayConfig,
    Phase,
    RunLogger,
    RunRequest,
    ScannerTriggerMode,
    Session,
    make_bids_stem,
)


def _float(value: Any, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _int(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _monitor_index_from_display_cfg(display_cfg: dict[str, Any]) -> int | None:
    explicit = display_cfg.get("monitor_index")
    if explicit is not None:
        return int(explicit)

    name = str(display_cfg.get("monitor_name", "") or "").strip().lower()
    if name.startswith("index:"):
        token = name.split(":", 1)[1].strip()
        if token and (token.isdigit() or (token.startswith("-") and token[1:].isdigit())):
            return int(token)
    if name and (name.isdigit() or (name.startswith("-") and name[1:].isdigit())):
        return int(name)
    return None


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf8"))

    try:
        import yaml
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PyYAML is required to parse YAML configs. Install 'pyyaml' or use a .json config."
        ) from exc

    with path.open("r", encoding="utf8") as f_in:
        return yaml.safe_load(f_in)


def build_trials(rows: list[dict[str, Any]]) -> list[ConditionTrial]:
    trials: list[ConditionTrial] = []
    for idx, row in enumerate(rows):
        row = dict(row)
        if "draw_command" not in row and "draw_kind" in row:
            draw = {"kind": row.pop("draw_kind")}
            for key, value in list(row.items()):
                if key in {"phase_name", "event_type", "duration_s", "duration", "isi_s"}:
                    continue
                draw[key] = value
            row["draw_command"] = draw

        phases = [
            Phase(
                name=str(row.get("phase_name", row.get("event_type", "stim"))),
                duration_s=_float(row.get("duration_s", row.get("duration", 1.0)), 1.0),
            )
        ]
        if "isi_s" in row:
            phases.append(Phase(name="ISI", duration_s=_float(row.get("isi_s"), 0.0)))

        trials.append(
            ConditionTrial(
                trial_nr=idx,
                phases=phases,
                condition_row=row,
                parameters={"condition_index": idx},
            )
        )
    return trials


def run_from_config(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path)
    cfg = load_config(cfg_path)
    run_cfg = cfg.get("run", {})

    stem = run_cfg.get("bids_stem")
    if stem is None:
        stem = make_bids_stem(
            sub=str(run_cfg.get("sub", "001")),
            ses=str(run_cfg.get("ses", "01")),
            task=str(run_cfg.get("task", "task")),
            run=str(run_cfg.get("run", "01")),
        )

    backend_name = str(run_cfg.get("backend", "gl")).lower()
    output_root = Path(run_cfg.get("output_root", "logs"))
    contract_version = str(run_cfg.get("contract_version", "1.1"))

    condition_path = cfg.get("conditions", {}).get("path")
    if condition_path:
        rows = ConditionsLoader.load(condition_path, key=cfg.get("conditions", {}).get("key"))
    else:
        rows = list(cfg.get("conditions", {}).get("rows", []))

    if not rows:
        rows = [{"phase_name": "stim", "duration_s": 1.0}]

    scanner_cfg = run_cfg.get("scanner_trigger_mode", {})
    scanner_mode = ScannerTriggerMode(
        mode=str(scanner_cfg.get("mode", "none")),
        params=dict(scanner_cfg.get("params", {})),
    )

    request_condition_row = dict(run_cfg.get("condition_row", {}))
    if not request_condition_row:
        request_condition_row = dict(rows[0]) if rows else {"n_rows": 0}
    request_condition_row.setdefault("n_rows", len(rows))

    request = RunRequest(
        bids_stem=stem,
        condition_row=request_condition_row,
        seed=_int(run_cfg.get("seed"), 1),
        t0_ns=_int(run_cfg.get("t0_ns"), time.monotonic_ns()),
        scanner_trigger_mode=scanner_mode,
        contract_version=contract_version,
    )

    logger = RunLogger(
        output_root=output_root,
        bids_stem=stem,
        contract_version=contract_version,
        backend=backend_name,
        metadata={"config_path": str(path)},
    )

    if backend_name == "godot":
        godot_cfg = cfg.get("godot", {})
        display_cfg = cfg.get("display", {})
        scene = godot_cfg.get("scene")
        if scene is not None:
            scene_path = Path(str(scene))
            if not scene_path.is_absolute():
                scene_path = (cfg_path.parent / scene_path).resolve()
            scene = str(scene_path)

        godot_args = list(godot_cfg.get("args", []))
        monitor_index = _monitor_index_from_display_cfg(dict(display_cfg))
        has_screen_arg = any(str(arg) == "--screen" for arg in godot_args)
        if monitor_index is not None and (not has_screen_arg):
            godot_args.extend(["--screen", str(monitor_index)])

        runner = GodotRunner(
            GodotConfig(
                executable=str(godot_cfg.get("executable", "godot4")),
                scene=scene,
                args=godot_args,
                ipc=UDPConfig(
                    host=str(godot_cfg.get("host", "127.0.0.1")),
                    port=_int(godot_cfg.get("port"), 5005),
                    timeout_s=_float(godot_cfg.get("timeout_s"), 0.1),
                ),
            )
        )
        status = runner.run(request=request, logger=logger, timeout_s=_float(godot_cfg.get("run_timeout_s"), 600.0))
        return {
            "backend": backend_name,
            "status": status.value,
            "bids_stem": stem,
            "output_root": str(output_root),
        }

    if backend_name not in {"gl", "headless"}:
        raise ValueError(f"Unsupported backend: {backend_name}")

    if backend_name == "headless":
        backend = HeadlessDisplayBackend()
    else:
        from exptools2.backends.gl import GLDisplayBackend

        backend = GLDisplayBackend()

    recorders: list[Any] = []
    eyelink_cfg = cfg.get("eyelink", {})
    if bool(eyelink_cfg.get("enabled", False)):
        if backend_name != "gl":
            raise ValueError("EyeLink integration currently requires backend: gl")
        from exptools2.eyelink import EyeLinkRecorder, EyeLinkRecorderConfig

        recorders.append(
            EyeLinkRecorder(
                backend=backend,
                config=EyeLinkRecorderConfig.from_mapping(dict(eyelink_cfg)),
            )
        )

    trigger_cfg = cfg.get("trigger_io", {})
    if bool(trigger_cfg.get("enabled", False)):
        from exptools2.triggerio import TriggerIORecorder, TriggerIORecorderConfig

        recorders.append(TriggerIORecorder(TriggerIORecorderConfig.from_mapping(dict(trigger_cfg))))

    prelude_cfg = dict(cfg.get("prelude", {}))
    if backend_name != "headless":
        prelude_cfg.setdefault("enabled", True)
        scanner_key = scanner_mode.params.get("key", "t")

        instruction_cfg = dict(prelude_cfg.get("instruction", {}))
        instruction_cfg.setdefault(
            "text",
            prelude_cfg.get("instruction_text", "Instruction stage\n\nPrepare for the run."),
        )
        if "instruction_continue_key" in prelude_cfg:
            instruction_cfg.setdefault("continue_keys", prelude_cfg.get("instruction_continue_key"))
        if "instruction_duration_s" in prelude_cfg:
            instruction_cfg.setdefault("timeout_s", prelude_cfg.get("instruction_duration_s"))
        prelude_cfg.setdefault("instruction_duration_s", 2.0)
        instruction_cfg.setdefault("timeout_s", prelude_cfg.get("instruction_duration_s"))
        prelude_cfg["instruction"] = instruction_cfg

        fixation_wait_cfg = dict(prelude_cfg.get("fixation_wait", {}))
        fixation_wait_cfg.setdefault("enabled", prelude_cfg.get("show_fixation_wait", True))
        start_key = prelude_cfg.get("start_key", scanner_key if scanner_key else "t")
        fixation_wait_cfg.setdefault("start_keys", start_key)
        prelude_cfg["fixation_wait"] = fixation_wait_cfg

    display_cfg = cfg.get("display", {})
    session = Session(
        request=request,
        backend=backend,
        logger=logger,
        display_config=DisplayConfig(
            width=_int(display_cfg.get("width"), 1440),
            height=_int(display_cfg.get("height"), 900),
            refresh_hz=_float(display_cfg.get("refresh_hz"), 60.0),
            fullscreen=bool(display_cfg.get("fullscreen", True)),
            hide_cursor=bool(display_cfg.get("hide_cursor", True)),
            title=str(display_cfg.get("title", "exptools2")),
            vsync=bool(display_cfg.get("vsync", True)),
            monitor_name=str(display_cfg.get("monitor_name", "default")),
            monitor_index=_opt_int(display_cfg.get("monitor_index")),
        ),
        recorders=recorders,
        prelude=prelude_cfg,
    )

    session.add_trials(build_trials(rows))
    result = session.run()

    return {
        "backend": backend_name,
        "status": result.status.value,
        "bids_stem": stem,
        "output_root": str(output_root),
        "run_start_ns": result.run_start_ns,
        "run_end_ns": result.run_end_ns,
    }
