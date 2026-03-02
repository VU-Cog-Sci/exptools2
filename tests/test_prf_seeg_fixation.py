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


def test_fixation_event_times_no_broadcast_shape_mismatch() -> None:
    module = _load_resolver()
    design_cfg = {
        "offset_ifi_duration": 1.0,
        "minimal_ifi_duration": 1.5,
        "gaussian_ifi_sd": 1.5,
        "exponential_ifi_mean": 1.5,
        "start_duration": 4.0,
    }
    events = module.create_fixation_event_times(
        total_time=488.0,
        design_cfg=design_cfg,
        seed=18,
    )
    assert events.ndim == 1
    assert events.size > 0
    assert float(events[0]) > design_cfg["start_duration"]
