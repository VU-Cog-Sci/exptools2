from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run import run_from_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="expctl", description="exptools2 experiment runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run an experiment from a YAML config")
    run.add_argument("config", type=Path, help="Path to config.yaml")

    images = sub.add_parser(
        "images-to-hdf5",
        help="Convert bitmap image sequences (jpg/png/gif) to an HDF5 dataset",
    )
    images.add_argument("inputs", nargs="+", type=Path, help="Input files and/or directories")
    images.add_argument("--output", required=True, type=Path, help="Output HDF5 path")
    images.add_argument("--dataset", default="stimuli", help="HDF5 dataset name")
    images.add_argument("--recursive", action="store_true", help="Recursively scan directories")
    images.add_argument("--mode", choices=["rgb", "gray"], default="rgb", help="Output pixel mode")
    images.add_argument("--resize", default=None, help="Resize all frames: WIDTHxHEIGHT")
    images.add_argument("--limit", type=int, default=None, help="Maximum number of output frames")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_from_config(args.config)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "images-to-hdf5":
        from exptools2.media.images_to_hdf5 import convert_images_to_hdf5, parse_resize_token

        result = convert_images_to_hdf5(
            inputs=args.inputs,
            output=args.output,
            dataset=args.dataset,
            recursive=bool(args.recursive),
            mode=args.mode,
            resize=parse_resize_token(args.resize),
            limit=args.limit,
        )
        print(json.dumps(result, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
