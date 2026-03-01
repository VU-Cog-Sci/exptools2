EyeLink Integration
===================

`exptools2` includes optional EyeLink support via ``pylink``.

Overview
--------

When enabled, the EyeLink recorder:

- initializes tracker connection
- configures pixel coordinate mapping to the active GLFW framebuffer
- launches calibration/drift setup on the experiment window
- starts recording at ``RUN_STARTED``
- writes markers for phase starts and participant input
- downloads EDF to the BIDS-like output folder

Requirements
------------

- GL backend (``run.backend: gl``)
- SR Research ``pylink`` installed and importable in the runtime environment

If your lab installation is private, expose it via ``PYTHONPATH`` before running.

Config
------

.. code-block:: yaml

   run:
     backend: gl
     sub: "001"
     ses: "01"
     task: "demo"
     run: "01"
     output_root: logs
     seed: 42

   display:
     width: 1920
     height: 1080
     fullscreen: true
     hide_cursor: true

   eyelink:
     enabled: true
     address: "100.1.1.1"
     calibrate_on_start: true
     drift_correct_on_start: false
     sample_rate: 1000
     send_input_messages: true
     send_flip_messages: false
     options:
       calibration_type: HV9
       file_event_filter: "LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT"
       link_event_filter: "LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON"
       link_sample_data: "LEFT,RIGHT,GAZE,GAZERES,AREA,STATUS,HTARGET"

Outputs
-------

In addition to core run artifacts, EyeLink adds:

- ``<stem>_eyetrack.edf``
- ``<stem>_eyetrack.json``

Both are included in the run manifest.

