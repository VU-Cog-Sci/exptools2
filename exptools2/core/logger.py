from __future__ import annotations

import hashlib
import json
import csv
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

    def finalize(self, run_start_ns: int, run_end_ns: int) -> ArtifactPaths:
        self._write_events(run_start_ns=run_start_ns)
        self._write_h5(run_start_ns=run_start_ns, run_end_ns=run_end_ns)
        self._write_manifest()
        return self.paths
