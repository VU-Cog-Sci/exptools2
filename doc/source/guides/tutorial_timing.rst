Detailed Timing Tutorial
========================

This page explains how timing works and how to reason about precision.

Core model
----------

Timing is anchored to a monotonic nanosecond origin ``t0_ns``.
The scheduler reserves absolute windows, so phase durations do not drift due to loop overhead.

Key components
--------------

- ``RunRequest.t0_ns``: absolute run origin
- ``NonSlipScheduler.reserve(duration_s)``: absolute phase windows
- ``DisplayBackend.flip(target_ns=...)``: target-based frame pacing
- ``RunLogger.log_flip(...)``: per-frame timing diagnostics

Why this avoids drift
---------------------

Relative loop timing accumulates error. Absolute deadlines do not:

.. code-block:: text

   bad: next = now + dt
   good: next = t0 + n * dt

The session runtime uses absolute target flips and periodically resynchronizes if the loop falls behind.

Practical precision checklist
-----------------------------

1. Use ``refresh_hz`` matching measured display rate.
2. Keep per-frame draw work bounded.
3. Inspect ``late_ns`` and dropped frame metrics in ``*_log.h5``.
4. For scanner synchronization, use ``scanner_trigger_mode`` and log pulses as ``SYNC``.

Timing-focused run config
-------------------------

.. code-block:: yaml

   run:
     backend: gl
     contract_version: "1.1"
     scanner_trigger_mode:
       mode: key
       params:
         key: "t"
   display:
     refresh_hz: 120
     vsync: true

Related code:

.. literalinclude:: ../../../exptools2/core/scheduler.py
   :language: python

.. literalinclude:: ../../../exptools2/core/session.py
   :language: python
