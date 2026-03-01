"""Launch the Godot navigation arena example through the exptools2 runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exptools2.runner.run import run_from_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "configs" / "godot_navigation.yaml",
        help="Path to run config (YAML/JSON)",
    )
    args = parser.parse_args()

    result = run_from_config(args.config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
