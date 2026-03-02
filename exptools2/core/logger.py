from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .bids import bids_artifact_path
from .types import ArtifactPaths, RunArtifactManifest, RunStatus, StatusKind


class RunLogger:
    def __init__(
        self,
        output_root: str | Path,
        bids_stem: str,
        contract_version: str = "1.1",
        backend: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.bids_stem = bids_stem
        self.contract_version = contract_version
        self.backend = backend
        self.metadata = metadata or {}

        self.events: list[dict[str, Any]] = []
        self.statuses: list[RunStatus] = []
        self.flip_records: list[dict[str, Any]] = []
        self.video_records: list[dict[str, Any]] = []
        self.audio_records: list[dict[str, Any]] = []
        self.stim_trace: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []

    @property
    def paths(self) -> ArtifactPaths:
        return ArtifactPaths(
            events_tsv=bids_artifact_path(self.output_root, self.bids_stem, "events", "tsv"),
            events_json=bids_artifact_path(self.output_root, self.bids_stem, "events", "json"),
            log_h5=bids_artifact_path(self.output_root, self.bids_stem, "log", "h5"),
            manifest_json=bids_artifact_path(
                self.output_root, self.bids_stem, "manifest", "json"
            ),
        )

    @property
    def report_path(self) -> Path:
        return bids_artifact_path(self.output_root, self.bids_stem, "report", "txt")

    @property
    def timing_dashboard_path(self) -> Path:
        return bids_artifact_path(
            self.output_root, self.bids_stem, "timing_dashboard", "png"
        )

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f_in:
            for chunk in iter(lambda: f_in.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _json_default(self, obj: Any) -> Any:
        # numpy compatibility (without hard dependency at import time)
        if hasattr(obj, "tolist"):
            try:
                return obj.tolist()
            except Exception:
                pass
        if isinstance(obj, (set, tuple)):
            return list(obj)
        return str(obj)

    def register_artifact(
        self,
        path: str | Path,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        p = Path(path)
        entry = {
            "kind": kind,
            "path": str(p),
            "metadata": metadata or {},
        }
        if p.exists() and p.is_file():
            entry["sha256"] = self._hash_file(p)
        self.artifacts.append(entry)

    def log_status(self, kind: StatusKind, timestamp_ns: int, **payload: Any) -> None:
        self.statuses.append(RunStatus(kind=kind, timestamp_ns=timestamp_ns, payload=payload))

    def log_event(
        self,
        onset_ns: int,
        event_type: str,
        trial_nr: int | None = None,
        phase: int | None = None,
        response: str | None = None,
        duration_ns: int | None = None,
        **extra: Any,
    ) -> None:
        row: dict[str, Any] = {
            "onset_ns": onset_ns,
            "event_type": event_type,
            "trial_nr": trial_nr,
            "phase": phase,
            "response": response,
            "duration_ns": duration_ns,
        }
        row.update(extra)
        self.events.append(row)

    def log_flip(self, **record: Any) -> None:
        self.flip_records.append(record)

    def log_video_frame(self, **record: Any) -> None:
        self.video_records.append(record)

    def log_audio(self, **record: Any) -> None:
        self.audio_records.append(record)

    def log_stimulus(self, **record: Any) -> None:
        self.stim_trace.append(record)

    def _write_events(self, run_start_ns: int) -> None:
        paths = self.paths
        event_rows: list[dict[str, Any]] = []
        for row in self.events:
            item = dict(row)
            onset_ns = int(item.pop("onset_ns"))
            duration_ns = item.pop("duration_ns", 0) or 0
            item["onset"] = (onset_ns - run_start_ns) / 1_000_000_000
            item["duration"] = float(duration_ns) / 1_000_000_000
            event_rows.append(item)

        paths.events_tsv.parent.mkdir(parents=True, exist_ok=True)
        fixed = ["onset", "duration", "event_type", "trial_nr", "phase", "response"]
        extra_cols: list[str] = []
        for row in event_rows:
            for key in row.keys():
                if key not in fixed and key not in extra_cols:
                    extra_cols.append(key)
        fieldnames = fixed + extra_cols

        with paths.events_tsv.open("w", encoding="utf8", newline="") as f_out:
            writer = csv.DictWriter(
                f_out, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore"
            )
            writer.writeheader()
            for row in event_rows:
                writer.writerow(row)

        sidecar = {
            "onset": {"Description": "Event onset relative to run start", "Units": "s"},
            "duration": {"Description": "Event duration", "Units": "s"},
            "event_type": {"Description": "Event label"},
            "trial_nr": {"Description": "Trial index"},
            "phase": {"Description": "Phase index within trial"},
            "response": {"Description": "Response key/value"},
            "contract_version": self.contract_version,
            "backend": self.backend,
        }
        paths.events_json.write_text(
            json.dumps(sidecar, indent=2, default=self._json_default), encoding="utf8"
        )

        self.register_artifact(paths.events_tsv, kind="events_tsv")
        self.register_artifact(paths.events_json, kind="events_sidecar")

    def _write_h5(self, run_start_ns: int, run_end_ns: int) -> None:
        paths = self.paths

        try:
            import h5py
        except Exception:  # pragma: no cover
            h5py = None

        payload = {
            "run_start_ns": run_start_ns,
            "run_end_ns": run_end_ns,
            "contract_version": self.contract_version,
            "backend": self.backend,
            "metadata": self.metadata,
            "statuses": [asdict(x) for x in self.statuses],
            "events": self.events,
            "flips": self.flip_records,
            "video": self.video_records,
            "audio": self.audio_records,
            "stim_trace": self.stim_trace,
        }

        if h5py is not None:
            with h5py.File(paths.log_h5, "w") as h5f:
                h5f.attrs["contract_version"] = self.contract_version
                h5f.attrs["backend"] = self.backend
                h5f.attrs["run_start_ns"] = run_start_ns
                h5f.attrs["run_end_ns"] = run_end_ns
                h5f.create_dataset(
                    "payload_json",
                    data=json.dumps(
                        payload, separators=(",", ":"), default=self._json_default
                    ).encode("utf8"),
                )
                self._write_h5_timing_tables(h5f=h5f, run_start_ns=run_start_ns)
        else:
            # Lightweight fallback: preserve path/extension and store JSON payload.
            paths.log_h5.write_text(
                json.dumps(payload, indent=2, default=self._json_default), encoding="utf8"
            )

        self.register_artifact(paths.log_h5, kind="run_log")

    def _write_manifest(self) -> RunArtifactManifest:
        paths = self.paths
        manifest = RunArtifactManifest(
            contract_version=self.contract_version,
            bids_stem=self.bids_stem,
            backend=self.backend,
            output_root=str(self.output_root),
            artifacts=[],
        )
        for record in self.artifacts:
            manifest.artifacts.append(record)  # type: ignore[arg-type]

        paths.manifest_json.write_text(
            json.dumps(asdict(manifest), indent=2, default=self._json_default),
            encoding="utf8",
        )
        self.register_artifact(paths.manifest_json, kind="manifest")
        return manifest

    @staticmethod
    def _coerce_int(value: Any, default: int = -1) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except Exception:
            return default

    def _write_h5_timing_tables(self, h5f: Any, run_start_ns: int) -> None:
        import numpy as np

        try:
            import h5py
        except Exception:  # pragma: no cover
            return

        str_dtype = h5py.string_dtype(encoding="utf-8")
        run_start_ns_i = int(run_start_ns)

        flip_group = h5f.create_group("flips")
        flip_rows = list(self.flip_records)
        n_flips = len(flip_rows)

        def flip_int(key: str, default: int = -1) -> np.ndarray:
            return np.asarray(
                [self._coerce_int(row.get(key), default=default) for row in flip_rows],
                dtype=np.int64,
            )

        ts_ns = flip_int("timestamp_ns")
        target_ns = flip_int("target_ns")
        frame_index = flip_int("frame_index")
        late_ns = flip_int("late_ns", default=0)
        dropped_frames = flip_int("dropped_frames", default=0)
        trial_nr = flip_int("trial_nr")
        phase = flip_int("phase")

        flip_group.create_dataset("timestamp_ns", data=ts_ns)
        flip_group.create_dataset("target_ns", data=target_ns)
        flip_group.create_dataset("frame_index", data=frame_index)
        flip_group.create_dataset("late_ns", data=late_ns)
        flip_group.create_dataset("dropped_frames", data=dropped_frames)
        flip_group.create_dataset("trial_nr", data=trial_nr)
        flip_group.create_dataset("phase", data=phase)
        if n_flips > 0:
            timestamp_s = ts_ns.astype(np.float64)
            timestamp_s = (timestamp_s - float(run_start_ns_i)) / 1_000_000_000.0
            target_s = target_ns.astype(np.float64)
            target_s = (target_s - float(run_start_ns_i)) / 1_000_000_000.0
            target_s[target_ns < 0] = np.nan
            late_ms = late_ns.astype(np.float64) / 1_000_000.0
            interval_ms = np.full(n_flips, np.nan, dtype=np.float64)
            if n_flips >= 2:
                interval_ms[1:] = np.diff(ts_ns.astype(np.float64)) / 1_000_000.0
        else:
            timestamp_s = np.asarray([], dtype=np.float64)
            target_s = np.asarray([], dtype=np.float64)
            late_ms = np.asarray([], dtype=np.float64)
            interval_ms = np.asarray([], dtype=np.float64)

        flip_group.create_dataset("timestamp_s", data=timestamp_s)
        flip_group.create_dataset("target_s", data=target_s)
        flip_group.create_dataset("late_ms", data=late_ms)
        flip_group.create_dataset("interval_ms", data=interval_ms)

        flip_json_rows = [
            json.dumps(row, separators=(",", ":"), default=self._json_default)
            for row in flip_rows
        ]
        flip_group.create_dataset(
            "raw_json",
            data=np.asarray(flip_json_rows, dtype=object),
            dtype=str_dtype,
        )

        input_group = h5f.create_group("inputs")
        input_rows = [
            row
            for row in self.events
            if str(row.get("event_type")) in {"response", "pulse", "abort"}
        ]
        onset_ns = np.asarray(
            [self._coerce_int(row.get("onset_ns")) for row in input_rows], dtype=np.int64
        )
        onset_s = (onset_ns.astype(np.float64) - float(run_start_ns_i)) / 1_000_000_000.0
        trial_vals = np.asarray(
            [self._coerce_int(row.get("trial_nr")) for row in input_rows], dtype=np.int64
        )
        phase_vals = np.asarray(
            [self._coerce_int(row.get("phase")) for row in input_rows], dtype=np.int64
        )
        event_type_vals = np.asarray(
            [str(row.get("event_type", "")) for row in input_rows], dtype=object
        )
        response_vals = np.asarray(
            [str(row.get("response", "")) if row.get("response") is not None else "" for row in input_rows],
            dtype=object,
        )
        input_group.create_dataset("onset_ns", data=onset_ns)
        input_group.create_dataset("onset_s", data=onset_s)
        input_group.create_dataset("trial_nr", data=trial_vals)
        input_group.create_dataset("phase", data=phase_vals)
        input_group.create_dataset("event_type", data=event_type_vals, dtype=str_dtype)
        input_group.create_dataset("response", data=response_vals, dtype=str_dtype)
        input_json_rows = [
            json.dumps(row, separators=(",", ":"), default=self._json_default)
            for row in input_rows
        ]
        input_group.create_dataset(
            "raw_json",
            data=np.asarray(input_json_rows, dtype=object),
            dtype=str_dtype,
        )

    def write_timing_dashboard(
        self,
        run_start_ns: int,
        run_end_ns: int,
        refresh_hz: float | None = None,
        kind: str = "timing_dashboard",
    ) -> Path | None:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception as exc:
            self.metadata["timing_dashboard_error"] = (
                f"{exc.__class__.__name__}: {exc}"
            )
            return None

        run_start_ns_i = int(run_start_ns)
        run_end_ns_i = int(run_end_ns)
        run_duration_s = max(0.0, (run_end_ns_i - run_start_ns_i) / 1_000_000_000.0)
        expected_interval_ms = 1000.0 / float(refresh_hz) if refresh_hz else None

        ts_ns = np.asarray(
            [self._coerce_int(row.get("timestamp_ns")) for row in self.flip_records],
            dtype=np.int64,
        )
        late_ms = np.asarray(
            [self._coerce_int(row.get("late_ns"), default=0) / 1_000_000.0 for row in self.flip_records],
            dtype=np.float64,
        )
        dropped_frames = np.asarray(
            [self._coerce_int(row.get("dropped_frames"), default=0) for row in self.flip_records],
            dtype=np.int64,
        )
        ts_s = (ts_ns.astype(np.float64) - float(run_start_ns_i)) / 1_000_000_000.0
        interval_ms = (
            np.diff(ts_ns.astype(np.float64)) / 1_000_000.0 if ts_ns.size >= 2 else np.asarray([], dtype=np.float64)
        )
        interval_t_s = ts_s[1:] if ts_s.size >= 2 else np.asarray([], dtype=np.float64)

        input_rows = [
            row
            for row in self.events
            if str(row.get("event_type")) in {"response", "pulse", "abort"}
        ]
        input_t_s = np.asarray(
            [
                (self._coerce_int(row.get("onset_ns")) - run_start_ns_i) / 1_000_000_000.0
                for row in input_rows
            ],
            dtype=np.float64,
        )
        input_type = [str(row.get("event_type")) for row in input_rows]
        response_t_s = np.asarray(
            [
                (self._coerce_int(row.get("onset_ns")) - run_start_ns_i) / 1_000_000_000.0
                for row in input_rows
                if str(row.get("event_type")) == "response"
            ],
            dtype=np.float64,
        )
        response_ibi_ms = (
            np.diff(response_t_s) * 1000.0
            if response_t_s.size >= 2
            else np.asarray([], dtype=np.float64)
        )

        fig, axes = plt.subplots(2, 3, figsize=(16, 9))
        fig.suptitle(
            f"Timing Dashboard: {self.bids_stem}\n"
            f"duration={run_duration_s:.3f}s, flips={ts_ns.size}, inputs={len(input_rows)}"
        )

        ax = axes[0, 0]
        if interval_ms.size > 0:
            ax.plot(interval_t_s, interval_ms, lw=1.0, color="#1f77b4")
            if expected_interval_ms is not None:
                ax.axhline(
                    expected_interval_ms,
                    color="#d62728",
                    lw=1.0,
                    ls="--",
                    label=f"target {expected_interval_ms:.3f} ms",
                )
                ax.legend(loc="upper right", fontsize=8)
        else:
            ax.text(0.5, 0.5, "No flip intervals", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Flip Intervals Over Time")
        ax.set_xlabel("Time since run start (s)")
        ax.set_ylabel("Interval (ms)")

        ax = axes[0, 1]
        if interval_ms.size > 0:
            bins = min(80, max(10, int(round(np.sqrt(interval_ms.size)))))
            ax.hist(interval_ms, bins=bins, color="#2ca02c", alpha=0.85)
            if expected_interval_ms is not None:
                ax.axvline(expected_interval_ms, color="#d62728", lw=1.0, ls="--")
        else:
            ax.text(0.5, 0.5, "No flip intervals", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Flip Interval Distribution")
        ax.set_xlabel("Interval (ms)")
        ax.set_ylabel("Count")

        ax = axes[0, 2]
        if ts_s.size > 0:
            ax.plot(ts_s, late_ms, lw=0.9, color="#ff7f0e")
            if expected_interval_ms is not None:
                ax.axhline(expected_interval_ms * 0.5, color="#d62728", lw=1.0, ls="--")
        else:
            ax.text(0.5, 0.5, "No flips", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Flip Lateness Over Time")
        ax.set_xlabel("Time since run start (s)")
        ax.set_ylabel("Lateness (ms)")

        ax = axes[1, 0]
        if ts_s.size > 0:
            ax.step(ts_s, dropped_frames, where="post", color="#9467bd", lw=1.0)
            ax.set_ylim(bottom=0)
        else:
            ax.text(0.5, 0.5, "No flips", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Dropped Frames By Flip")
        ax.set_xlabel("Time since run start (s)")
        ax.set_ylabel("Dropped frames")

        ax = axes[1, 1]
        if input_t_s.size > 0:
            y_map = {"response": 0, "pulse": 1, "abort": 2}
            y = np.asarray([y_map.get(kind, 3) for kind in input_type], dtype=np.float64)
            ax.scatter(input_t_s, y, s=18, alpha=0.85, color="#8c564b")
            ax.set_yticks([0, 1, 2, 3], labels=["response", "pulse", "abort", "other"])
        else:
            ax.text(0.5, 0.5, "No input events", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Input Event Timeline")
        ax.set_xlabel("Time since run start (s)")
        ax.set_ylabel("Event type")

        ax = axes[1, 2]
        if response_ibi_ms.size > 0:
            bins = min(60, max(10, int(round(np.sqrt(response_ibi_ms.size)))))
            ax.hist(response_ibi_ms, bins=bins, color="#17becf", alpha=0.9)
        else:
            ax.text(
                0.5,
                0.5,
                "Not enough responses for IBI",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        ax.set_title("Response Intervals (IBI)")
        ax.set_xlabel("Inter-response interval (ms)")
        ax.set_ylabel("Count")

        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
        path = self.timing_dashboard_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=160)
        plt.close(fig)
        self.register_artifact(
            path=path,
            kind=kind,
            metadata={
                "run_start_ns": run_start_ns_i,
                "run_end_ns": run_end_ns_i,
                "refresh_hz": float(refresh_hz) if refresh_hz is not None else None,
            },
        )
        return path

    def write_text_report(self, text: str, kind: str = "run_report") -> Path:
        path = self.report_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(text), encoding="utf8")
        self.register_artifact(path=path, kind=kind)
        return path

    def finalize(self, run_start_ns: int, run_end_ns: int) -> ArtifactPaths:
        self._write_events(run_start_ns=run_start_ns)
        self._write_h5(run_start_ns=run_start_ns, run_end_ns=run_end_ns)
        self._write_manifest()
        return self.paths
