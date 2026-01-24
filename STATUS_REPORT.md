# Sim-Arena Next Phase Status Report

**Date**: Spring Semester 2026  
**Context**: Post-MVP integration complete; traces generated, policies implemented  
**Goal**: Add safeguards, prepare demos, continue integration work

---

## Meeting Guidance Summary

### From Erin's Meeting:
- ✅ Finish integration testing
- ✅ Create a **working** agent–simulation loop
- ✅ Build a simple hand-coded or random agent
- ⚠️ **Keep scope narrow** — focus on *one* error type
- ⚠️ Prepare for break by documenting system state
- ⚠️ Ensure future you knows how to restart

### From David's Meeting:
- ✅ Generate multiple traces of the *same* insufficient-resources error (100 traces complete)
- ✅ Implement **real actions** (bump_cpu, bump_mem, scale_replicas complete)
- ✅ Define state and action space (policies + observations complete)
- ✅ Fill in the "empty shells" inside modules (mostly complete)
- ⚠️ Prepare demo
- ✅ Complete mid-year update

### Current Status:
- ✅ MVP is fully integrated
- ✅ Real logic implemented (policies, actions, observations)
- ⚠️ Remaining: safeguards, demos, testing across traces

---

## Task Assignments (1–1.5 Weeks)

---

## **DIYA — Integration + Arena Behavior**

### Task 1: Implement Real Policy Behavior Inside the Loop
**Status**: ✅ Complete  
**Priority**: High  
**Files Modified**:
- `runner/one_step.py` — Simplified action application (removed action_applier.py) ✅
- `runner/policies.py` — Added all required policies ✅

**Deliverables**:
- [x] Replace current simple policy with configurable policy system ✅
- [x] Implement at least 3 policies:
  - [x] `always_bump_cpu()` — Always increments CPU requests ✅
  - [x] `always_bump_memory()` — Always increments memory requests ✅
  - [x] `scale_replicas()` — Always scales up replicas ✅
- [x] Add policy selection mechanism (CLI arg or config) ✅ `--policy` argument exists
- [x] These policies needed to test reward + environment interactions (per Erin) ✅

**Bonus Improvements**:
- Enhanced `policy_random` to select from all 4 action types (not just 2)
- Simplified codebase: removed action_applier.py, inlined logic into one_step.py
- Removed 11 dead/broken files (~572 lines of code)
- Created comprehensive README.md (685 lines)

**Acceptance Criteria**:
- ✅ `python runner/one_step.py --policy bump_cpu ...` works
- ✅ Each policy produces different trace modifications
- ✅ Policies can be tested independently

---

### Task 2: Add Safeguard Logic / Hard Caps
**Status**: ✅ Complete  
**Priority**: High  
**Files Modified**:
- `runner/one_step.py` — Added current state extraction and validation before action application ✅
- `runner/safeguards.py` — Validation logic (already existed) ✅
- `test_safeguards.py` — Test suite to verify safeguards work ✅

**Deliverables**:
- [x] Prevent actions that allocate absurd resources (e.g., 100 CPUs, 1TB memory) ✅
- [x] Implement simple guardrails:
  - Maximum CPU per container: 16 CPUs (16000m) ✅
  - Maximum memory per container: 32GB (34359738368 bytes) ✅
  - Maximum replicas: 100 ✅
- [x] Return clear error messages when actions are blocked ✅
- [x] Add validation before action application in `one_step()` ✅

**Implementation Details**:
- Extracts current CPU/memory/replicas from trace before validation
- Validates that (current + delta) doesn't exceed hard caps
- Blocked actions return unchanged trace with `blocked: true` flag
- All tests pass (CPU, memory, replicas, noop, parsing)

**Acceptance Criteria**:
- ✅ Attempting to allocate >16 CPUs returns error/blocks action
- ✅ Agent cannot issue impossible requests
- ✅ Guardrails prevent infinite resource allocation
- ✅ Test suite validates all edge cases

---

### Task 3: Prepare Combined System Demo
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Create/Modify**:
- `demo/walkthrough.sh` or `demo/end_to_end_demo.sh` — Clean reproducible script
- Update `DEMO_GUIDE.md` — Document the walkthrough

**Deliverables**:
- [ ] Create clean, reproducible walkthrough script:
  - `create` → `wait` → `observe` → `agent action` → `reward` → `cleanup`
- [ ] Fix any integration rough edges discovered
- [ ] Ensure demo works with hand-coded policies
- [ ] Document demo in `DEMO_GUIDE.md`

