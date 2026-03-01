from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from exptools2.backends.headless import HeadlessDisplayBackend
from exptools2.core import DisplayConfig, Phase, RunLogger, RunRequest, ScannerTriggerMode, Session, Trial, make_bids_stem
from exptools2.core.types import DrawBatch, InputEvent

try:
    import h5py
except Exception:  # pragma: no cover
    h5py = None


@dataclass(slots=True)
class FixationState:
    event_times_s: np.ndarray
    response_window_s: float
    pointer: int = 0
    polarity: float = 1.0
    responses: dict[int, dict[str, float | str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.responses is None:
            self.responses = {}


@dataclass(slots=True)
class FixationRenderSpec:
    bullseye_color: tuple[float, float, float, float]
    bullseye_radii: tuple[float, ...]
    bullseye_diag_extent: float
    bullseye_line_width_px: float
    report_extent: float
    report_line_width_px: float
    report_color_light: tuple[float, float, float, float]
    report_color_dark: tuple[float, float, float, float]


def _scalar_to_unit(v: float) -> float:
    if v < 0.0:
        return float(np.clip((v + 1.0) * 0.5, 0.0, 1.0))
    return float(np.clip(v, 0.0, 1.0))


def _resolve_fixation_spec(settings: dict[str, Any]) -> FixationRenderSpec:
    stimuli = settings.get("stimuli", {})

    aperture_radius = float(stimuli.get("aperture_radius", 1.0))
    outer_radius = float(stimuli.get("dartboard_outer_radius", aperture_radius))
    max_ring_radius = max(0.0, min(aperture_radius, outer_radius))

    raw_fractions = stimuli.get("dartboard_ring_fractions", [1.0, 0.75, 0.5, 0.25])
    if not isinstance(raw_fractions, (list, tuple)):
        raw_fractions = [raw_fractions]

    # Accept mirrored positive/negative fraction lists (legacy style) and
    # render unique ring radii from outer to inner.
    unique_fractions: dict[str, float] = {}
    for value in raw_fractions:
        try:
            frac = abs(float(value))
        except (TypeError, ValueError):
            continue
        if frac <= 0.0:
            continue
        if frac > 1.0:
            frac = 1.0
        key = f"{frac:.6f}"
        unique_fractions[key] = frac

    if not unique_fractions:
        unique_fractions = {"1.000000": 1.0, "0.750000": 0.75, "0.500000": 0.5, "0.250000": 0.25}

    sorted_fractions = sorted(unique_fractions.values(), reverse=True)
    bullseye_radii = tuple(float(max_ring_radius * frac) for frac in sorted_fractions)

    fixation_extent = float(stimuli.get("fixation_extent", stimuli.get("fix_radius", 0.03)))

    fix_color_raw = float(stimuli.get("fix_color", 0.75))
    fix_light = _scalar_to_unit(fix_color_raw)
    fix_dark = _scalar_to_unit(-fix_color_raw)
    report_color_light = (fix_light, fix_light, fix_light, 1.0)
    report_color_dark = (fix_dark, fix_dark, fix_dark, 1.0)

    bullseye_base = _scalar_to_unit(float(stimuli.get("fixation_base_color", 0.5)))
    bullseye_color = (bullseye_base, bullseye_base, bullseye_base, 1.0)

    return FixationRenderSpec(
        bullseye_color=bullseye_color,
        bullseye_radii=bullseye_radii,
        bullseye_diag_extent=float(stimuli.get("dartboard_diag_extent", outer_radius * 2.0)),
        bullseye_line_width_px=float(stimuli.get("outer_fix_linewidth", 1.0)),
        report_extent=fixation_extent,
        report_line_width_px=float(stimuli.get("inner_fix_linewidth", 2.0)),
        report_color_light=report_color_light,
        report_color_dark=report_color_dark,
    )


def _bar_visible(local_elapsed_s: float, bar_blank_duration: float, bar_blank_interval: float) -> bool:
    interval = float(bar_blank_interval)
    duration = float(bar_blank_duration)

    # Non-positive values disable blanking.
    if interval <= 0.0 or duration <= 0.0:
        return True
    # Equal/longer blank duration is interpreted as "no periodic blanking";
    # this matches the common settings value where both are one frame period.
    if duration >= interval:
        return True

    phase = local_elapsed_s % interval
    return phase >= duration


class PRFBarPassTrial(Trial):
    def __init__(
        self,
        *args,
        start_offset_s: float,
        run_t0_ns: int,
        fixation_state: FixationState,
        is_blank: bool,
        bar_direction: float,
        bar_width: float,
        bar_refresh_time: float,
        bg_stim_refresh_time: float,
        bar_blank_duration: float,
        bar_blank_interval: float,
        aperture_radius: float,
        bar_positions: np.ndarray,
        bg_images: np.ndarray,
        bg_sequence: np.ndarray,
        response_keys: set[str],
        fixation_spec: FixationRenderSpec,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.start_offset_s = start_offset_s
        self.run_t0_ns = run_t0_ns
        self.fixation_state = fixation_state
        self.is_blank = is_blank
        self.bar_direction = bar_direction
        self.bar_width = bar_width
        self.bar_refresh_time = bar_refresh_time
        self.bg_stim_refresh_time = bg_stim_refresh_time
        self.bar_blank_duration = bar_blank_duration
        self.bar_blank_interval = bar_blank_interval
        self.aperture_radius = aperture_radius
        self.bar_positions = bar_positions
        self.bg_images = bg_images
        self.bg_sequence = bg_sequence
        self.response_keys = response_keys
        self.fixation_spec = fixation_spec

        self._phase_start_ns: int | None = None
        self._bg_idx = -1
        self._bar_idx = -1

        self.bg_records: list[tuple[int, float, float]] = []
        self.bar_records: list[tuple[int, float, float]] = []

    def on_run_start(self, run_start_ns: int) -> None:
        self.run_t0_ns = int(run_start_ns)
        self._phase_start_ns = None

    def _run_elapsed_s(self, now_ns: int) -> float:
        return (now_ns - self.run_t0_ns) / 1_000_000_000.0

    def draw(self, phase_index: int, now_ns: int) -> DrawBatch:
        if self._phase_start_ns is None:
            self._phase_start_ns = now_ns

        local_elapsed_s = (now_ns - self._phase_start_ns) / 1_000_000_000.0
        run_elapsed_s = self.start_offset_s + local_elapsed_s

        while (
            self.fixation_state.pointer < len(self.fixation_state.event_times_s)
            and run_elapsed_s >= self.fixation_state.event_times_s[self.fixation_state.pointer]
        ):
            self.fixation_state.pointer += 1
            self.fixation_state.polarity *= -1.0

        bg_idx = min(
            int(local_elapsed_s / self.bg_stim_refresh_time),
            len(self.bg_sequence) - 1,
        )
        if bg_idx != self._bg_idx:
            expected = self.start_offset_s + bg_idx * self.bg_stim_refresh_time
            self.bg_records.append((int(self.bg_sequence[bg_idx]), expected, run_elapsed_s))
            self._bg_idx = bg_idx

        bar_idx = min(
            int(local_elapsed_s / self.bar_refresh_time),
            len(self.bar_positions) - 1,
        )
        if bar_idx != self._bar_idx:
            expected = self.start_offset_s + bar_idx * self.bar_refresh_time
            self.bar_records.append((bar_idx, expected, run_elapsed_s))
            self._bar_idx = bar_idx

        batch = DrawBatch()

        # Constant gray outside the bar aperture.
        bg_level = 0.5
        batch.add(
            "shape",
            shape="rect",
            center=(0.0, 0.0),
            size=(2.0, 2.0),
            fill_color=(bg_level, bg_level, bg_level, 1.0),
            stroke_width=0.0,
        )

        if (not self.is_blank) and _bar_visible(
            local_elapsed_s=local_elapsed_s,
            bar_blank_duration=self.bar_blank_duration,
            bar_blank_interval=self.bar_blank_interval,
        ):
            pos = self.bar_positions[bar_idx]
            frame_idx = int(self.bg_sequence[bg_idx] % len(self.bg_images))
            batch.add(
                "bar_texture",
                image=self.bg_images[frame_idx],
                bar_center=(float(pos[0]), float(pos[1])),
                bar_size=(float(self.bar_width * 2.0), float(self.aperture_radius * 2.0)),
                bar_orientation_deg=float(self.bar_direction),
                aperture_radius=float(self.aperture_radius),
                opacity=1.0,
            )

        fx = self.fixation_spec

        # Match original pRF-SEEG "dartboard" style: two large diagonals + 4 outlined circles.
        diag = fx.bullseye_diag_extent
        bull_col = fx.bullseye_color
        batch.add(
            "line",
            start=(-diag, -diag),
            end=(diag, diag),
            width=fx.bullseye_line_width_px,
            color=bull_col,
            coord_space="square",
        )
        batch.add(
            "line",
            start=(-diag, diag),
            end=(diag, -diag),
            width=fx.bullseye_line_width_px,
            color=bull_col,
            coord_space="square",
        )

        for radius in fx.bullseye_radii:
            batch.add(
                "shape",
                shape="circle",
                center=(0.0, 0.0),
                size=(radius * 2.0, radius * 2.0),
                fill_color=(0.0, 0.0, 0.0, 0.0),
                stroke_color=bull_col,
                line_width_px=fx.bullseye_line_width_px,
                stroke_width=0.003,
                coord_space="square",
            )

        report_col = (
            fx.report_color_dark
            if self.fixation_state.polarity < 0
            else fx.report_color_light
        )
        extent = fx.report_extent
        batch.add(
            "line",
            start=(-extent, -extent),
            end=(extent, extent),
            width=fx.report_line_width_px,
            color=report_col,
            coord_space="square",
        )
        batch.add(
            "line",
            start=(-extent, extent),
            end=(extent, -extent),
            width=fx.report_line_width_px,
            color=report_col,
            coord_space="square",
        )

        return batch

    def on_input(self, event: InputEvent, phase_index: int) -> None:
        super().on_input(event, phase_index)

        if event.key not in self.response_keys:
            return

        run_elapsed_s = self._run_elapsed_s(event.timestamp_ns)
        idx = int(np.searchsorted(self.fixation_state.event_times_s, run_elapsed_s, side="right") - 1)
        if idx < 0:
            return
        if idx in self.fixation_state.responses:
            return

        rt = run_elapsed_s - float(self.fixation_state.event_times_s[idx])
        if 0 <= rt <= self.fixation_state.response_window_s:
            self.fixation_state.responses[idx] = {
                "response_time_s": run_elapsed_s,
                "event_time_s": float(self.fixation_state.event_times_s[idx]),
                "rt_s": rt,
                "key": event.key,
            }


def _rotate(x: np.ndarray, y: np.ndarray, radians: float) -> tuple[np.ndarray, np.ndarray]:
    xx = x * np.cos(radians) + y * np.sin(radians)
    yy = -x * np.sin(radians) + y * np.cos(radians)
    return xx, yy


def create_bar_positions(bar_direction: float, bar_width: float, nr_steps: int) -> np.ndarray:
    steps = np.linspace(-bar_width - 1.0, 1.0 + bar_width, nr_steps, endpoint=True)
    x = steps
    y = np.zeros_like(steps)
    xr, yr = _rotate(x, y, np.deg2rad(bar_direction))
    return np.column_stack([xr, yr])


def create_fixation_event_times(total_time: float, design_cfg: dict[str, Any], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    nr_events = int(6 * total_time / float(design_cfg["minimal_ifi_duration"]))

    exponentials = rng.exponential(float(design_cfg["exponential_ifi_mean"]), nr_events)
    gaussians = rng.normal(0.0, float(design_cfg["gaussian_ifi_sd"]), nr_events)
    offsets = np.ones(nr_events) * float(design_cfg["offset_ifi_duration"])
    minimum = float(design_cfg["minimal_ifi_duration"])

    durations = exponentials + gaussians + offsets
    durations = durations[durations > minimum]
    durations[durations < offsets] = minimum

    return np.cumsum(durations) + float(design_cfg["start_duration"])


def _resolve_stimulus_h5_path(settings: dict[str, Any], settings_file: Path) -> Path:
    stim_cfg = settings.get("stimuli", {})
    filename = str(stim_cfg.get("bg_stim_h5file", "stims_1024.h5"))
    direct = Path(filename).expanduser()
    if direct.is_absolute() and direct.exists():
        return direct
    if "/" in filename or "\\" in filename:
        rel = (settings_file.parent / direct).resolve()
        if rel.exists():
            return rel

    stimuli_dir = settings_file.parent / "stimuli"
    stimuli_dir.mkdir(parents=True, exist_ok=True)
    h5_path = stimuli_dir / filename
    if h5_path.exists():
        return h5_path

    url = stim_cfg.get("bg_stim_url")
    if not url:
        raise FileNotFoundError(
            f"Stimulus file not found at {h5_path} and no bg_stim_url configured"
        )
    print(f"Downloading pRF stimulus file from {url} to {h5_path} ...")
    urllib.request.urlretrieve(url, h5_path)
    return h5_path


def load_bg_images(settings: dict[str, Any], settings_file: Path) -> np.ndarray:
    if h5py is None:
        raise RuntimeError("h5py is required to load pRF bitmap stimuli")

    h5_path = _resolve_stimulus_h5_path(settings=settings, settings_file=settings_file)
    with h5py.File(h5_path, "r") as h5f:
        if "stimuli" not in h5f:
            raise KeyError(f"'stimuli' dataset not found in {h5_path}")
        raw = np.asarray(h5f["stimuli"])

    # Expected: (n, h, w) grayscale or (n, h, w, c)
    if raw.ndim == 3:
        if raw.dtype != np.uint8:
            raw = np.clip(raw, 0, 255).astype(np.uint8)
        rgb = np.repeat(raw[..., None], repeats=3, axis=-1)
    elif raw.ndim == 4:
        if raw.shape[-1] == 1:
            rgb = np.repeat(raw, repeats=3, axis=-1)
        elif raw.shape[-1] >= 3:
            rgb = raw[..., :3]
        else:
            raise ValueError(f"Unsupported image channel count in {h5_path}: {raw.shape[-1]}")
        if rgb.dtype != np.uint8:
            rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    else:
        raise ValueError(f"Unsupported stimulus dataset shape in {h5_path}: {raw.shape}")

    return np.ascontiguousarray(rgb)


def build_prf_trials(
    settings: dict[str, Any],
    run_t0_ns: int,
    fixation_state: FixationState,
    bg_images: np.ndarray,
    fixation_spec: FixationRenderSpec,
    seed: int,
) -> tuple[list[PRFBarPassTrial], float]:
    stimuli_cfg = settings["stimuli"]
    design_cfg = settings["design"]

    bar_dirs = np.array(stimuli_cfg["bar_directions"], dtype=float)
    bar_widths = np.array(stimuli_cfg["bar_widths"], dtype=float)
    bar_refresh_times = np.array(stimuli_cfg["bar_refresh_times"], dtype=float)

    bw_grid, brt_grid = np.meshgrid(bar_widths, bar_refresh_times)
    bw_grid, brt_grid = bw_grid.ravel(), brt_grid.ravel()

    order = np.arange(bw_grid.shape[0])
    rng = np.random.default_rng(seed)
    rng.shuffle(order)

    trials: list[PRFBarPassTrial] = []
    start_offset_s = float(design_cfg["start_duration"])
    idx = 0

    trial_nr = 0
    # Leading blank period.
    trials.append(
        PRFBarPassTrial(
            trial_nr=trial_nr,
            phases=[Phase(name="start", duration_s=float(design_cfg["start_duration"]))],
            start_offset_s=0.0,
            run_t0_ns=run_t0_ns,
            fixation_state=fixation_state,
            is_blank=True,
            bar_direction=0.0,
            bar_width=0.0,
            bar_refresh_time=1.0,
            bg_stim_refresh_time=float(stimuli_cfg["bg_stim_refresh_time"]),
            bar_blank_duration=float(stimuli_cfg["bar_blank_duration"]),
            bar_blank_interval=float(stimuli_cfg["bar_blank_interval"]),
            aperture_radius=float(stimuli_cfg["aperture_radius"]),
            bar_positions=np.array([[0.0, 0.0]]),
            bg_images=bg_images,
            bg_sequence=np.array([0, 1, 2], dtype=int),
            response_keys=set(stimuli_cfg["response_keys"]),
            fixation_spec=fixation_spec,
        )
    )
    trial_nr += 1

    for _ in range(len(bar_widths)):
        for _ in range(len(bar_refresh_times)):
            for bd in bar_dirs:
                is_blank = bd < 0
                if is_blank:
                    duration_s = float(design_cfg["blank_duration"])
                    bw = 0.0
                    brt = 1.0
                    positions = np.array([[0.0, 0.0]])
                else:
                    bw = float(bw_grid[order[idx]])
                    brt = float(brt_grid[order[idx]])
                    duration_s = float(design_cfg["bar_duration"])
                    n_steps = max(1, int(duration_s / brt))
                    positions = create_bar_positions(bd, bw, n_steps)

                n_bg = max(1, int(duration_s / float(stimuli_cfg["bg_stim_refresh_time"])))
                n_bg_images = max(int(bg_images.shape[0]), 1)
                bg_sequence = np.mod(
                    np.cumsum(rng.integers(1, n_bg_images, size=n_bg + 1)),
                    n_bg_images,
                )

                trials.append(
                    PRFBarPassTrial(
                        trial_nr=trial_nr,
                        phases=[Phase(name="blank" if is_blank else "barpass", duration_s=duration_s)],
                        start_offset_s=start_offset_s,
                        run_t0_ns=run_t0_ns,
                        fixation_state=fixation_state,
                        is_blank=is_blank,
                        bar_direction=float(max(0.0, bd)),
                        bar_width=bw,
                        bar_refresh_time=brt,
                        bg_stim_refresh_time=float(stimuli_cfg["bg_stim_refresh_time"]),
                        bar_blank_duration=float(stimuli_cfg["bar_blank_duration"]),
                        bar_blank_interval=float(stimuli_cfg["bar_blank_interval"]),
                        aperture_radius=float(stimuli_cfg["aperture_radius"]),
                        bar_positions=positions,
                        bg_images=bg_images,
                        bg_sequence=bg_sequence,
                        response_keys=set(stimuli_cfg["response_keys"]),
                        fixation_spec=fixation_spec,
                    )
                )

                start_offset_s += duration_s
                trial_nr += 1
            idx += 1

    trials.append(
        PRFBarPassTrial(
            trial_nr=trial_nr,
            phases=[Phase(name="end", duration_s=float(design_cfg["end_duration"]))],
            start_offset_s=start_offset_s,
            run_t0_ns=run_t0_ns,
            fixation_state=fixation_state,
            is_blank=True,
            bar_direction=0.0,
            bar_width=0.0,
            bar_refresh_time=1.0,
            bg_stim_refresh_time=float(stimuli_cfg["bg_stim_refresh_time"]),
            bar_blank_duration=float(stimuli_cfg["bar_blank_duration"]),
            bar_blank_interval=float(stimuli_cfg["bar_blank_interval"]),
            aperture_radius=float(stimuli_cfg["aperture_radius"]),
            bar_positions=np.array([[0.0, 0.0]]),
            bg_images=bg_images,
            bg_sequence=np.array([0, 1, 2], dtype=int),
            response_keys=set(stimuli_cfg["response_keys"]),
            fixation_spec=fixation_spec,
        )
    )

    total_time = start_offset_s + float(design_cfg["end_duration"])
    return trials, total_time


def save_sequence_outputs(
    stem: str, outdir: Path, trials: list[PRFBarPassTrial], fixation_state: FixationState
) -> dict[str, Path]:
    if h5py is not None:
        seq_path = outdir / f"{stem}_seq_timing.h5"
        with h5py.File(seq_path, "w") as h5f:
            for trial in trials:
                group = h5f.create_group(f"trial_{trial.trial_nr:03d}")
                if trial.bg_records:
                    bg = np.asarray(trial.bg_records, dtype=np.float64)
                    group.create_dataset("bg_seq_index", data=bg[:, 0], compression=6)
                    group.create_dataset("bg_expected_time_s", data=bg[:, 1], compression=6)
                    group.create_dataset("bg_empirical_time_s", data=bg[:, 2], compression=6)
                if trial.bar_records:
                    bar = np.asarray(trial.bar_records, dtype=np.float64)
                    group.create_dataset("bar_seq_index", data=bar[:, 0], compression=6)
                    group.create_dataset("bar_expected_time_s", data=bar[:, 1], compression=6)
                    group.create_dataset("bar_empirical_time_s", data=bar[:, 2], compression=6)
    else:
        seq_path = outdir / f"{stem}_seq_timing.json"
        payload: dict[str, Any] = {}
        for trial in trials:
            payload[f"trial_{trial.trial_nr:03d}"] = {
                "bg_records": trial.bg_records,
                "bar_records": trial.bar_records,
            }
        seq_path.write_text(json.dumps(payload, indent=2), encoding="utf8")

    responses_tsv = outdir / f"{stem}_fix_responses.tsv"
    header = "response_time_s\tevent_time_s\trt_s\tkey\n"
    rows = [header]
    for idx, event_time in enumerate(fixation_state.event_times_s):
        row = fixation_state.responses.get(idx)
        if row is None:
            rows.append(f"\t{event_time:.6f}\t\t\n")
        else:
            rows.append(
                f"{row['response_time_s']:.6f}\t{row['event_time_s']:.6f}\t{row['rt_s']:.6f}\t{row['key']}\n"
            )
    responses_tsv.write_text("".join(rows), encoding="utf8")
    return {"seq": seq_path, "responses": responses_tsv}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f_in:
        for chunk in iter(lambda: f_in.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_extra_artifacts(manifest_path: Path, artifacts: list[tuple[str, Path]]) -> None:
    data = json.loads(manifest_path.read_text(encoding="utf8"))
    existing = {entry.get("path") for entry in data.get("artifacts", [])}
    for kind, path in artifacts:
        if str(path) in existing:
            continue
        data.setdefault("artifacts", []).append(
            {
                "kind": kind,
                "path": str(path),
                "metadata": {},
                "sha256": _sha256(path),
            }
        )
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf8")


def run_prf_experiment(
    subject: str,
    run: int,
    backend_name: str,
    settings_file: Path,
    output_root: Path,
    seed: int,
    eyelink_enabled: bool | None = None,
    stimulus_set: str = "default",
    stim_h5file: str | None = None,
) -> dict[str, Any]:
    settings = yaml.safe_load(settings_file.read_text(encoding="utf8"))
    if stim_h5file:
        settings.setdefault("stimuli", {})["bg_stim_h5file"] = str(stim_h5file)
    elif stimulus_set == "toon512":
        settings.setdefault("stimuli", {})["bg_stim_h5file"] = "toon_stims_512.h5"
    elif stimulus_set == "legacy1024":
        settings.setdefault("stimuli", {})["bg_stim_h5file"] = "stims_1024.h5"

    bg_images = load_bg_images(settings=settings, settings_file=settings_file)
    fixation_spec = _resolve_fixation_spec(settings=settings)

    stem = make_bids_stem(sub=subject, ses="01", task="prfseeg", run=f"{run:02d}")
    run_t0_ns = time.monotonic_ns()

    request = RunRequest(
        bids_stem=stem,
        condition_row={"experiment": "prf_seeg"},
        seed=seed,
        t0_ns=run_t0_ns,
        scanner_trigger_mode=ScannerTriggerMode(mode="none"),
    )

    logger = RunLogger(output_root=output_root, bids_stem=stem, backend=backend_name)

    if backend_name == "gl":
        from exptools2.backends.gl import GLDisplayBackend

        backend = GLDisplayBackend()
    elif backend_name == "headless":
        backend = HeadlessDisplayBackend()
    else:
        raise ValueError("backend must be 'gl' or 'headless'")

    recorders: list[Any] = []
    eyelink_cfg = dict(settings.get("eyelink", {}))
    if eyelink_enabled is None:
        eyelink_use = bool(eyelink_cfg.get("enabled", False))
    else:
        eyelink_use = bool(eyelink_enabled)

    if eyelink_use:
        if backend_name != "gl":
            raise ValueError("EyeLink integration requires --backend gl")
        from exptools2.eyelink import EyeLinkRecorder, EyeLinkRecorderConfig

        recorders.append(
            EyeLinkRecorder(
                backend=backend,
                config=EyeLinkRecorderConfig.from_mapping(eyelink_cfg),
            )
        )

    trigger_cfg = dict(settings.get("trigger_io", {}))
    if bool(trigger_cfg.get("enabled", False)):
        from exptools2.triggerio import TriggerIORecorder, TriggerIORecorderConfig

        # Backward-style defaults modeled on original pRF-SEEG trigger semantics.
        design_cfg = dict(settings.get("design", {}))
        trigger_cfg.setdefault(
            "codes",
            {
                "run_started": int(design_cfg.get("ttl_trigger_start", 5)),
                "run_ended_ok": int(design_cfg.get("ttl_trigger_end", 250)),
                "run_ended_aborted": int(design_cfg.get("ttl_trigger_abort", 251)),
                "run_ended_error": int(design_cfg.get("ttl_trigger_error", 252)),
                "abort": int(design_cfg.get("ttl_trigger_abort", 251)),
                "pulse": int(design_cfg.get("ttl_trigger_pulse", 1)),
                "response": int(design_cfg.get("ttl_trigger_response", 20)),
            },
        )
        trigger_cfg.setdefault(
            "phase_codes",
            {
                "barpass": int(design_cfg.get("ttl_trigger_bar", 2)),
                "blank": int(design_cfg.get("ttl_trigger_blank", 3)),
            },
        )
        if "pulse_width_ms" not in trigger_cfg and "ttl_trigger_delay" in design_cfg:
            trigger_cfg["pulse_width_ms"] = float(design_cfg["ttl_trigger_delay"]) * 1000.0

        recorders.append(
            TriggerIORecorder(
                config=TriggerIORecorderConfig.from_mapping(trigger_cfg),
            )
        )

    display_cfg = settings.get("display", {})
    prelude_cfg = dict(settings.get("prelude", {}))
    prelude_cfg.setdefault("enabled", backend_name != "headless")
    prelude_cfg.setdefault("background_color", [0.5, 0.5, 0.5, 1.0])
    prelude_cfg.setdefault("instruction_text", "Press SPACE to continue.\n\nFixate and press T to start.")
    prelude_cfg.setdefault("instruction_continue_key", "space")
    prelude_cfg.setdefault("show_fixation_wait", True)
    prelude_cfg.setdefault("start_key", "t")

    instruction_cfg = dict(prelude_cfg.get("instruction", {}))
    instruction_cfg.setdefault("text", prelude_cfg.get("instruction_text"))
    instruction_cfg.setdefault("continue_keys", prelude_cfg.get("instruction_continue_key", "space"))
    if "instruction_duration_s" in prelude_cfg:
        instruction_cfg.setdefault("timeout_s", prelude_cfg.get("instruction_duration_s"))
    style_cfg = dict(instruction_cfg.get("style", {}))
    style_cfg.setdefault("panel_width_fraction", 0.76)
    style_cfg.setdefault("panel_height_fraction", 0.54)
    style_cfg.setdefault("panel_fill", [0.07, 0.09, 0.12, 0.86])
    style_cfg.setdefault("panel_border", [0.88, 0.90, 0.95, 0.34])
    style_cfg.setdefault("text_color", [0.97, 0.98, 1.0, 1.0])
    style_cfg.setdefault("panel_padding_px", 56)
    style_cfg.setdefault("font_size_px", 44)
    style_cfg.setdefault("line_spacing_px", 10)
    style_cfg.setdefault("text_align", "center")
    instruction_cfg["style"] = style_cfg
    prelude_cfg["instruction"] = instruction_cfg

    fixation_wait_cfg = dict(prelude_cfg.get("fixation_wait", {}))
    fixation_wait_cfg.setdefault("enabled", prelude_cfg.get("show_fixation_wait", True))
    fixation_wait_cfg.setdefault("start_keys", prelude_cfg.get("start_key", "t"))
    fixation_wait_cfg.setdefault("color", [0.85, 0.85, 0.85, 1.0])
    fixation_wait_cfg.setdefault("extent", prelude_cfg.get("fixation_extent", 0.03))
    fixation_wait_cfg.setdefault("line_width_px", prelude_cfg.get("fixation_line_width_px", 2.0))
    prelude_cfg["fixation_wait"] = fixation_wait_cfg

    session = Session(
        request=request,
        backend=backend,
        logger=logger,
        display_config=DisplayConfig(
            width=int(display_cfg.get("width", 1920)),
            height=int(display_cfg.get("height", 1080)),
            refresh_hz=float(display_cfg.get("refresh_hz", 60.0)),
            fullscreen=bool(display_cfg.get("fullscreen", False)),
            hide_cursor=bool(display_cfg.get("hide_cursor", True)),
            vsync=bool(display_cfg.get("vsync", True)),
            monitor_name=str(display_cfg.get("monitor_name", "default")),
            monitor_index=(
                int(display_cfg["monitor_index"])
                if display_cfg.get("monitor_index") is not None
                else None
            ),
            title="pRF SEEG (exptools2 rewrite)",
        ),
        recorders=recorders,
        prelude=prelude_cfg,
    )

    # Build trials/fixation schedule in the same spirit as the original pRF design.
    trial_seed = seed + run
    trials, total_time = build_prf_trials(
        settings=settings,
        run_t0_ns=run_t0_ns,
        fixation_state=FixationState(event_times_s=np.array([]), response_window_s=1.0),
        bg_images=bg_images,
        fixation_spec=fixation_spec,
        seed=trial_seed,
    )
    fix_events = create_fixation_event_times(total_time, settings["design"], seed=trial_seed)
    fixation_state = FixationState(
        event_times_s=fix_events,
        response_window_s=float(settings["design"].get("response_window_s", 1.0)),
    )

    # Rebuild trials with a shared fixation state object.
    trials, total_time = build_prf_trials(
        settings=settings,
        run_t0_ns=run_t0_ns,
        fixation_state=fixation_state,
        bg_images=bg_images,
        fixation_spec=fixation_spec,
        seed=trial_seed,
    )
    session.add_trials(trials)

    result = session.run()
    outdir = logger.paths.events_tsv.parent
    outputs = save_sequence_outputs(
        stem=stem, outdir=outdir, trials=trials, fixation_state=fixation_state
    )

    hits = len(fixation_state.responses)
    total = len(fixation_state.event_times_s)
    hit_rate = (hits / total) if total else 0.0

    metrics_path = outdir / f"{stem}_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "fixation_hits": hits,
                "fixation_events": total,
                "hit_rate": hit_rate,
                "total_time_s": total_time,
                "status": result.status.value,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    register_extra_artifacts(
        logger.paths.manifest_json,
        artifacts=[
            ("prf_seq_timing", outputs["seq"]),
            ("prf_fix_responses", outputs["responses"]),
            ("prf_metrics", metrics_path),
        ],
    )

    return {
        "stem": stem,
        "backend": backend_name,
        "status": result.status.value,
        "output_dir": str(outdir),
        "hit_rate": hit_rate,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="pRF SEEG example migrated to the new exptools2 API")
    parser.add_argument("subject", nargs="?", default="001")
    parser.add_argument("run", nargs="?", type=int, default=1)
    parser.add_argument("--backend", choices=["gl", "headless"], default="gl")
    parser.add_argument("--settings", type=Path, default=Path(__file__).with_name("settings.yml"))
    parser.add_argument("--output-root", type=Path, default=Path("logs"))
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument(
        "--stimulus-set",
        choices=["default", "toon512", "legacy1024"],
        default="default",
        help="Select built-in background stimulus set",
    )
    parser.add_argument(
        "--stim-h5file",
        type=str,
        default=None,
        help="Explicit HDF5 stimulus file (absolute, relative, or filename in examples/prf_seeg/stimuli)",
    )
    parser.add_argument("--eyelink", action="store_true", help="Enable EyeLink recorder/calibration if configured")
    parser.add_argument(
        "--no-eyelink",
        action="store_true",
        help="Disable EyeLink integration even if enabled in settings",
    )
    args = parser.parse_args()

    eyelink_flag: bool | None = None
    if args.eyelink and not args.no_eyelink:
        eyelink_flag = True
    elif args.no_eyelink and not args.eyelink:
        eyelink_flag = False

    result = run_prf_experiment(
        subject=str(args.subject),
        run=int(args.run),
        backend_name=args.backend,
        settings_file=args.settings,
        output_root=args.output_root,
        seed=args.seed,
        eyelink_enabled=eyelink_flag,
        stimulus_set=str(args.stimulus_set),
        stim_h5file=args.stim_h5file,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
