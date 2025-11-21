# Sim-Arena Next Phase Status Report

**Date**: Created for next 1–1.5 weeks of work  
**Context**: Post-MVP integration complete; now implementing real logic, traces, and agents  
**Goal**: Fill in empty shells, create working agent–simulation loop, generate traces, document system state

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
- ⚠️ Generate multiple traces of the *same* insufficient-resources error
- ⚠️ Implement **real actions**
- ⚠️ Define state and action space
- ⚠️ Fill in the "empty shells" inside modules
- ⚠️ Prepare demo
- ⚠️ Complete mid-year update

### Current Status:
- ✅ MVP is fully integrated
- ⚠️ Most internals are still no-ops (need real logic)
- ⚠️ Remaining: fill in real logic, create traces, implement hand-coded agent, document for mid-year deliverable

---

## Task Assignments (1–1.5 Weeks)

---

## **DIYA — Integration + Arena Behavior**

### Task 1: Implement Real Policy Behavior Inside the Loop
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Modify**:
- `runner/one_step.py` — Replace `simple_policy()` function (lines ~92-102)
- Create new file: `runner/policies.py` — Add configurable hand-coded policies

**Deliverables**:
- [ ] Replace current simple policy with configurable policy system
- [ ] Implement at least 3 policies:
  - `always_bump_cpu()` — Always increments CPU requests
  - `always_bump_memory()` — Always increments memory requests
  - `scale_replicas()` — Always scales up replicas
- [ ] Add policy selection mechanism (CLI arg or config)
- [ ] These policies needed to test reward + environment interactions (per Erin)

**Acceptance Criteria**:
- `python runner/one_step.py --policy always_bump_cpu ...` works
- Each policy produces different trace modifications
- Policies can be tested independently

---

### Task 2: Add Safeguard Logic / Hard Caps
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Modify**:
- `runner/one_step.py` — Add guardrails before applying actions
- `env/actions/ops.py` — Add validation logic to action functions
- Consider: `runner/safeguards.py` — New module for guardrail logic

**Deliverables**:
- [ ] Prevent actions that allocate absurd resources (e.g., 100 CPUs, 1TB memory)
- [ ] Implement simple guardrails:
  - Maximum CPU per container (e.g., 16 CPUs)
  - Maximum memory per container (e.g., 32GB)
  - Maximum replicas (e.g., 100)
- [ ] Return clear error messages when actions are blocked
- [ ] Add validation before action application in `one_step()`

**Acceptance Criteria**:
- Attempting to allocate >16 CPUs returns error/False
- Agent cannot issue impossible requests
- Guardrails prevent infinite resource allocation

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

### Task 4: Co-edit "Next Steps" Section of Mid-Year Update
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files to Modify**:
- Create/update: `docs/MID_YEAR_UPDATE.md` or similar
- Section: "Next Steps" — Explain how working loop sets up spring learning-agent stage

**Deliverables**:
- [ ] Summarize current working loop state
- [ ] Explain transition path to learning agents (spring)
- [ ] Document current limitations and future improvements

**Acceptance Criteria**:
- Clear explanation of current state
- Clear roadmap for spring semester

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
**Status**: 🔄 In Progress  
**Priority**: Medium  
**Files to Modify**:
- `runner/one_step.py` — Policy selection mechanism
- `runner/policies.py` (coordinate with Diya) — Policy implementations

**Deliverables**:
- [ ] Let runners select between policies:
  - `noop` — No action
  - `random` — Random action selection
  - `always_bump_cpu` — Always bump CPU (from Diya)
  - `always_bump_memory` — Always bump memory (from Diya)
- [ ] Policy selection via CLI argument: `--policy <name>`
- [ ] Needed to "fill in" empty agent shell (per Erin)

**Acceptance Criteria**:
- `--policy noop` runs without errors
- `--policy random` selects random actions
- Each policy produces different behavior

---

### Task 3: Test Integration with Multiple Generated Traces
**Status**: 🔄 In Progress  
**Priority**: High  
**Files to Create/Modify**:
- `tests/test_multiple_traces.py` — New test file
- `scripts/batch_run_traces.sh` — Batch runner script (coordinate with Rui)

**Deliverables**:
- [ ] Run 5–10 different insufficient-resource traces
- [ ] Confirm loop behavior is stable:
  - Pending pods first
  - Then ready pods after action
- [ ] Document bugs for mid-year update if results differ
- [ ] Test trace variety:
  - Very bad CPU (>16 CPUs requested)
  - Very bad memory (>32GB requested)
  - Slightly bad CPU (e.g., 8.5 CPUs)
  - Mixed CPU/memory issues

**Acceptance Criteria**:
- All traces produce consistent loop behavior
- Bugs documented if any found
- Test suite passes with multiple traces

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

### Task 4: Write "Architecture Overview" Section in Mid-Year Update
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files to Create/Modify**:
- `docs/MID_YEAR_UPDATE.md` — Architecture Overview section

**Deliverables**:
- [ ] Explain each module's role now that integration is complete
- [ ] Document:
  - `env/` — Environment management
  - `observe/` — Observations and rewards
  - `ops/` — Hooks and preflight
  - `runner/` — Agent orchestration
  - `env/actions/` — Trace operations

**Acceptance Criteria**:
- Clear explanation of each module
- Module responsibilities documented
- Integration points explained