**Acceptance Criteria**:
- Script runs end-to-end without manual intervention
- Demo shows working agent loop
- Clean output/logging for presentation

---

## **OMAR — Runner Internals + Testing**

### Task 1: Complete Internal Logic for Observation → Action → Trace Update
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Modify**:
- `runner/one_step.py` — Verify trace update flow (lines ~145-180)
- Ensure proper sequencing and state management

**Deliverables**:
- [ ] Verify runner loads updated trace from Bob's ops and writes it back
- [ ] Confirm proper sequencing:
  - `pre_start` → `create` → `wait` → `observe` → `apply action` → `compute reward` → `cleanup`
- [ ] Ensure trace modifications persist between episodes
- [ ] Add logging to verify trace update flow

**Acceptance Criteria**:
- Trace file is updated after action application
- Next episode uses updated trace
- Logging shows trace modification steps

---

### Task 2: Add Multiple Policy Plug-ins
**Status**: ✅ Complete  
**Priority**: Medium  
**Files to Modify**:
- `runner/one_step.py` — Policy selection mechanism ✅ DONE
- `runner/policies.py` (coordinate with Diya) — Policy implementations ✅ DONE

**Deliverables**:
- [x] Let runners select between policies:
  - [x] `noop` — No action ✅
  - [x] `random` — Random action selection ✅
  - [x] `always_bump_cpu` — Always bump CPU (from Diya) ✅
  - [x] `always_bump_memory` — Always bump memory (from Diya) ✅
- [x] Policy selection via CLI argument: `--policy <name>` ✅
- [x] Needed to "fill in" empty agent shell (per Erin) ✅

**Acceptance Criteria**:
- `--policy noop` runs without errors
- `--policy random` selects random actions
- Each policy produces different behavior

---

### Task 2: Validate Action Correctness Across New Traces
**Status**: ✅ Complete  
**Priority**: High  
**Files Modified**:
- `env/actions/ops.py` — All action functions verified ✅
- `tests/test_ops.py` — Tests with traces added ✅

**Deliverables**:
- [x] Verify `bump_cpu_small`, `bump_mem_small`, `scale_up_replicas` work with new traces ✅
- [x] Confirm each delegate returns `False` gracefully if invalid ✅
- [x] Test edge cases (deployment not found, invalid values, missing fields) ✅

**Acceptance Criteria**:
- ✅ All actions produce valid updated traces
- ✅ Invalid inputs handled gracefully
- ✅ Tests pass with new trace set

---

### Task 4: Write Small Troubleshooting Notes
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files to Create**:
- `docs/TROUBLESHOOTING.md` or `README_TROUBLESHOOTING.md`

