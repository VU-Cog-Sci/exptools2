#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d ".venv" ]]; then
  echo "No .venv found. Run scripts/create_env.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! command -v sphinx-build >/dev/null 2>&1; then
  echo "sphinx-build not found. Install docs extras: pip install -e '.[docs]'" >&2
  exit 1
fi

make -C doc html

echo "Docs built at: doc/_build/html/index.html"
