from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_resolver():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "examples" / "prf_seeg" / "main.py"
    spec = importlib.util.spec_from_file_location("prf_seeg_main_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dartboard_ring_fractions_use_full_mirrored_list() -> None:
    module = _load_resolver()
    settings = {
        "stimuli": {
            "aperture_radius": 0.95,
            "dartboard_outer_radius": 0.9,
            "dartboard_ring_fractions": [1.0, 0.75, 0.5, 0.25, 0.0, -0.25, -0.5, -0.75, -1.0],
        }
    }
    fx = module._resolve_fixation_spec(settings)
    assert fx.bullseye_radii == (0.9, 0.675, 0.45, 0.225)


def test_dartboard_ring_radii_clamped_to_aperture() -> None:
    module = _load_resolver()
    settings = {
        "stimuli": {
            "aperture_radius": 0.6,
            "dartboard_outer_radius": 0.95,
            "dartboard_ring_fractions": [1.0, 0.5, -0.5],
        }
    }
    fx = module._resolve_fixation_spec(settings)
    assert fx.bullseye_radii == (0.6, 0.3)


def test_bar_visible_when_duration_equals_interval() -> None:
    module = _load_resolver()
    assert module._bar_visible(0.0, bar_blank_duration=1 / 60, bar_blank_interval=1 / 60) is True
    assert module._bar_visible(0.5, bar_blank_duration=1 / 60, bar_blank_interval=1 / 60) is True


def test_bar_visible_periodic_blanking() -> None:
    module = _load_resolver()
    # First half of each interval: blank, second half: visible.
    assert module._bar_visible(0.01, bar_blank_duration=0.02, bar_blank_interval=0.04) is False
    assert module._bar_visible(0.03, bar_blank_duration=0.02, bar_blank_interval=0.04) is True