**Deliverables**:
- [ ] Explain common runner errors
- [ ] Document clean-up problems for January restart
- [ ] Include "how to restart" guide (per Erin's advice)

**Acceptance Criteria**:
- Future you (or team) can debug common issues
- Clear restart instructions

---

## **CATE — Observations, Reward, System Diagram**

### Task 1: Refine and Finalize Reward Function for Real Tests
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Modify**:
- `observe/reward.py` — Enhance reward function (current: binary)

**Deliverables**:
- [ ] Evaluate whether wasteful solutions should get lower reward (Erin + David)
- [ ] Propose and test at least *one* non-binary variant:
  - Penalty for exceeding node capacity (hard cap from Diya)
  - Gradual penalty based on resource waste
  - Negative reward for over-allocation
- [ ] Keep binary reward as baseline
- [ ] Add configurable reward mode: `--reward-mode binary|gradual|penalty`

**Acceptance Criteria**:
- At least one non-binary reward variant implemented
- Reward function tested with real traces
- Over-allocation penalized appropriately

---

### Task 2: Improve and Finalize System Architecture Diagram
**Status**: 🔄 In Progress  
**Priority**: Medium  
**Files to Create/Modify**:
- `docs/ARCHITECTURE.md` — System architecture documentation
- Create diagram: `docs/images/system-architecture.png` or `.svg`

**Deliverables**:
- [ ] Cleaned-up architecture diagram showing:
  - Different boxes (components)
  - Component flows
  - Data flow
- [ ] Diagram ready for mid-year update
- [ ] Erin suggested formalizing architecture

**Acceptance Criteria**:
- Clear visual representation of system
- All components labeled
- Data flows indicated

---

### Task 3: Verify Observation Correctness Across Traces
**Status**: 🔄 In Progress  
**Priority**: Medium  
**Files to Modify**:
- `observe/reader.py` — Verify observation logic
- `tests/test_observe.py` — Add trace-based tests

**Deliverables**:
- [ ] Check that `ready/pending/total` values behave sensibly across scenarios
- [ ] Test with various resource-error traces (from Bob)
- [ ] Document any edge cases found

**Acceptance Criteria**:
- Observations correct across all test traces
- Edge cases documented


---

## **BOB — Trace Generation + Action Validation**

### Task 1: Generate Multiple Insufficient-Resource Traces (Core Requirement)
**Status**: ✅ Complete  
**Priority**: Critical  
**Files to Create/Modify**:
- `demo/generate_traces.py` — Script to generate trace variations ✅ DONE
- `demo/traces/` — Directory for generated traces ✅ DONE
- Use existing: `demo/make_demo_trace.py` as reference ✅

**Deliverables**:
- [x] Create **50–100 variations** by templating CPU/memory fields ✅ (100 traces generated)
- [x] Errors should exceed node capacity:
  - >16 CPUs requested ✅
  - >32GB memory requested ✅
  - Combinations of both ✅
- [x] Convert JSON → msgpack using existing tooling ✅
- [x] Per David: generate multiple traces of the *same* error type ✅

**Acceptance Criteria**:
- 50+ trace files in `demo/traces/` directory
- Each trace has insufficient resources
- All traces loadable (msgpack format)
- Traces cover variety: very bad, slightly bad, mixed errors

---

### Task 2: Validate Action Correctness Across New Traces
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Modify**:
- `env/actions/ops.py` — Verify all action functions
- `tests/test_ops.py` — Add tests with new traces

**Deliverables**:
- [ ] Verify `bump_cpu_small`, `bump_mem_small`, `scale_up_replicas` work with new traces
- [ ] Confirm each delegate returns `False` gracefully if invalid
- [ ] Test edge cases:
  - Deployment not found
  - Invalid resource values
  - Missing fields in trace

**Acceptance Criteria**:
- All actions produce valid updated traces
- Invalid inputs handled gracefully
- Tests pass with new trace set

---

### Task 3: Prepare 3–4 Canonical Traces for Team Demo
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files to Create**:
- `demo/canonical/` — Directory for demo traces
- Recommended traces:
  - `canonical-very-bad-cpu.msgpack`
  - `canonical-very-bad-memory.msgpack`
  - `canonical-slightly-bad-cpu.msgpack`
  - `canonical-mixed-errors.msgpack`

**Deliverables**:
- [ ] Select 3–4 representative traces from generated set
- [ ] Copy to `demo/canonical/` directory
- [ ] Document what each trace demonstrates

**Acceptance Criteria**:
- 3–4 traces ready for demo
- Each trace represents different error scenario
- Traces documented

---

### Task 4: Document Trace Format + How to Generate More
**Status**: ✅ Complete  
**Priority**: Medium  
**Files Created**:
- `demo/generate_traces.py` — Trace generation script with documentation ✅

**Deliverables**:
- [x] Document trace JSON structure (in script comments) ✅
- [x] Explain how to generate new traces (script is self-documenting) ✅
- [x] Include examples and templates (100 trace variations generated) ✅
- [x] Document msgpack conversion process ✅

**Acceptance Criteria**:
- ✅ New team member can generate traces using the script
- ✅ Format documented in code
- ✅ 100 example traces provided

---

## **RUI — Hooks, Preflight, Setup, Cleanup**

### Task 1: Test and Finalize Namespace Lifecycle for Repeated Agent Runs
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Modify**:
- `ops/hooks.py` — Verify idempotency
- `Makefile` — Ensure `make clean-ns` works reliably
- Test end-to-end: repeated runs

**Deliverables**:
- [ ] Verify idempotent behavior (per Erin):
  - `make clean-ns` → run agent → run again → clean → no leftover pods
- [ ] Test repeated runs:
  - Run agent 5 times in a row
  - Each run should clean up properly
  - No namespace pollution
- [ ] Document clean-up guarantees

**Acceptance Criteria**:
- 5 consecutive runs leave no leftover pods
- `make clean-ns` is fully idempotent
- Namespace returns to clean state

---

### Task 2: Automate Environment Setup for Multi-Trace Batch Runs
**Status**: 🔄 In Progress  
**Priority**: Medium  
**Files to Create**:
- `scripts/batch_run_traces.sh` — Script to run one_step over directory of traces
- Coordinate with Omar for runner integration

**Deliverables**:
- [ ] Write script to run `one_step` over directory of traces
- [ ] Ensure preflight catches all cluster/CRD issues before batch
- [ ] Handle errors gracefully (skip failed traces, continue)
- [ ] Collect results from batch run

**Acceptance Criteria**:
- Script runs all traces in directory
- Preflight runs once before batch
- Failed traces don't stop entire batch
- Results collected/aggregated

---

### Task 3: Add Explicit Error Messaging for Cluster Failures
**Status**: 🔄 In Progress  
**Priority**: Medium  
**Files to Modify**:
- `ops/preflight.py` — Improve error messages

**Deliverables**:
- [ ] Make preflight outputs more helpful (per Erin's advice)
- [ ] Add specific error messages for:
  - Cluster not accessible
  - Namespace missing
  - CRD not installed
  - Permissions issues
- [ ] Include "how to fix" suggestions

**Acceptance Criteria**:
- Preflight errors are self-explanatory
- "Future you" can debug cluster issues
- Clear fix suggestions provided

---

## Integration Checklist

### Spring 2026 Priority Tasks:
- [ ] **Diya**: Prepare demo script (Task 3) — NEXT TASK
- [ ] **Omar**: Verify trace update flow (Task 1)
- [ ] **Cate**: Finalize reward function (Task 1)
- [ ] **Rui**: Verify namespace lifecycle (Task 1)
- [ ] **Rui**: Batch run script (Task 2)

### Completed Tasks:
- [x] **Bob**: Generate 50+ traces ✅ (100 traces generated)
- [x] **Bob**: Validate action correctness ✅
- [x] **Bob**: Document trace format ✅
- [x] **Diya**: Implement real policies ✅
- [x] **Diya**: Add safeguard logic ✅ — JUST COMPLETED
- [x] **Omar**: Add policy plugins ✅
- [x] **ALL**: Mid-year update ✅

---

## Key File Locations Reference

### Core Modules:
- `env/sim_env.py` — SimKube environment
- `env/actions/ops.py` — Action operations (Bob)
- `env/actions/trace_io.py` — Trace I/O (Bob)
- `observe/reader.py` — Observations (Cate)
- `observe/reward.py` — Reward function (Cate)
- `ops/hooks.py` — Hooks (Rui)
- `ops/preflight.py` — Preflight checks (Rui)
- `runner/one_step.py` — Agent loop (Omar)

### New Files to Create:
- `runner/policies.py` — Policy implementations (Diya + Omar)
- `runner/safeguards.py` — Guardrail logic (Diya)
- `scripts/batch_run_traces.sh` — Batch runner (Rui)
- `demo/generate_traces.py` — Trace generator (Bob)
- `docs/MID_YEAR_UPDATE.md` — Mid-year documentation (All)
- `docs/TRACE_FORMAT.md` — Trace docs (Bob)
- `docs/TROUBLESHOOTING.md` — Troubleshooting (Omar)
- `docs/ARCHITECTURE.md` — Architecture (Cate)

### Directories:
- `demo/traces/` — Generated traces (Bob)
- `demo/canonical/` — Demo traces (Bob)
- `docs/` — All documentation

---

## Timeline

**Spring 2026 Focus**:
- Safeguards and validation (Weeks 1-2)
- Demo preparation and testing (Weeks 3-4)
- Integration refinement (Ongoing)

---

## Notes

- **Scope**: Keep narrow — focus on insufficient-resources error type
- **Priority**: Working loop > polish > documentation
- **Demo**: Must show end-to-end working system
- ✅ Mid-year report complete

---

**Last Updated**: 2026-01-24 (Spring semester — Mid-year complete, Task 1 complete)  
**Next Review**: After Task 2 completion

**Recent Updates**:
- ✅ **TASK 2 COMPLETE**: Safeguards implemented - agents can't exceed resource caps
- ✅ Mid-year report completed and delivered
- ✅ **TASK 1 COMPLETE**: All policies implemented (noop, heuristic, random, bump_cpu, bump_mem, scale_replicas)
- ✅ Bob completed trace generation: 100 traces (trace-0001 through trace-0100)
- ✅ Bob completed action validation and trace documentation
- ✅ Omar completed policy plugin system with CLI support
- ✅ Major codebase cleanup: Removed 11 files (~572 lines), simplified structure
- ✅ Created comprehensive README.md (685 lines covering entire architecture)
- ✅ Enhanced random policy to use all 4 action types
- ✅ Simplified action application: removed action_applier.py, inlined into one_step.py

**Remaining for Diya**:
- ⚠️ **Task 3: Prepare combined system demo** ← CURRENT FOCUS (waiting for other team members)
