from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Recorder(Protocol):
    def start(self, stem: str, output_dir: Path) -> None:
        ...

    def stop(self) -> None:
        ...

    def artifact_paths(self) -> list[Path]:
        ...

    def artifact_records(self) -> list[tuple[str, Path]]:
        ...


class MarkerRecorder:
    """Minimal marker recorder placeholder for physio/eyetracker marker streams."""

    def __init__(self) -> None:
        self._records: list[dict] = []
        self._output: Path | None = None

    def start(self, stem: str, output_dir: Path) -> None:
        self._output = output_dir / f"{stem}_markers.jsonl"

    def mark(self, label: str, timestamp_ns: int, **payload) -> None:
        self._records.append(
            {"label": label, "timestamp_ns": timestamp_ns, "payload": payload}
        )

    def stop(self) -> None:
        if self._output is None:
            return
        self._output.parent.mkdir(parents=True, exist_ok=True)
        with self._output.open("w", encoding="utf8") as f_out:
            for row in self._records:
                import json

                f_out.write(json.dumps(row) + "\n")

    def artifact_paths(self) -> list[Path]:
        if self._output is None:
            return []
        return [self._output]

    def artifact_records(self) -> list[tuple[str, Path]]:
        if self._output is None:
            return []
        return [("marker_stream", self._output)]