---

## **BOB — Trace Generation + Action Validation**

### Task 1: Generate Multiple Insufficient-Resource Traces (Core Requirement)
**Status**: 🔄 In Progress  
**Priority**: Critical  
**Files to Create/Modify**:
- `demo/generate_traces.py` — Script to generate trace variations
- `demo/traces/` — Directory for generated traces
- Use existing: `demo/make_demo_trace.py` as reference

**Deliverables**:
- [ ] Create **50–100 variations** by templating CPU/memory fields
- [ ] Errors should exceed node capacity:
  - >16 CPUs requested
  - >32GB memory requested
  - Combinations of both
- [ ] Convert JSON → msgpack using existing tooling
- [ ] Per David: generate multiple traces of the *same* error type

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
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files to Create**:
- `docs/TRACE_FORMAT.md` — Trace format documentation

**Deliverables**:
- [ ] Document trace JSON structure
- [ ] Explain how to generate new traces
- [ ] Include examples and templates
- [ ] Document msgpack conversion process
- [ ] Short page for future team members (January restart)

**Acceptance Criteria**:
- New team member can generate traces
- Format clearly documented
- Examples provided

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

### Task 4: Write "Reproducibility & Environment Setup" Section for Mid-Year Update
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files to Create/Modify**:
- `docs/MID_YEAR_UPDATE.md` — Reproducibility section

**Deliverables**:
- [ ] Document namespace requirements
- [ ] Document preflight expectations
- [ ] Document cleanup guarantees
- [ ] Include setup instructions for January restart

**Acceptance Criteria**:
- Clear setup instructions
- Reproducibility documented
- Cleanup behavior explained

---

## **Cross-Team Deliverable Tasks**

Each member gets *one* of these so writing load is shared evenly.

### Mid-Year Update Revision
**Status**: 🔄 Pending  
**Priority**: Medium  
**Files**: `docs/MID_YEAR_UPDATE.md` (coordinate sections)

**Sections to Assign**:
- [ ] **Architecture Overview** (Cate — Task 4)
- [ ] **System State & Integration** (Omar — summary of runner work)
- [ ] **Trace Generation & Format** (Bob — Task 4)
- [ ] **Reproducibility & Setup** (Rui — Task 4)
- [ ] **Next Steps** (Diya — Task 4)
- [ ] **Demo Walkthrough** (Diya — Task 3, coordinate with others)

---

### Personal Reflection
**Status**: 🔄 Pending  
**Priority**: Low  
**Files**: `docs/PERSONAL_REFLECTIONS.md` or individual files

**Deliverables**:
- [ ] Each person writes 1–2 paragraphs:
  - What you learned
  - Challenges faced
  - Contributions made
  - Future goals

---

### Meeting with David: Technical Questions
**Status**: 🔄 Pending  
**Priority**: Low  
**Deliverables**:
- [ ] Each person prepares 1–2 technical questions
- [ ] Questions about:
  - Architecture decisions
  - Next steps
  - Integration challenges
  - Future work

---

## Integration Checklist

### Critical Path (Blocking Demo):
- [ ] **Bob**: Generate 50+ traces (Task 1)
- [ ] **Diya**: Implement real policies (Task 1)
- [ ] **Omar**: Verify trace update flow (Task 1)
- [ ] **Cate**: Finalize reward function (Task 1)
- [ ] **Rui**: Verify namespace lifecycle (Task 1)
- [ ] **Diya**: Prepare demo script (Task 3)

### High Priority (Before Break):
- [ ] **Diya**: Add safeguard logic (Task 2)
- [ ] **Omar**: Add policy plugins (Task 2)
- [ ] **Omar**: Test with multiple traces (Task 3)
- [ ] **Cate**: Verify observations (Task 3)
- [ ] **Bob**: Validate actions (Task 2)
- [ ] **Rui**: Batch run script (Task 2)

### Medium Priority (Polish):
- [ ] **Cate**: Architecture diagram (Task 2)
- [ ] **Bob**: Canonical traces (Task 3)
- [ ] **Rui**: Better error messages (Task 3)
- [ ] **Omar**: Troubleshooting notes (Task 4)

### Documentation (Before Break):
- [ ] **All**: Mid-year update sections
- [ ] **All**: Personal reflections
- [ ] **Bob**: Trace format docs (Task 4)
- [ ] **Cate**: Architecture overview (Task 4)
- [ ] **Rui**: Reproducibility docs (Task 4)
- [ ] **Diya**: Next steps section (Task 4)

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

**Week 1 Focus** (Days 1–5):
- Critical path items (trace generation, real policies, verification)
- Core functionality implementation

**Week 2 Focus** (Days 6–10):
- Integration testing with multiple traces
- Demo preparation
- Documentation

**Buffer** (Days 11–12):
- Polish and final review
- Mid-year update compilation
- Demo rehearsal

---

## Notes

- **Scope**: Keep narrow — focus on insufficient-resources error type (per Erin)
- **Priority**: Working loop > polish > documentation
- **Documentation**: Critical for January restart (per Erin)
- **Demo**: Must show end-to-end working system
- **Integration**: Most internals are no-ops — need real logic now

---

**Last Updated**: [Date will be set when tasks begin]  
**Next Review**: After Week 1 completion
