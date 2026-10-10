#!/usr/bin/env bash
# ==============================================================================
# MHIDE STORY INTELLIGENCE — RUNNER SCRIPT
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure virtualenv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

# Run command inside virtualenv
exec .venv/bin/python -m app.main "$@"
