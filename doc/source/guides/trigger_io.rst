Trigger I/O (Parallel / Serial)
================================

For EEG-style hardware marking, `exptools2` supports optional trigger output via
the ``trigger_io`` recorder.

Capabilities
------------

- parallel port pulses (LPT; module ``parallel``)
- serial-port trigger bytes/lines (module ``pyserial``)
- code emission on run start/end, phase start, pulse, response, and abort

Config example
--------------

.. code-block:: yaml

   trigger_io:
     enabled: true
     mode: parallel        # parallel | serial | both
     pulse_width_ms: 1.0
     auto_zero: true
     parallel:
       address: 0x0378
     serial:
       port: null
       baudrate: 115200
       write_mode: byte
     codes:
       run_started: 5
       run_ended_ok: 250
       abort: 255
       pulse: 1
       response: 20
     phase_codes:
       barpass: 2
       blank: 3

Notes
-----

- Set ``dry_run: true`` to verify configuration/logging without touching hardware.
- Trigger artifacts are saved as:

  - ``<stem>_triggers.jsonl``
  - ``<stem>_triggers.json``

