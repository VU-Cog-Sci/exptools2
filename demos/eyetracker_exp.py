"""Marker recorder demo; dedicated eyetracker integrations are backend-specific."""

from __future__ import annotations

from pathlib import Path

from exptools2.core.recorders import MarkerRecorder


if __name__ == "__main__":
    outdir = Path("logs")
    outdir.mkdir(exist_ok=True)
    rec = MarkerRecorder()
    rec.start(stem="sub-001_ses-01_task-eye_run-01", output_dir=outdir)
    rec.mark("calibration_start", 1)
    rec.mark("calibration_end", 2)
    rec.stop()
    print(rec.artifact_paths())
