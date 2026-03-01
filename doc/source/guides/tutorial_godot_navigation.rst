Godot Navigation Tutorial
=========================

This tutorial covers:

1. installing Godot 4,
2. running the Burgess/Doeller-style navigation example,
3. choosing the target display/monitor from YAML.

Install Godot 4
---------------

Run the helper script from repository root:

.. code-block:: bash

   scripts/install_godot4.sh

The script supports macOS and Linux and tries package-manager installation
first, then falls back to an official portable build.

Create Python Environment
-------------------------

.. code-block:: bash

   scripts/create_env.sh --extras full,docs,dev
   source .venv/bin/activate

Run Navigation Experiment
-------------------------

.. code-block:: bash

   python examples/godot_navigation_experiment.py \
     --config examples/configs/godot_navigation.yaml

Controls in the Godot window:

- ``W A S D``: move
- ``Q / E``: rotate heading
- ``ESC``: abort

Trial Structure
---------------

The navigation config supports structured epochs via
``conditions.rows[0].trial_structure``.

Each trial entry can define:

- ``name``
- ``mode`` (for metadata)
- ``duration_s``
- ``num_gems``
- ``show_gems``
- ``reset_gems``
- ``allow_movement``
- ``allow_collection``

This enables encoding/retrieval/probe/rest sequences in a single run.

Monitor Selection (YAML)
------------------------

Set monitor in ``display``:

.. code-block:: yaml

   display:
     monitor_index: 1
     monitor_name: primary

Notes:

- For GLFW/OpenGL runs, ``monitor_index`` (if set) is used directly.
- For Godot subprocess runs, ``monitor_index`` is forwarded as ``--screen N``.
- ``monitor_name`` supports ``primary``, ``index:N``, a numeric string, or a
  monitor-name substring fallback.

Artifacts
---------

The Godot navigation example writes:

- core: ``<stem>_events.tsv``, ``<stem>_log.h5``, ``<stem>_manifest.json``
- Godot trace: ``<stem>_world_trace.jsonl`` (raw)
- converted world file: ``<stem>_world.h5``
