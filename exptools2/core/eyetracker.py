"""Eyetracker integration hooks for the rewritten backend architecture.

The previous PsychoPy-based EyeLink implementation is intentionally removed.
Use the optional pylink integration under ``exptools2.eyelink``.
"""


class PylinkEyetrackerSession:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "PylinkEyetrackerSession was removed in the PsychoPy-free rewrite. "
            "Use exptools2.eyelink.EyeLinkRecorder with a GL session."
        )
