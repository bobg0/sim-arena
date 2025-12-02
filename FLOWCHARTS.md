# Sim-Arena Status Flowcharts

**Date**: Pre-Winter Break Status  
**Purpose**: Visual representation of current system state and remaining work

---

## Flowchart 1: Current System Status (What's Complete)

This flowchart shows the **working end-to-end flow** that is currently implemented and functional.

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT SYSTEM STATUS                        │
│                    (MVP - Fully Integrated)                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  Preflight  │  ✅ COMPLETE
│   Checks    │  - Check cluster connectivity
└──────┬──────┘  - Verify namespace exists
       │         - Verify SimKube CRD installed
       │
       ▼
┌─────────────┐
│ Pre-start   │  ✅ COMPLETE
│   Hook      │  - Clean namespace (delete all pods)
└──────┬──────┘  - Idempotent operation
       │
       ▼
┌─────────────┐
│   Create    │  ✅ COMPLETE
│ Simulation  │  - Create SimKube Simulation CR
│      CR     │  - Load trace from msgpack file
└──────┬──────┘  - Generate deterministic sim name
       │
       ▼
┌─────────────┐
│ Wait Fixed  │  ✅ COMPLETE
│  Duration   │  - Block for specified duration (e.g., 120s)
└──────┬──────┘  - Wait for simulation to run
       │
       ▼
┌─────────────┐
│  Observe    │  ✅ COMPLETE (Basic)
│  Cluster    │  - Read pod states via Kubernetes API
│   State     │  - Returns: {ready, pending, total}
└──────┬──────┘  - Filters by deployment name
       │
       ▼
┌─────────────┐
│   Policy    │  ⚠️  BASIC (Needs Enhancement)
│  Decision   │  - Simple heuristic: if pending > 0 → bump CPU
└──────┬──────┘  - Returns: {"type": "bump_cpu_small"} or {"type": "noop"}
       │         - Only one policy implemented
       │
       ▼
┌─────────────┐
│   Action    │  ✅ COMPLETE (Partial)
│ Application │  - bump_cpu_small: ✅ Works
└──────┬──────┘  - bump_mem_small: ✅ Implemented (not used in policy)
       │         - scale_up_replicas: ✅ Implemented (not used in policy)
       │         - No safeguards/guardrails yet
       │
       ▼
┌─────────────┐
│ Trace Update│  ✅ COMPLETE
│   & Save    │  - Load trace from file
└──────┬──────┘  - Apply action modifications
       │         - Save updated trace to .tmp/trace-next.msgpack
       │
       ▼
┌─────────────┐
│   Reward    │  ✅ COMPLETE (Basic)
│ Computation │  - Binary reward: 1 if target met, 0 otherwise
└──────┬──────┘  - Target: ready == target_total && pending == 0
       │         - No penalty for over-allocation yet
       │
       ▼
┌─────────────┐
│    Log      │  ✅ COMPLETE
│  Results    │  - Write to runs/step.jsonl (one record per step)
└──────┬──────┘  - Update runs/summary.json (aggregated stats)
       │         - Includes: obs, action, reward, timestamps
       │
       ▼
┌─────────────┐
│  Cleanup    │  ✅ COMPLETE
│  Simulation │  - Delete Simulation CR
└─────────────┘  - Best-effort cleanup in finally block

═══════════════════════════════════════════════════════════════════

LEGEND:
✅ = Fully implemented and working
⚠️  = Basic implementation, needs enhancement
❌ = Not implemented

CURRENT CAPABILITIES:
- End-to-end single step execution works
- Can run with demo trace (trace-0001.msgpack)
- Basic observation and reward computation
- Simple policy (heuristic-based)
- One action type (bump_cpu_small) integrated
- Logging and cleanup functional

