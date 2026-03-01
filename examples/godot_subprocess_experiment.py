"""Run a Godot-backed experiment from config using the run contract."""

from __future__ import annotations

import argparse

from exptools2.runner.run import run_from_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Path to JSON/YAML run config")
    args = parser.parse_args()

    result = run_from_config(args.config)
    print(result)


if __name__ == "__main__":
    main()
