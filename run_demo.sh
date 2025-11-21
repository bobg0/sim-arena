#!/bin/bash
# Quick demo script for Sim-Arena MVP

set -e  # Exit on error

echo "=== Sim-Arena Demo ==="
echo ""

# Make sure we're in the right directory
cd "$(dirname "$0")"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Virtual environment not activated. Activating..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        echo "✅ Virtual environment activated"
    else
        echo "❌ Virtual environment not found. Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
fi

echo ""
echo "1. Running preflight checks..."
make preflight || echo "⚠️  Preflight had warnings, continuing..."

echo ""
echo "2. Cleaning namespace..."
make clean-ns || echo "⚠️  Clean had warnings, continuing..."

echo ""
echo "3. Running one agent step..."
echo "   This will:"
echo "   - Create a SimKube Simulation"
echo "   - Wait 60 seconds"
echo "   - Observe pod states"
echo "   - Apply policy (bump CPU if pods pending)"
echo "   - Compute reward"
echo "   - Log results"
echo ""

# Use virtual environment Python if available, otherwise use system python3
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

PYTHONPATH=. $PYTHON runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --seed 42

echo ""
echo "4. Results:"
echo "--- Last Step Record ---"
if [ -f runs/step.jsonl ]; then
    tail -1 runs/step.jsonl | python3 -m json.tool 2>/dev/null || tail -1 runs/step.jsonl
else
    echo "No step records found"
fi

echo ""
echo "--- Summary ---"
if [ -f runs/summary.json ]; then
    cat runs/summary.json | python3 -m json.tool 2>/dev/null || cat runs/summary.json
else
    echo "No summary found"
fi

echo ""
echo "=== Demo Complete ==="
echo ""
echo "To view cluster state:"
echo "  kubectl get pods -n test-ns"
echo "  kubectl get simulations"

