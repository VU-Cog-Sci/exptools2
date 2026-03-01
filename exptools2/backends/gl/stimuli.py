from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from exptools2.core.interfaces import Stimulus
from exptools2.core.types import DrawBatch


@dataclass(slots=True)
class GaborSpec:
    center: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (0.2, 0.2)
    orientation_deg: float = 0.0
    phase: float = 0.0
    spatial_freq: float = 2.0
    sigma: float = 0.4
    contrast: float = 1.0
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(slots=True)
class LineSpec:
    start: tuple[float, float] = (-0.5, 0.0)
    end: tuple[float, float] = (0.5, 0.0)
    width: float = 1.0
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)


@dataclass(slots=True)
class ShapeSpec:
    shape: str = "circle"
    center: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (0.2, 0.2)
    rotation_deg: float = 0.0
    fill_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    stroke_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    stroke_width: float = 0.0


@dataclass(slots=True)
class ElementArraySpec:
    n_elements: int
    base_spec: GaborSpec = field(default_factory=GaborSpec)
    centers: np.ndarray | None = None
    orientations_deg: np.ndarray | None = None
    phases: np.ndarray | None = None
    contrasts: np.ndarray | None = None
    seed: int = 0


@dataclass(slots=True)
class VideoSpec:
    source: str
    position: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (1.0, 1.0)
    loop: bool = False


@dataclass(slots=True)
class ImageSpec:
    source: str
    center: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (0.6, 0.6)
    rotation_deg: float = 0.0
    opacity: float = 1.0
    tint: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)


@dataclass(slots=True)
class TextSpec:
    text: str
    position: tuple[float, float] = (0.0, 0.0)
    size: float = 0.05
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)


class BaseStimulus(Stimulus):
    def __init__(self, kind: str, spec: Any):
        self.kind = kind
        self.spec = spec

    def update(self, params: dict) -> None:
        for key, value in params.items():
            if hasattr(self.spec, key):
                setattr(self.spec, key, value)

    def enqueue(self, batch: DrawBatch) -> None:
        batch.add(self.kind, **asdict(self.spec))


class GaborStimulus(BaseStimulus):
    def __init__(self, spec: GaborSpec | None = None):
        super().__init__(kind="gabor", spec=spec or GaborSpec())


class LineStimulus(BaseStimulus):
    def __init__(self, spec: LineSpec | None = None):
        super().__init__(kind="line", spec=spec or LineSpec())


class ShapeStimulus(BaseStimulus):
    def __init__(self, spec: ShapeSpec | None = None):
        super().__init__(kind="shape", spec=spec or ShapeSpec())


class TextStimulus(BaseStimulus):
    def __init__(self, spec: TextSpec):
        super().__init__(kind="text", spec=spec)


class ElementArrayStimulus(Stimulus):
    def __init__(self, spec: ElementArraySpec):
        self.spec = spec
        self._rng = np.random.default_rng(spec.seed)
        self._ensure_arrays()

    def _ensure_arrays(self) -> None:
        n = self.spec.n_elements
        if self.spec.centers is None:
            self.spec.centers = self._rng.uniform(-0.8, 0.8, size=(n, 2))
        if self.spec.orientations_deg is None:
            self.spec.orientations_deg = self._rng.uniform(0, 180, size=n)
        if self.spec.phases is None:
            self.spec.phases = self._rng.uniform(0, 2 * np.pi, size=n)
        if self.spec.contrasts is None:
            self.spec.contrasts = np.full(shape=n, fill_value=self.spec.base_spec.contrast)

    def update(self, params: dict) -> None:
        for key, value in params.items():
            if hasattr(self.spec, key):
                setattr(self.spec, key, value)
        self._ensure_arrays()

    def enqueue(self, batch: DrawBatch) -> None:
        self._ensure_arrays()
        base = asdict(self.spec.base_spec)
        batch.add(
            "element_array",
            n_elements=self.spec.n_elements,
            base_spec=base,
            centers=np.asarray(self.spec.centers).tolist(),
            orientations_deg=np.asarray(self.spec.orientations_deg).tolist(),
            phases=np.asarray(self.spec.phases).tolist(),
            contrasts=np.asarray(self.spec.contrasts).tolist(),
        )


class VideoStimulus(BaseStimulus):
    def __init__(self, spec: VideoSpec):
        super().__init__(kind="video", spec=spec)


class ImageStimulus(BaseStimulus):
    def __init__(self, spec: ImageSpec):
        super().__init__(kind="image", spec=spec)


def make_gabor_grating(spec: GaborSpec, size_px: int = 128) -> np.ndarray:
    """CPU reference Gabor used for testing/math validation."""
    xy = np.linspace(-1.0, 1.0, size_px)
    x, y = np.meshgrid(xy, xy)

    theta = np.deg2rad(spec.orientation_deg)
    xr = x * np.cos(theta) + y * np.sin(theta)
    carrier = np.sin(2 * np.pi * spec.spatial_freq * xr + spec.phase)
    gauss = np.exp(-(x**2 + y**2) / max(1e-8, 2 * spec.sigma * spec.sigma))
    img = carrier * gauss * spec.contrast
    return img.astype(np.float32)
