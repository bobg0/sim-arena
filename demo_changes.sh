#!/bin/bash
# Quick demo script to show the action_applier changes in action

set -e

echo "============================================================"
echo "Demo: Action Applier Changes"
echo "============================================================"
echo ""

# Activate venv if available
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo "Using virtual environment Python"
else
    PYTHON="python3"
    echo "Using system Python"
fi

echo ""
echo "1. Testing action_applier module..."
echo "   Applying bump_cpu_small action:"
echo ""

PYTHONPATH=. $PYTHON << 'PYTHON_SCRIPT'
from runner.action_applier import apply_action_from_policy

# Test 1: Bump CPU
print("Test 1: bump_cpu_small (step=250m)")
out1, info1 = apply_action_from_policy(
    'demo/trace-0001.msgpack',
    {'type': 'bump_cpu_small', 'step': '250m'},
    'web',
    output_path='.tmp/demo-bump-cpu.msgpack'
)
print(f"Output: {out1}")
print(f"Changed: {info1['changed']}")
print(f"Changes detected: {len(info1['diff'])}")
print()

# Test 2: Scale replicas
print("Loading original trace for next test...")
print()
print("Test 2: scale_up_replicas (delta=1)")
out2, info2 = apply_action_from_policy(
    'demo/trace-0001.msgpack',
    {'type': 'scale_up_replicas', 'delta': 1},
    'web',
    output_path='.tmp/demo-scale.msgpack'
)
print(f"Output: {out2}")
print(f"Changed: {info2['changed']}")
print(f"Changes detected: {len(info2['diff'])}")
print()

print("All tests completed successfully!")
PYTHON_SCRIPT

echo ""
echo "============================================================"
echo "2. Summary of changes:"
echo "============================================================"
echo ""
echo "Created new files:"
echo "  - env/actions/utils.py (shared utilities)"
echo "  - runner/action_applier.py (action application module)"
echo ""
echo "Modified files:"
echo "  - runner/one_step.py (uses action_applier)"
echo "  - sk-action.py (uses shared utilities)"
echo ""
echo "Benefits:"
echo "  - Eliminated ~70 lines of duplicate code"
echo "  - Single source of truth for action mappings"
echo "  - Automatic change detection and printing"
echo "  - Easier to maintain and extend"
echo ""
echo "For full details, see: CHANGES_SUMMARY.md"
echo ""

