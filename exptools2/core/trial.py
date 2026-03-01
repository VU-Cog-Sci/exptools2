from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import DrawBatch, InputEvent, Phase


@dataclass(slots=True)
class Trial:
    trial_nr: int
    phases: list[Phase]
    condition_row: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    last_response: str | None = None
    last_response_onset_ns: int | None = None

    def draw(self, phase_index: int, now_ns: int) -> DrawBatch:
        """Override in subclass to emit backend draw commands for the current frame."""
        return DrawBatch()

    def on_input(self, event: InputEvent, phase_index: int) -> None:
        self.last_response = event.key
        self.last_response_onset_ns = event.timestamp_ns

    def on_run_start(self, run_start_ns: int) -> None:  # noqa: ARG002
        """Optional lifecycle hook called once when a session run starts."""
        return


@dataclass(slots=True)
class ConditionTrial(Trial):
    """Generic trial whose condition row directly maps to draw commands."""

    def draw(self, phase_index: int, now_ns: int) -> DrawBatch:
        batch = DrawBatch()
        command = self.condition_row.get("draw_command")
        if isinstance(command, dict):
            kind = command.get("kind", "noop")
            params = {k: v for k, v in command.items() if k != "kind"}
            batch.add(kind, **params)
        return batch
