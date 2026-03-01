# Migration to PsychoPy-free exptools2

This rewrite is a hard API break.

## Removed

- PsychoPy-based `Session`, `Trial`, and eye tracker integrations.
- PsychoPy dependency from install requirements.

## New modules

- `exptools2.core`: contract, scheduler, session runtime, logger, BIDS helpers.
- `exptools2.backends.gl`: GLFW/OpenGL backend and shader stimulus specs.
- `exptools2.backends.godot`: subprocess + UDP contract integration.
- `exptools2.media`: video playback interfaces (PyAV implementation).
- `exptools2.audio`: PTB-like API with psychtoolbox/PortAudio engines.
- `exptools2.runner`: `expctl run config.yaml` CLI.

## New required outputs per run

- `<stem>_events.tsv`
- `<stem>_events.json`
- `<stem>_log.h5`
- `<stem>_manifest.json`

## Minimal migration strategy

1. Define a run config YAML and switch entrypoint to `expctl run config.yaml`.
2. Move trial condition tables to `conditions.path` (TSV/HDF5) or `conditions.rows`.
3. Use backend-specific stimuli via `exptools2.backends.gl.stimuli`.
4. For Godot experiments, wire your scene to the UDP run contract.
