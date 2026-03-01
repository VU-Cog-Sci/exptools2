from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from exptools2.media.images_to_hdf5 import convert_images_to_hdf5, parse_resize_token
from exptools2.runner.cli import main as runner_main


PIL = pytest.importorskip("PIL.Image")


def _write_png(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (12, 10)) -> None:
    data = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    data[:, :] = np.array(color, dtype=np.uint8)
    image = PIL.fromarray(data, mode="RGB")
    image.save(path)


def _write_gif(path: Path) -> None:
    frame_a = np.zeros((10, 12, 3), dtype=np.uint8)
    frame_a[:, :] = np.array([255, 0, 0], dtype=np.uint8)
    frame_b = np.zeros((10, 12, 3), dtype=np.uint8)
    frame_b[:, :] = np.array([0, 255, 0], dtype=np.uint8)

    im_a = PIL.fromarray(frame_a, mode="RGB")
    im_b = PIL.fromarray(frame_b, mode="RGB")
    im_a.save(path, save_all=True, append_images=[im_b], duration=40, loop=0)


def test_convert_images_to_hdf5_from_dir(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir(parents=True)
    _write_png(image_dir / "a.png", color=(10, 20, 30))
    _write_png(image_dir / "b.jpg", color=(40, 50, 60))
    _write_gif(image_dir / "c.gif")

    output = tmp_path / "out" / "stimuli.h5"
    result = convert_images_to_hdf5(
        inputs=[image_dir],
        output=output,
        resize=(16, 16),
        mode="rgb",
    )

    assert result["n_sources"] == 3
    assert result["n_frames"] == 4
    with h5py.File(output, "r") as h5f:
        data = h5f["stimuli"][:]
        assert tuple(data.shape) == (4, 16, 16, 3)
        source_index = json.loads(h5f["source_index_json"][()].decode("utf8"))
        assert len(source_index) == 4


def test_parse_resize_token() -> None:
    assert parse_resize_token("512x512") == (512, 512)
    assert parse_resize_token(" 640 x 480 ") == (640, 480)
    assert parse_resize_token(None) is None


def test_expctl_images_to_hdf5_subcommand(tmp_path: Path) -> None:
    image_dir = tmp_path / "imgs"
    image_dir.mkdir(parents=True)
    _write_png(image_dir / "one.png", color=(120, 10, 90))
    out_path = tmp_path / "converted.h5"

    exit_code = runner_main(
        [
            "images-to-hdf5",
            str(image_dir),
            "--output",
            str(out_path),
            "--resize",
            "8x8",
            "--mode",
            "rgb",
        ]
    )
    assert exit_code == 0
    assert out_path.exists()
