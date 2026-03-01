#!/usr/bin/env bash
set -euo pipefail

ENV_DIR=".venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXTRAS="full,docs,dev"
EDITABLE=1

usage() {
  cat <<USAGE
Usage: scripts/create_env.sh [options]

Options:
  --env-dir PATH        Virtualenv directory (default: .venv)
  --python BIN          Python executable to use (default: python3)
  --extras LIST         Optional extras list for install, comma-separated
                        (default: full,docs,dev)
  --no-editable         Install as regular package instead of editable
  --help                Show this help

Examples:
  scripts/create_env.sh
  scripts/create_env.sh --env-dir .venv-exp --extras full,docs
  scripts/create_env.sh --python python3.11 --extras full
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-dir)
      ENV_DIR="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --extras)
      EXTRAS="$2"
      shift 2
      ;;
    --no-editable)
      EDITABLE=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -d "$ENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$ENV_DIR"
fi

# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel

if [[ "$EDITABLE" -eq 1 ]]; then
  python -m pip install -e ".[$EXTRAS]"
else
  python -m pip install ".[$EXTRAS]"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: ffmpeg not found on PATH. Video decoding features may be unavailable."
fi

if ! python - <<'PY' >/dev/null 2>&1
import sounddevice
PY
then
  echo "Warning: sounddevice/PortAudio runtime check failed. Audio playback may be unavailable."
fi

echo
echo "Environment ready."
echo "Activate it with: source $ENV_DIR/bin/activate"
echo "Run an experiment with: expctl run demos/config_headless.yaml"