LIMITATIONS:
- Only one policy (simple heuristic)
- No policy selection mechanism
- No safeguards/guardrails
- Only one trace available (demo trace)
- Binary reward only (no penalties)
- No batch processing
- Limited error handling messages
```

---

## Flowchart 2: Remaining Work (What Needs to Be Done)

This flowchart shows the **enhancements and features** that need to be implemented before/during spring semester.

```
┌─────────────────────────────────────────────────────────────────┐
│                    REMAINING WORK                                │
│              (Pre-Break + Spring Semester)                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    CRITICAL PATH (Before Break)                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  Preflight  │  ⚠️  ENHANCE
└──────┬──────┘  - Add explicit error messages
       │         - Include "how to fix" suggestions
       │         - Better cluster failure diagnostics
       │
       ▼
┌─────────────┐
│   Policy    │  ❌ IMPLEMENT
│   System    │  - Create runner/policies.py
└──────┬──────┘  - Implement multiple policies:
       │           • always_bump_cpu()
       │           • always_bump_memory()
       │           • scale_replicas()
       │           • random policy
       │           • noop policy
       │         - Add --policy CLI argument
       │         - Policy selection mechanism
       │
       ▼
┌─────────────┐
│ Safeguards  │  ❌ IMPLEMENT
│ / Guardrails│  - Create runner/safeguards.py
└──────┬──────┘  - Max CPU per container (e.g., 16 CPUs)
       │         - Max memory per container (e.g., 32GB)
       │         - Max replicas (e.g., 100)
       │         - Validate before action application
       │         - Return clear error messages
       │
       ▼
┌─────────────┐
│ Trace       │  ❌ GENERATE
│ Generation  │  - Create demo/generate_traces.py
└──────┬──────┘  - Generate 50-100 trace variations
       │         - Insufficient resource errors:
       │           • >16 CPUs requested
       │           • >32GB memory requested
       │           • Mixed CPU/memory issues
       │         - Convert JSON → msgpack
       │         - Create demo/canonical/ directory
       │
       ▼
┌─────────────┐
│ Trace       │  ⚠️  VERIFY
│ Update Flow │  - Verify trace loads from ops
└──────┬──────┘  - Confirm trace modifications persist
       │         - Test trace update between episodes
       │         - Add logging for trace flow
       │
       ▼
┌─────────────┐
│   Reward    │  ⚠️  ENHANCE
│   Function  │  - Add non-binary reward variants:
└──────┬──────┘    • Penalty for exceeding node capacity
       │           • Gradual penalty for resource waste
       │           • Negative reward for over-allocation
       │         - Add --reward-mode CLI argument
       │         - Keep binary as baseline
       │
       ▼
┌─────────────┐
│ Namespace   │  ⚠️  TEST
│ Lifecycle   │  - Verify idempotent behavior
└──────┬──────┘  - Test 5 consecutive runs
       │         - Ensure no leftover pods
       │         - Document cleanup guarantees
       │
       ▼
┌─────────────┐
│   Demo      │  ❌ CREATE
│   Script    │  - Create demo/walkthrough.sh
└──────┬──────┘  - End-to-end reproducible script
       │         - Update DEMO_GUIDE.md
       │         - Test with hand-coded policies
       │

═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│                    HIGH PRIORITY (Before Break)                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  Multiple   │  ❌ IMPLEMENT
│   Traces    │  - Test with 5-10 different traces
└──────┬──────┘  - Verify loop behavior is stable
       │         - Document bugs if found
       │         - Test trace variety
       │
       ▼
┌─────────────┐
│  Action     │  ⚠️  VALIDATE
│ Validation  │  - Test all actions with new traces
└──────┬──────┘  - Verify edge cases:
       │           • Deployment not found
       │           • Invalid resource values
       │           • Missing fields in trace
       │
       ▼
┌─────────────┐
│ Observation │  ⚠️  VERIFY
│ Correctness │  - Test ready/pending/total across scenarios
└──────┬──────┘  - Verify with various resource-error traces
       │         - Document edge cases
       │
       ▼
┌─────────────┐
│  Batch Run  │  ❌ CREATE
│   Script    │  - Create scripts/batch_run_traces.sh
└──────┬──────┘  - Run one_step over directory of traces
       │         - Preflight once before batch
       │         - Handle errors gracefully
       │         - Collect/aggregate results
       │

