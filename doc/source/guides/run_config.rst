Run Configuration
=================

The main entrypoint is:

.. code-block:: bash

   expctl run config.yaml

Minimal config:

.. literalinclude:: ../../../demos/config_headless.yaml
   :language: yaml

Backend options:

- ``run.backend: headless`` for CI/offline contract validation.
- ``run.backend: gl`` for GLFW/OpenGL psychophysics rendering.
- ``run.backend: godot`` for subprocess world execution over UDP contract IPC.

Display and monitor options:

.. code-block:: yaml

   display:
     width: 1920
     height: 1080
     fullscreen: true
     monitor_index: 1      # preferred explicit monitor selector
     monitor_name: primary # fallback selector by name/index token

Monitor behavior:

- GLFW backend uses ``monitor_index`` if set, otherwise ``monitor_name``.
- ``monitor_name`` supports ``primary``, ``index:N``, numeric tokens, and
  case-insensitive substring matching against monitor names.
- Godot backend forwards ``display.monitor_index`` as ``--screen N`` when
  launching Godot.

EyeLink options (GL backend only):

.. code-block:: yaml

   eyelink:
     enabled: true
     address: "100.1.1.1"
     calibrate_on_start: true
     drift_correct_on_start: false
     sample_rate: 1000
     options:
       calibration_type: HV9

Trigger I/O options:

.. code-block:: yaml

   trigger_io:
     enabled: true
     mode: parallel
     pulse_width_ms: 1.0
     parallel:
       address: 0x0378
     codes:
       run_started: 5
       pulse: 1
       response: 20
     phase_codes:
       stim: 2

Prelude options (instruction + fixation wait):

.. code-block:: yaml

   prelude:
     enabled: true
     background_color: [0.5, 0.5, 0.5, 1.0]
     instruction:
       text: "Press SPACE to continue.\n\nFixate and press T to start."
       continue_keys: ["space"]
       timeout_s: null
       style:
         panel_width_fraction: 0.76
         panel_height_fraction: 0.54
         panel_fill: [0.07, 0.09, 0.12, 0.86]
         panel_border: [0.88, 0.9, 0.95, 0.34]
         text_color: [0.97, 0.98, 1.0, 1.0]
         font_size_px: 44
         line_spacing_px: 10
     fixation_wait:
       enabled: true
       start_keys: ["t"]
       color: [0.85, 0.85, 0.85, 1.0]
       extent: 0.03
       line_width_px: 2.0

Bitmap Sequence Conversion
--------------------------

You can convert a sequence of ``jpg/png/gif`` files into an HDF5 dataset from
the package CLI:

.. code-block:: bash

   expctl images-to-hdf5 examples/prf_seeg/stimuli \
     --output examples/prf_seeg/stimuli/custom_stims.h5 \
     --mode rgb --resize 512x512
