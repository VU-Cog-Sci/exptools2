from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

try:
    import h5py
except Exception as exc:  # pragma: no cover
    raise RuntimeError("h5py is required") from exc


SUPPORTED_BITMAP_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}


def _import_pillow() -> tuple[Any, Any]:
    try:
        from PIL import Image, ImageSequence
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for bitmap conversion") from exc
    return Image, ImageSequence


def parse_resize_token(token: str | None) -> tuple[int, int] | None:
    if token is None:
        return None
    clean = str(token).lower().strip().replace(" ", "")
    if "x" not in clean:
        raise ValueError("--resize must look like WIDTHxHEIGHT")
    width_str, height_str = clean.split("x", 1)
    width = int(width_str)
    height = int(height_str)
    if width <= 0 or height <= 0:
        raise ValueError("--resize values must be positive")
    return (width, height)


def iter_input_files(inputs: Sequence[Path], recursive: bool) -> list[Path]:
    out: list[Path] = []
    for item in inputs:
        if item.is_file():
            if item.suffix.lower() in SUPPORTED_BITMAP_EXTENSIONS:
                out.append(item)
            continue
        if item.is_dir():
            pattern = "**/*" if recursive else "*"
            for path in sorted(item.glob(pattern)):
                if path.is_file() and path.suffix.lower() in SUPPORTED_BITMAP_EXTENSIONS:
                    out.append(path)
    return sorted(out)


def load_frames(path: Path, mode: str, resize: tuple[int, int] | None) -> Iterable[np.ndarray]:
    image_mod, image_seq_mod = _import_pillow()
    with image_mod.open(path) as image:
        is_gif = path.suffix.lower() == ".gif" and getattr(image, "is_animated", False)
        frames = image_seq_mod.Iterator(image) if is_gif else [image]
        for frame in frames:
            converted = frame.convert(mode)
            if resize is not None:
                converted = converted.resize(
                    (resize[0], resize[1]),
                    resample=image_mod.Resampling.LANCZOS,
                )
            arr = np.asarray(converted, dtype=np.uint8)
            yield np.ascontiguousarray(arr)


def convert_images_to_hdf5(
    *,
    inputs: Sequence[str | Path],
    output: str | Path,
    dataset: str = "stimuli",
    recursive: bool = False,
    mode: str = "rgb",
    resize: tuple[int, int] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    source_paths = [Path(item).expanduser() for item in inputs]
    paths = iter_input_files(source_paths, recursive=recursive)
    if not paths:
        raise FileNotFoundError("No supported image files found")
    if mode not in {"rgb", "gray"}:
        raise ValueError("mode must be one of: rgb, gray")
    if limit is not None and int(limit) <= 0:
        raise ValueError("limit must be > 0 when provided")

    pil_mode = "RGB" if mode == "rgb" else "L"
    frames: list[np.ndarray] = []
    source_index: list[dict[str, int | str]] = []
    out_idx = 0

    for path in paths:
        local_idx = 0
        for frame in load_frames(path, mode=pil_mode, resize=resize):
            frames.append(frame)
            source_index.append(
                {
                    "out_index": out_idx,
                    "source_file": str(path),
                    "source_frame": local_idx,
                }
            )
            out_idx += 1
            local_idx += 1
            if limit is not None and out_idx >= int(limit):
                break
        if limit is not None and out_idx >= int(limit):
            break

    if not frames:
        raise RuntimeError("No frames decoded from input images")

    first_shape = tuple(frames[0].shape)
    for idx, frame in enumerate(frames):
        if tuple(frame.shape) != first_shape:
            raise ValueError(
                f"Frame shape mismatch at index {idx}: expected {first_shape}, got {tuple(frame.shape)}. "
                "Use --resize to enforce a common shape."
            )

    data = np.stack(frames, axis=0)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(output_path, "w") as h5f:
        ds = h5f.create_dataset(dataset, data=data, compression=6)
        ds.attrs["mode"] = mode
        ds.attrs["n_frames"] = int(data.shape[0])
        ds.attrs["height"] = int(data.shape[1])
        ds.attrs["width"] = int(data.shape[2])
        if data.ndim == 4:
            ds.attrs["channels"] = int(data.shape[3])
        h5f.create_dataset(
            "source_index_json",
            data=json.dumps(source_index, separators=(",", ":")).encode("utf8"),
        )

    return {
        "output": str(output_path),
        "dataset": dataset,
        "shape": list(data.shape),
        "dtype": str(data.dtype),
        "n_sources": len(paths),
        "n_frames": int(data.shape[0]),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a sequence of bitmap images (jpg/png/gif) to an HDF5 dataset."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Input image files and/or directories")
    parser.add_argument("--output", required=True, type=Path, help="Output HDF5 path")
    parser.add_argument("--dataset", default="stimuli", help="HDF5 dataset name (default: stimuli)")
    parser.add_argument("--recursive", action="store_true", help="Recursively scan input directories")
    parser.add_argument(
        "--mode",
        choices=["rgb", "gray"],
        default="rgb",
        help="Output pixel format",
    )
    parser.add_argument(
        "--resize",
        default=None,
        help="Resize all images to WIDTHxHEIGHT, e.g. 512x512",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of output frames",
    )
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    resize = parse_resize_token(args.resize)
    result = convert_images_to_hdf5(
        inputs=args.inputs,
        output=args.output,
        dataset=args.dataset,
        recursive=bool(args.recursive),
        mode=args.mode,
        resize=resize,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2))
    return 0

