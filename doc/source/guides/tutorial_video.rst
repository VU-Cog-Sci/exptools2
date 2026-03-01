Video in Experiments Tutorial
=============================

This framework uses a dedicated video player interface and a draw-batch integration path.

Video pipeline
--------------

1. Open media with ``PyAVVideoPlayer.open(path, hwaccel=...)``.
2. Schedule start with ``schedule(start_ns)``.
3. Each frame, call ``enqueue(batch, now_ns)``.
4. Render queued video commands in the display backend.

Minimal example
---------------

.. literalinclude:: ../../../examples/video_playback_experiment.py
   :language: python

Hardware decode modes
---------------------

- ``auto``: let FFmpeg choose
- ``off``: force software decode
- ``videotoolbox``: macOS
- ``vaapi``: Linux Intel/AMD path
- ``nvdec``: NVIDIA path

Deterministic logging recommendations
-------------------------------------

When integrating into full runs, log per-frame:

- PTS (``pts_ns``)
- decoded frame index
- presented frame index
- dropped/repeated counters
- decode mode (hw/sw)

Notes
-----

- Keep decode on a worker thread (already done in ``PyAVVideoPlayer``).
- Do not stream every decoded frame across processes unless needed for closed-loop control.
