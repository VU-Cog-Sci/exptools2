# Godot Navigation Arena Example

This example implements a basic Burgess/Doeller-style navigation paradigm:

- circular arena boundary
- hidden collectible gems/rewards
- distant mountain landmarks as allocentric orientation cues
- multi-epoch trial structure (orientation, encoding, retrieval, probe, rest)

The scene listens for `RUN_START` over UDP from `exptools2` and responds with:

- `EVENT` messages (e.g. `gem_collected`)
- `SYNC` pose markers
- `RUN_ENDED` with a world-trace file path

`exptools2` converts the emitted JSONL world trace into `<stem>_world.h5` and
adds it to the run manifest.

## Run

From repository root:

```bash
python examples/godot_navigation_experiment.py \
  --config examples/configs/godot_navigation.yaml
```

## Controls (in Godot window)

- `W A S D`: translate
- `Q / E`: rotate heading
- `ESC`: abort run

## Key config parameters

In `examples/configs/godot_navigation.yaml`:

- `duration_s`
- `arena_radius`
- `num_gems`
- `collection_radius`
- `mountain_distance`
- `show_gems`
- `trial_structure` (ordered epoch definitions)
- `display.monitor_index` (target display for fullscreen/window)
