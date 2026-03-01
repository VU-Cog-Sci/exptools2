Minimal Experiment Tutorial
===========================

This tutorial shows the smallest useful experiment in the new framework.

Goal
----

- one run
- one trial
- two phases
- BIDS-like output artifacts

Step 1: Create a run request and logger
---------------------------------------

.. code-block:: python

   import time
   from exptools2.core import RunRequest, ScannerTriggerMode, RunLogger

   request = RunRequest(
       bids_stem="sub-001_ses-01_task-minimal_run-01",
       condition_row={"experiment": "minimal"},
       seed=123,
       t0_ns=time.monotonic_ns(),
       scanner_trigger_mode=ScannerTriggerMode(mode="none"),
   )

   logger = RunLogger(output_root="logs", bids_stem=request.bids_stem, backend="headless")

Step 2: Create a session
------------------------

.. code-block:: python

   from exptools2.backends.headless import HeadlessDisplayBackend
   from exptools2.core import Session, DisplayConfig

   session = Session(
       request=request,
       backend=HeadlessDisplayBackend(),
       logger=logger,
       display_config=DisplayConfig(fullscreen=False, refresh_hz=60.0),
   )

Step 3: Add a trial
-------------------

.. code-block:: python

   from exptools2.core import ConditionTrial, Phase

   trial = ConditionTrial(
       trial_nr=0,
       phases=[
           Phase(name="fix", duration_s=0.5),
           Phase(name="stim", duration_s=0.5),
       ],
       condition_row={
           "draw_command": {
               "kind": "shape",
               "shape": "circle",
               "center": (0.0, 0.0),
               "size": (0.1, 0.1),
           }
       },
   )
   session.add_trial(trial)

Step 4: Run
-----------

.. code-block:: python

   result = session.run()
   print(result)

Expected outputs
----------------

The run writes:

- ``<stem>_events.tsv``
- ``<stem>_events.json``
- ``<stem>_log.h5``
- ``<stem>_manifest.json``

Still images
------------

Still images are implemented as a dedicated stimulus class:
``exptools2.backends.gl.ImageStimulus`` using a textured quad shader path.
See ``examples/image_stimulus_experiment.py`` for a full runnable example.

For a complete file, see:

.. literalinclude:: ../../../examples/basic_headless_experiment.py
   :language: python
