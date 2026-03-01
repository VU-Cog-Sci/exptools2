# exptools2

`exptools2` is a backend-agnostic experiment runtime with a strict run contract.
It is no longer a wrapper around PsychoPy.

## What this rewrite provides

- Shared core for `Session / Trial / Phase` with non-slip monotonic scheduling.
- Contract-first runs (`RunRequest` + status semantics + required artifacts).
- BIDS-like stem naming and output layout.
- Core run outputs:
  - `<stem>_events.tsv`
  - `<stem>_events.json`
  - `<stem>_log.h5`
  - `<stem>_manifest.json`
- Backend A scaffold: GLFW/OpenGL 3.3 psychophysics backend.
- Backend B scaffold: Godot subprocess backend with UDP contract channel.
- Video scaffold: PyAV/FFmpeg player interface with hwaccel selection.
- Audio scaffold: PTB-like API with Psychtoolbox adapter + PortAudio fallback.

## Installation

```bash
pip install -e .
```

Optional runtime extras:

```bash
pip install -e .[gl,video,audio]
```

For image-sequence conversion only:

```bash
pip install -e .[media]
```

EyeLink integration is optional and loaded at runtime when configured:

```bash
pip install -e .[gl]
# then install pylink from SR Research (private wheel/path) or:
# pip install sr-research-pylink
```

Trigger I/O (parallel/serial TTL) is optional:

```bash
pip install -e .[triggerio]
```

Or bootstrap a full development/docs/runtime environment:

```bash
scripts/create_env.sh --extras full,docs,dev
source .venv/bin/activate
```

Install Godot 4 helper (for subprocess/world examples):

```bash
scripts/install_godot4.sh
```

## CLI

```bash
expctl run config.yaml
```

Minimal `config.yaml`:

```yaml
run:
  sub: "001"
  ses: "01"
  task: "roam"
  run: "02"
  backend: gl
  output_root: logs
  seed: 123
  contract_version: "1.1"

conditions:
  rows:
    - phase_name: stim
      duration_s: 1.0
      draw_command:
        kind: gabor
        orientation_deg: 45
```

## Example Experiments

The `examples/` folder contains runnable examples for:

- Headless contract validation (`examples/basic_headless_experiment.py`)
- GLFW/OpenGL visual stimuli (`examples/gl_visual_experiment.py`)
- Shader-backed still image stimulus (`examples/image_stimulus_experiment.py`)
- Audio scheduling/playback (`examples/audio_playback_experiment.py`)
- Video decoding/scheduling (`examples/video_playback_experiment.py`)
- Godot subprocess runs (`examples/godot_subprocess_experiment.py`)
- Godot navigation arena (`examples/godot_navigation_experiment.py`)
- Migrated pRF SEEG workflow (`examples/prf_seeg/main.py`)

Multi-monitor selection is configurable via YAML:

```yaml
display:
  monitor_index: 1
  monitor_name: primary
```

## EyeLink (pylink) Integration

When `eyelink.enabled: true` is present in config, `Session` starts an
`EyeLinkRecorder` that:

- connects to tracker (`address`)
- configures pixel coordinates + tracker options
- runs calibration/drift correction on the GLFW display
- starts recording at run start
- sends phase/input markers
- retrieves EDF into the run output folder

Example config block:

```yaml
eyelink:
  enabled: true
  address: "100.1.1.1"
  calibrate_on_start: true
  drift_correct_on_start: false
  sample_rate: 1000
  options:
    calibration_type: HV9
```

Private/local pylink installs can be exposed via `PYTHONPATH` before launch.

## Trigger I/O (EEG/TTL)

`trigger_io` can emit event codes to:

- parallel port (LPT, via `parallel` module)
- serial port (USB serial adapters, via `pyserial`)

This is integrated through `Session` recorder hooks and can tag:

- run start/end
- phase start by name (`phase_codes`)
- scanner pulses (`pulse`)
- participant responses (`response`)
- abort events

Example:

```yaml
trigger_io:
  enabled: true
  mode: parallel
  pulse_width_ms: 1.0
  parallel:
    address: 0x0378
  phase_codes:
    barpass: 2
    blank: 3
```

## Bitmap Sequence to HDF5

Use either the package CLI or the utility script to convert jpg/png/gif image
sequences into an HDF5 `stimuli` dataset compatible with the pRF-style bitmap
workflow:

```bash
expctl images-to-hdf5 examples/prf_seeg/stimuli \
  --output examples/prf_seeg/stimuli/custom_stims.h5 \
  --mode rgb --resize 512x512
```

Equivalent script command:

```bash
python scripts/images_to_hdf5.py examples/prf_seeg/stimuli \
  --output examples/prf_seeg/stimuli/custom_stims.h5 \
  --mode rgb --resize 512x512
```

Run the migrated pRF SEEG example:

```bash
python examples/prf_seeg/main.py 001 1 --backend headless
```

## Documentation (Sphinx)

Build local docs:

```bash
scripts/build_docs.sh
```

Then open:

`doc/_build/html/index.html`

## API sketch

```python
from exptools2.core import (
    DisplayConfig,
    Phase,
    RunLogger,
    RunRequest,
    ScannerTriggerMode,
    Session,
)
from exptools2.backends.gl import GLDisplayBackend
from exptools2.core.trial import ConditionTrial

request = RunRequest(
    bids_stem="sub-001_ses-01_task-roam_run-02",
    condition_row={"n_rows": 1},
    seed=123,
    t0_ns=1,
    scanner_trigger_mode=ScannerTriggerMode(mode="none"),
)
logger = RunLogger(output_root="logs", bids_stem=request.bids_stem, backend="gl")
session = Session(request=request, backend=GLDisplayBackend(), logger=logger, display_config=DisplayConfig(fullscreen=False))
session.add_trial(ConditionTrial(trial_nr=0, phases=[Phase(name="stim", duration_s=1.0)]))
session.run()
```

## Notes

- OS focus for this rewrite is macOS + Linux.
- This is a hard API break from the old PsychoPy-centric exptools2 API.
- Shader/video/audio paths are implemented as modular backends/adapters so experiment logic remains backend-independent.
