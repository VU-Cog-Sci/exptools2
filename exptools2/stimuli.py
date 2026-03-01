"""Backend-agnostic stimulus conveniences.

For OpenGL-backed primitives, use exptools2.backends.gl.stimuli.
"""

from exptools2.backends.gl.stimuli import (
    ElementArraySpec,
    ElementArrayStimulus,
    GaborSpec,
    GaborStimulus,
    ImageSpec,
    ImageStimulus,
    LineSpec,
    LineStimulus,
    ShapeSpec,
    ShapeStimulus,
    TextSpec,
    TextStimulus,
    VideoSpec,
    VideoStimulus,
    make_gabor_grating,
)

__all__ = [
    "ElementArraySpec",
    "ElementArrayStimulus",
    "GaborSpec",
    "GaborStimulus",
    "ImageSpec",
    "ImageStimulus",
    "LineSpec",
    "LineStimulus",
    "ShapeSpec",
    "ShapeStimulus",
    "TextSpec",
    "TextStimulus",
    "VideoSpec",
    "VideoStimulus",
    "make_gabor_grating",
]
