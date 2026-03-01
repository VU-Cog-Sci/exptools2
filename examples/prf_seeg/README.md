# pRF SEEG example (ported from `spinoza-centre/prf-seeg`)

This example ports the original `experiment/` workflow from:
`https://github.com/spinoza-centre/prf-seeg/tree/main/experiment`

to the new exptools2 architecture.

## What is preserved

- Multi-pass bar design with randomized bar width/refresh combinations.
- Direction sequence including explicit blank trials (`-1` directions).
- Separate bar and background refresh timing streams.
- Original pRF bitmap stimulus source (`stims_1024.h5`) with auto-download.
- Exponential fixation-event schedule and response scoring.
- Sequence timing output (`*_seq_timing.h5`) plus fixation response table.
- Optional EEG-style trigger output via parallel/serial `trigger_io`.

## What is intentionally different

- It uses the new contract/session runtime (`RunRequest`, `Session`, `RunLogger`).
- It runs on the on-screen `gl` backend by default (headless remains available).
- It does not depend on PsychoPy or legacy eyetracker classes.
- Stimulus rendering uses backend draw commands rather than PsychoPy stimulus objects.

## Run

```bash
python examples/prf_seeg/main.py 001 1
```

By default this opens a fullscreen OpenGL window (`display.fullscreen: true` in `settings.yml`).
On first run it downloads the bitmap stimulus HDF5 configured in `settings.yml`.

With headless backend:

```bash
python examples/prf_seeg/main.py 001 1 --backend headless
```

Outputs are written under BIDS-like paths in `logs/`.

## Optional trigger output (EEG)

Enable `trigger_io.enabled: true` in `settings.yml`.

The run can emit configurable codes for:

- run start/end
- `barpass` / `blank` phase starts
- scanner `pulse` events
- participant `response` events
