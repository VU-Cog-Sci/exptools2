Godot Navigation Arena
======================

This example demonstrates a Godot subprocess experiment with:

- a circular arena
- hidden gem/reward targets
- distant mountain landmarks for orientation
- configurable encoding/retrieval/probe trial epochs

Runner entrypoint:

.. literalinclude:: ../../../examples/godot_navigation_experiment.py
   :language: python

Config:

.. literalinclude:: ../../../examples/configs/godot_navigation.yaml
   :language: yaml

Godot project notes:

- Scene: ``examples/godot_navigation/nav_arena.tscn``
- Script: ``examples/godot_navigation/scripts/nav_arena.gd``