═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│                    MEDIUM PRIORITY (Polish)                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│ Architecture│  ❌ CREATE
│   Diagram   │  - Create docs/images/system-architecture.png
└──────┬──────┘  - Show components and data flows
       │         - Label all components
       │         - Ready for mid-year update
       │
       ▼
┌─────────────┐
│ Canonical   │  ❌ SELECT
│   Traces    │  - Select 3-4 representative traces
└──────┬──────┘  - Copy to demo/canonical/
       │         - Document what each demonstrates
       │
       ▼
┌─────────────┐
│Troubleshoot │  ❌ WRITE
│   Notes     │  - Create docs/TROUBLESHOOTING.md
└──────┬──────┘  - Explain common runner errors
       │         - Document cleanup problems
       │         - Include "how to restart" guide
       │

═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENTATION (Before Break)                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│ Mid-Year    │  ❌ WRITE
│   Update    │  - Create docs/MID_YEAR_UPDATE.md
└──────┬──────┘  Sections:
       │         - Architecture Overview (Cate)
       │         - System State & Integration (Omar)
       │         - Trace Generation & Format (Bob)
       │         - Reproducibility & Setup (Rui)
       │         - Next Steps (Diya)
       │         - Demo Walkthrough (Diya)
       │
       ▼
┌─────────────┐
│ Trace Format│  ❌ DOCUMENT
│   Docs      │  - Create docs/TRACE_FORMAT.md
└──────┬──────┘  - Document JSON structure
       │         - Explain generation process
       │         - Include examples/templates
       │         - Document msgpack conversion
       │
       ▼
┌─────────────┐
│ Personal    │  ❌ WRITE
│ Reflection  │  - Create docs/PERSONAL_REFLECTIONS.md
└──────┬──────┘  - Each person: 1-2 paragraphs
       │         - What learned, challenges, contributions
       │

═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│                    SPRING SEMESTER (Future)                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│ Learning    │  🔮 FUTURE
│   Agents    │  - Replace hand-coded policies with RL agents
└──────┬──────┘  - DQN, PPO, or other RL algorithms
       │         - Train on generated traces
       │         - Evaluate performance
       │
       ▼
┌─────────────┐
│ State/Action│  🔮 FUTURE
│   Space     │  - Formalize state representation
└──────┬──────┘  - Define action space
       │         - Design reward shaping
       │
       ▼
┌─────────────┐
│ Multi-Error │  🔮 FUTURE
│   Types     │  - Expand beyond insufficient-resources
└──────┬──────┘  - Handle other error types
       │         - More complex scenarios
       │

═══════════════════════════════════════════════════════════════════

LEGEND:
✅ = Complete
⚠️  = In Progress / Needs Enhancement
❌ = Not Started
🔮 = Future Work

PRIORITY LEVELS:
- Critical Path: Must complete before break
- High Priority: Should complete before break
- Medium Priority: Polish and documentation
- Spring Semester: Future enhancements
```

---

## Summary

### What's Working Now (MVP Complete)
- ✅ End-to-end single step execution
- ✅ Preflight, hooks, simulation creation
- ✅ Basic observation and reward
- ✅ Simple policy (heuristic)
- ✅ One action type (bump_cpu_small)
- ✅ Logging and cleanup

### What Needs to Be Done

**Before Break (Critical):**
1. Implement real policy system (multiple policies)
2. Add safeguards/guardrails
3. Generate 50-100 traces
4. Enhance reward function
5. Verify trace update flow
6. Test namespace lifecycle
7. Create demo script

**Before Break (High Priority):**
1. Test with multiple traces
2. Validate actions
3. Verify observations
4. Create batch run script

**Before Break (Documentation):**
1. Mid-year update document
2. Trace format documentation
3. Troubleshooting guide
4. Architecture diagram
5. Personal reflections

**Spring Semester:**
1. Replace hand-coded policies with learning agents
2. Formalize state/action space
3. Expand to multiple error types

---

**Last Updated**: Pre-Winter Break  
**Next Review**: After break, before spring semester

