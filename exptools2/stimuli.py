from psychopy.visual import Circle


def create_circle_fixation(win, radius=0.1, color=(1, 1, 1),
                           edges=100, **kwargs):
    """ Creates a circle fixation dot with sensible defaults. """
    return Circle(win, radius=radius, color=color, edges=edges, **kwargs)