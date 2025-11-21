#!/bin/bash
# Quick setup: source this file to activate the venv and set PYTHONPATH
# Usage: source setup_env.sh

cd "$(dirname "${BASH_SOURCE[0]}")"
if [ -d ".venv" ]; then
    source .venv/bin/activate
    export PYTHONPATH="${PWD}:${PYTHONPATH}"
    echo "✓ Virtual environment activated"
    echo "✓ PYTHONPATH set to: $PYTHONPATH"
    echo "  You can now run: python3 runner/one_step.py ..."
else
    echo "✗ Virtual environment not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
fi
