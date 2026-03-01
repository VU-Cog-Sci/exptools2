"""Legacy fLoc entrypoint placeholder.

The previous PsychoPy-backed fLoc implementation is removed as part of the
hard API break. Rebuild localizers using the new core + backend contracts.
"""


class FLocSession:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "Legacy PsychoPy-based FLocSession is removed. "
            "Migrate to exptools2.runner + backend-agnostic trials."
        )
