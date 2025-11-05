# Detailed Educational Tests

This directory contains comprehensive, beginner-friendly test suites with extensive logging that demonstrate how the actions module works.

## Test Files

### `test_ops_detailed.py`
Educational test suite for trace mutation operations. Shows:
- Trace structure visualization
- Step-by-step CPU bumping operations
- Memory unit conversions
- Replica scaling operations
- Safety checks (deployment not found)
- Multiple sequential mutations
- Code interaction flow diagrams

### `test_trace_io_detailed.py`
Educational test suite for MessagePack file operations. Shows:
- Save/load roundtrips
- Error handling for missing files
- Integration with operations (load → modify → save)
- Automatic directory creation

## Running the Tests

### Run with verbose output:
```bash
cd /home/bogao/sim-arena
python -m pytest tests/test_ops_detailed.py -v -s
python -m pytest tests/test_trace_io_detailed.py -v -s
```

Or using unittest directly:
```bash
python tests/test_ops_detailed.py
python tests/test_trace_io_detailed.py
```

The `-s` flag is important to see all the print statements!

## What These Tests Demonstrate

### For Slides/Presentations:

1. **Trace Structure**
   - How traces are organized (version, events, applied_objs)
   - Navigation through nested dictionaries
   - Location of deployment resources

2. **Operations Flow**
   - How `bump_cpu_small()` navigates the trace
   - Helper function responsibilities (_iter_deployments, _first_container, etc.)
   - Value parsing and formatting (CPU: "500m" ↔ 500 millicores)
   - Unit conversions (Memory: "512Mi" ↔ bytes)

3. **Safety Features**
   - Deployment not found → trace unchanged
   - Clear return values (True/False)
   - No side effects on missing deployments

4. **File Operations**
   - MessagePack serialization/deserialization
   - Roundtrip integrity
   - Error handling
   - Integration with operations module

## Output Format

Each test prints:
- Visual section dividers (══════, ──────)
- Step-by-step explanations
- Before/after comparisons
- Verification results
- Summary statistics

The output is designed to be suitable for:
- Learning the codebase
- Creating presentation slides
- Understanding the mutation workflow
- Debugging trace operations

