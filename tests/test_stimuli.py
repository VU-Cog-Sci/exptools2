import numpy as np

from exptools2.backends.gl.stimuli import (
    ElementArraySpec,
    ElementArrayStimulus,
    GaborSpec,
    ImageSpec,
    ImageStimulus,
    make_gabor_grating,
)
from exptools2.core.types import DrawBatch


def test_gabor_reference_generation_has_expected_shape() -> None:
    img = make_gabor_grating(GaborSpec(), size_px=64)
    assert img.shape == (64, 64)
    assert np.isfinite(img).all()


def test_element_array_reproducible_with_seed() -> None:
    s1 = ElementArrayStimulus(ElementArraySpec(n_elements=4, seed=123))
    s2 = ElementArrayStimulus(ElementArraySpec(n_elements=4, seed=123))

    b1 = DrawBatch()
    b2 = DrawBatch()
    s1.enqueue(b1)
    s2.enqueue(b2)

    assert b1.commands[0].params["centers"] == b2.commands[0].params["centers"]


def test_image_stimulus_enqueues_texture_command() -> None:
    stim = ImageStimulus(ImageSpec(source="dummy.png", center=(0.1, -0.1), size=(0.4, 0.3)))
    batch = DrawBatch()
    stim.enqueue(batch)
    assert batch.commands[0].kind == "image"
    assert batch.commands[0].params["source"] == "dummy.png"
