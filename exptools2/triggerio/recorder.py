from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from exptools2.core.types import RunEndStatus


def _parse_int(value: Any, default: int) -> int:
    if value is None:
        return int(default)
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


def _to_int_map(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in payload.items():
        if value is None:
            continue
        out[str(key)] = _parse_int(value, 0)
    return out


@dataclass(slots=True)
class ParallelPortConfig:
    address: int = 0x0378
    constructor: str = "parallel.Parallel"


@dataclass(slots=True)
class SerialPortConfig:
    port: str | None = None
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
    timeout_s: float = 0.0
    write_mode: str = "byte"  # byte | ascii
    line_ending: str = "\n"


@dataclass(slots=True)
class TriggerIORecorderConfig:
    enabled: bool = False
    mode: str = "parallel"  # parallel | serial | both
    dry_run: bool = False
    pulse_width_ms: float = 1.0
    auto_zero: bool = True
    parallel: ParallelPortConfig = field(default_factory=ParallelPortConfig)
    serial: SerialPortConfig = field(default_factory=SerialPortConfig)
    codes: dict[str, int] = field(
        default_factory=lambda: {
            "run_started": 5,
            "run_ended_ok": 250,
            "run_ended_aborted": 251,
            "run_ended_error": 252,
            "abort": 255,
            "pulse": 10,
            "response": 20,
        }
    )
    phase_codes: dict[str, int] = field(default_factory=dict)
    key_codes: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "TriggerIORecorderConfig":
        parallel_cfg = dict(payload.get("parallel", {}))
        serial_cfg = dict(payload.get("serial", {}))
        return cls(
            enabled=bool(payload.get("enabled", False)),
            mode=str(payload.get("mode", "parallel")).lower(),
            dry_run=bool(payload.get("dry_run", False)),
            pulse_width_ms=float(payload.get("pulse_width_ms", 1.0)),
            auto_zero=bool(payload.get("auto_zero", True)),
            parallel=ParallelPortConfig(
                address=_parse_int(parallel_cfg.get("address"), 0x0378),
                constructor=str(parallel_cfg.get("constructor", "parallel.Parallel")),
            ),
            serial=SerialPortConfig(
                port=serial_cfg.get("port"),
                baudrate=_parse_int(serial_cfg.get("baudrate"), 115200),
                bytesize=_parse_int(serial_cfg.get("bytesize"), 8),
                parity=str(serial_cfg.get("parity", "N")),
                stopbits=float(serial_cfg.get("stopbits", 1.0)),
                timeout_s=float(serial_cfg.get("timeout_s", 0.0)),
                write_mode=str(serial_cfg.get("write_mode", "byte")).lower(),
                line_ending=str(serial_cfg.get("line_ending", "\n")),
            ),
            codes=_to_int_map(payload.get("codes"))
            or {
                "run_started": 5,
                "run_ended_ok": 250,
                "run_ended_aborted": 251,
                "run_ended_error": 252,
                "abort": 255,
                "pulse": 10,
                "response": 20,
            },
            phase_codes=_to_int_map(payload.get("phase_codes")),
            key_codes=_to_int_map(payload.get("key_codes")),
        )


class TriggerIORecorder:
    """Optional EEG/fMRI trigger output recorder for parallel/serial ports."""

    def __init__(self, config: TriggerIORecorderConfig | None = None) -> None:
        self.config = config or TriggerIORecorderConfig()
        self._parallel = None
        self._serial = None
        self._stem: str | None = None
        self._output_dir: Path | None = None
        self._trace_path: Path | None = None
        self._meta_path: Path | None = None
        self._records: list[dict[str, Any]] = []

    def _mode_uses_parallel(self) -> bool:
        return self.config.mode in {"parallel", "both"}

    def _mode_uses_serial(self) -> bool:
        return self.config.mode in {"serial", "both"}

    def _open_parallel(self) -> None:
        import parallel  # type: ignore

        addr = int(self.config.parallel.address)
        candidates = [
            lambda: parallel.Parallel(addr),
            lambda: parallel.Parallel(address=addr),
            lambda: parallel.Parallel(port=addr),
            lambda: parallel.Parallel(),
        ]
        last_error: Exception | None = None
        for fn in candidates:
            try:
                port = fn()
                self._parallel = port
                self._parallel_write(0)
                return
            except Exception as exc:  # pragma: no cover - hardware/backend specific
                last_error = exc

        if last_error is not None:
            raise RuntimeError(f"Could not initialize parallel port: {last_error}") from last_error
        raise RuntimeError("Could not initialize parallel port")

    def _open_serial(self) -> None:
        if not self.config.serial.port:
            raise RuntimeError("serial.port must be configured when trigger_io mode uses serial")

        import serial  # type: ignore

        parity_value = {
            "N": getattr(serial, "PARITY_NONE", "N"),
            "E": getattr(serial, "PARITY_EVEN", "E"),
            "O": getattr(serial, "PARITY_ODD", "O"),
        }.get(self.config.serial.parity.upper(), getattr(serial, "PARITY_NONE", "N"))

        stopbits_value = {
            1.0: getattr(serial, "STOPBITS_ONE", 1),
            1.5: getattr(serial, "STOPBITS_ONE_POINT_FIVE", 1.5),
            2.0: getattr(serial, "STOPBITS_TWO", 2),
        }.get(float(self.config.serial.stopbits), getattr(serial, "STOPBITS_ONE", 1))

        self._serial = serial.Serial(
            port=str(self.config.serial.port),
            baudrate=int(self.config.serial.baudrate),
            bytesize=int(self.config.serial.bytesize),
            parity=parity_value,
            stopbits=stopbits_value,
            timeout=float(self.config.serial.timeout_s),
            write_timeout=float(self.config.serial.timeout_s),
        )

    def _parallel_write(self, value: int) -> None:
        if self._parallel is None:
            return
        if hasattr(self._parallel, "setData"):
            self._parallel.setData(int(value))
            return
        if hasattr(self._parallel, "set_data"):
            self._parallel.set_data(int(value))
            return
        raise RuntimeError("Parallel port backend does not expose setData/set_data")

    def _serial_write(self, value: int) -> None:
        if self._serial is None:
            return
        v = int(max(0, min(int(value), 255)))
        if self.config.serial.write_mode == "ascii":
            msg = f"{v}{self.config.serial.line_ending}"
            self._serial.write(msg.encode("ascii", errors="ignore"))
        else:
            self._serial.write(bytes([v]))

    def _write_outputs(self, value: int) -> None:
        if self.config.dry_run:
            return
        if self._mode_uses_parallel():
            self._parallel_write(value)
        if self._mode_uses_serial():
            self._serial_write(value)

    def _emit_code(self, code: int | None, label: str, **payload: Any) -> None:
        if code is None:
            return
        code = int(max(0, min(int(code), 255)))
        ts = time.monotonic_ns()
        self._records.append({"timestamp_ns": ts, "code": code, "label": label, "payload": payload})
        self._write_outputs(code)
        if self.config.auto_zero:
            wait_s = max(self.config.pulse_width_ms, 0.0) / 1000.0
            if wait_s > 0:
                time.sleep(wait_s)
            self._write_outputs(0)

    def start(self, stem: str, output_dir: Path) -> None:
        self._stem = str(stem)
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._trace_path = self._output_dir / f"{stem}_triggers.jsonl"
        self._meta_path = self._output_dir / f"{stem}_triggers.json"
        self._records.clear()

        if self.config.dry_run:
            return

        if self._mode_uses_parallel():
            self._open_parallel()
        if self._mode_uses_serial():
            self._open_serial()

    def on_run_started(self, run_start_ns: int) -> None:
        self._emit_code(self.config.codes.get("run_started"), "run_started", run_start_ns=int(run_start_ns))

    def on_phase_started(
        self,
        trial_nr: int,
        phase_index: int,
        phase_name: str,
        phase_start_ns: int,
        phase_end_ns: int,
    ) -> None:
        code = self.config.phase_codes.get(str(phase_name))
        if code is None:
            code = self.config.codes.get("phase_started")
        self._emit_code(
            code,
            "phase_started",
            trial_nr=int(trial_nr),
            phase_index=int(phase_index),
            phase_name=str(phase_name),
            phase_start_ns=int(phase_start_ns),
            phase_end_ns=int(phase_end_ns),
        )

    def on_input(
        self,
        key: str,
        timestamp_ns: int,
        event_type: str,
        trial_nr: int,
        phase_index: int,
    ) -> None:
        code = self.config.key_codes.get(str(key).lower())
        if code is None:
            code = self.config.codes.get(str(event_type))
        self._emit_code(
            code,
            "input",
            key=str(key),
            event_type=str(event_type),
            timestamp_ns=int(timestamp_ns),
            trial_nr=int(trial_nr),
            phase_index=int(phase_index),
        )

    def on_run_ended(self, run_end_ns: int, status: RunEndStatus, error: str | None) -> None:
        status_key = {
            RunEndStatus.OK: "run_ended_ok",
            RunEndStatus.ABORTED: "run_ended_aborted",
            RunEndStatus.ERROR: "run_ended_error",
        }.get(status, "run_ended")
        self._emit_code(
            self.config.codes.get(status_key, self.config.codes.get("run_ended")),
            "run_ended",
            run_end_ns=int(run_end_ns),
            status=status.value,
            error=error,
        )

    def stop(self) -> None:
        if not self.config.dry_run:
            try:
                self._write_outputs(0)
            except Exception:
                pass
            try:
                if self._serial is not None:
                    self._serial.close()
            finally:
                self._serial = None
            self._parallel = None
        self._write_artifacts()

    def _write_artifacts(self) -> None:
        if self._trace_path is None or self._meta_path is None:
            return
        with self._trace_path.open("w", encoding="utf8") as f_out:
            for row in self._records:
                f_out.write(json.dumps(row) + "\n")
        meta = {
            "mode": self.config.mode,
            "dry_run": self.config.dry_run,
            "pulse_width_ms": self.config.pulse_width_ms,
            "auto_zero": self.config.auto_zero,
            "parallel": asdict(self.config.parallel),
            "serial": asdict(self.config.serial),
            "codes": self.config.codes,
            "phase_codes": self.config.phase_codes,
            "key_codes": self.config.key_codes,
            "n_emitted": len(self._records),
        }
        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf8")

    def artifact_records(self) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        if self._trace_path is not None and self._trace_path.exists():
            out.append(("trigger_io_events", self._trace_path))
        if self._meta_path is not None and self._meta_path.exists():
            out.append(("trigger_io_metadata", self._meta_path))
        return out

