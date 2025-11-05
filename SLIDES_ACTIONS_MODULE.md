# Actions Module - Slide Bullet Points

## Overview
- **Module**: `env/actions/` - Trace mutation operations
- **Purpose**: Load/edit/save MessagePack traces with safe, controlled mutations
- **Key Feature**: Pure file transformations (no cluster interaction)

---

## Core Components

### 1. Trace I/O (`trace_io.py`)
- **`load_trace(path)`**: Deserializes MessagePack → Python dict
- **`save_trace(obj, path)`**: Serializes Python dict → MessagePack
- Handles file validation, missing directories, binary I/O

### 2. Operations (`ops.py`)
- **`bump_cpu_small()`**: Increase CPU requests (default: +500m)
- **`bump_mem_small()`**: Increase memory requests (default: +256Mi)
- **`scale_up_replicas()`**: Increase replica count (default: +1)
- All return `True`/`False` to indicate success

### 3. CLI Tool (`sk-action`)
- Command: `sk-action apply --in <input> --out <output> --deploy <name> --op <operation>`
- Shows JSON diff of changes
- Saves unchanged file if deployment not found

---

## Implementation Details

### Navigation Strategy
- `_iter_deployments()`: Searches `events[].applied_objs[]` for matching Deployment
- `_first_container()`: Navigates `spec.template.spec.containers[0]`
- `_ensure_requests()`: Creates `resources.requests` if missing

### Value Handling
- **CPU**: Parses "500m" ↔ 500 millicores (converts cores to millicores internally)
- **Memory**: Parses "512Mi" ↔ bytes (handles binary units: Ki, Mi, Gi, Ti)
- Preserves original unit formatting when possible

### Safety Guarantees
- Returns `False` if deployment not found → trace unchanged
- Validates input types (deployment must be MutableMapping)
- Creates parent directories automatically

---

## Test Coverage

### Unit Tests (`test_ops.py`, `test_trace_io.py`)
- ✓ CPU/memory/replica mutations work correctly
- ✓ Deployment not found leaves trace unchanged (acceptance criteria)
- ✓ Roundtrip save/load preserves data
- ✓ Error handling for missing files

### Educational Tests (`test_ops_detailed.py`, `test_trace_io_detailed.py`)
- Step-by-step walkthroughs with extensive logging
- Visual structure diagrams
- Code interaction flow charts
- Suitable for presentations and learning

---

## Demo Workflow

1. **Create trace**: `demo/trace-0001.json` (synthetic example)
2. **Pack to MessagePack**: `demo/make_demo_trace.py`
3. **Apply mutation**: 
   ```bash
   sk-action apply --in demo/trace-0001.msgpack \
                   --out .tmp/trace-next.msgpack \
                   --deploy web --op bump_cpu_small
   ```
4. **View diff**: JSON output shows exact changes

---

## Key Design Decisions

- **Pure functions**: No side effects outside trace dictionary
- **In-place mutation**: Operations modify the dict directly
- **Unit preservation**: Maintains original formatting when possible
- **Explicit returns**: Boolean indicates whether any change occurred
- **MessagePack format**: Binary serialization for efficiency

---

## Acceptance Criteria Met

- ✓ `load_trace()` and `save_trace()` implemented
- ✓ Three mutation operations with safe defaults
- ✓ CLI tool with `apply` command
- ✓ Synthetic demo trace + packing script
- ✓ Unit tests for "deployment not found" case
- ✓ Diff output shows only intended changes

---

## Technical Stack

- **Python** with type hints
- **MessagePack** for binary serialization
- **argparse** for CLI
- **unittest** for testing
- **No Kubernetes API calls** (pure file operations)

