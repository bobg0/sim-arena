# Sim-Arena MVP Readiness Assessment

**Date**: 2026-01-24  
**Context**: Spring semester - evaluating what's complete vs what's needed for fully working MVP  
**Question**: What do we need to have a FULLY RUNNING MVP?

---

## TL;DR: What's the Gap?

**Short answer**: We have all the code, but **haven't tested it end-to-end with a real cluster yet**.

**Status**: 
- Code: ✅ 95% complete
- Tests: ⚠️ 60% complete
- Integration: ⚠️ Not verified on real cluster
- Demo: ⚠️ Not finalized

---

## What We Have (Components)

### ✅ **Complete & Working**

1. **Trace Generation** (Bob)
   - 100 traces generated ✅
   - Various resource error scenarios ✅
   - MessagePack format ✅
   - `demo/generate_traces.py` can make more ✅

2. **Policies** (Diya + Omar)
   - 6 hand-coded policies ✅
   - Policy registry system ✅
   - `--policy` CLI argument ✅
   - Random, heuristic, always-bump variants ✅

3. **Actions** (Bob)
   - `bump_cpu_small()` ✅
   - `bump_mem_small()` ✅
   - `scale_up_replicas()` ✅
   - All tested in isolation ✅

4. **Safeguards** (Diya)
   - Hard caps (16 CPU, 32GB, 100 replicas) ✅
   - Validation before action application ✅
   - Test suite passing ✅
   - Clear error messages ✅

5. **Observations** (Cate)
   - Extract pod states (ready/pending/total) ✅
   - Kubernetes API integration ✅
   - Basic tests exist ✅

6. **Reward** (Cate)
   - Binary reward function (0 or 1) ✅
   - Simple and clear ✅
   - Works with current observations ✅

7. **Runner** (Omar)
   - `one_step.py` orchestrates full loop ✅
   - `multi_step.py` for episodes ✅
   - Logging to step.jsonl + summary.json ✅

8. **Infrastructure** (Rui)
   - Hooks system ✅
   - Preflight checks ✅
   - `run_demo.sh` exists ✅

---

## What's Missing (Gaps)

### 🔴 **Critical Gaps (Blocking MVP)**

1. **End-to-End Integration Testing**
   - **Status**: Not done
   - **What's missing**: Nobody has run the full loop on a real cluster with real SimKube
   - **Why it matters**: Code might work in isolation but fail when integrated
   - **Who**: Omar (Task 1), Rui (Task 1)
   - **Test**: Run `./run_demo.sh` and verify it completes without errors

2. **Trace Modification Persistence**
   - **Status**: Unclear if working
   - **What's missing**: Verify that when we bump CPU in episode 1, the trace used in episode 2 has the higher CPU
   - **Why it matters**: Core feature - agent can't learn if traces don't persist changes
   - **Who**: Omar (Task 1)
   - **Test**: Run `multi_step.py --steps 5` and check `.tmp/trace-next.msgpack` after each step

3. **Cleanup Reliability**
   - **Status**: Unknown
   - **What's missing**: Verify namespace gets cleaned properly between runs
   - **Why it matters**: Demos will fail if old pods interfere
   - **Who**: Rui (Task 1)
   - **Test**: Run demo 5 times in a row, check no leftover pods

### 🟡 **High Priority (Needed for Good MVP)**

4. **Observation Correctness Across Traces**
   - **Status**: In progress (Cate)
   - **What's missing**: Test that observations are correct for various trace scenarios
   - **Why it matters**: Agent makes decisions based on observations
   - **Who**: Cate (Task 3)
   - **Test**: Run with 10 different traces, verify pod counts are accurate

5. **Action Validation Across All Traces**
   - **Status**: In progress (Bob)
   - **What's missing**: Test all 3 actions on all 100 traces
   - **Why it matters**: Need to know actions work universally, not just on trace-0001
   - **Who**: Bob (Task 2)
   - **Test**: Automated test suite that runs actions on all traces

### 🟢 **Nice to Have (Polish)**

6. **Demo Script**
   - **Status**: `run_demo.sh` exists but may need updates
   - **What's missing**: Polished walkthrough showing different policies
   - **Why it matters**: Presentations and onboarding
   - **Who**: Diya (Task 3)

7. **Batch Runner**
   - **Status**: Not created
   - **What's missing**: Script to run one_step on all 100 traces automatically
   - **Why it matters**: Testing at scale
   - **Who**: Rui (Task 2)

8. **Canonical Demo Traces**
   - **Status**: Not selected
   - **What's missing**: 3-4 "showcase" traces for demos
   - **Why it matters**: Consistent demo experience
   - **Who**: Bob (Task 3)

---

## MVP Definition: What "Fully Running" Means

A **fully running MVP** should be able to:

### Must Have ✅
- [x] Load a trace file with resource problems
- [x] Create a SimKube simulation
- [x] Observe pod states (ready/pending counts)
- [x] Choose an action based on a policy
- [x] Modify the trace file with the action
- [x] Compute a reward
- [x] Log results
- [x] Clean up
- [ ] **Run 5 consecutive episodes without crashing** ← NOT VERIFIED
- [ ] **Show improvement over episodes** (pending → ready after bumping resources) ← NOT VERIFIED

### Should Have ⚠️
- [ ] Work reliably across different trace files (not just trace-0001)
- [ ] Clean up namespace between runs (no leftover pods)
- [ ] Block invalid actions (safeguards working in practice)
- [ ] Handle errors gracefully

### Nice to Have 🎯
- [ ] Polished demo script
- [ ] Documentation for reproducing
- [ ] Batch testing capabilities

---

## The Real Question: Can We Run This Today?

**Theory**: Yes, everything is implemented ✅  
**Practice**: Unknown - nobody has tested it end-to-end ⚠️

### What Could Go Wrong?

1. **Cluster connectivity issues**
   - SimKube CRDs not installed
   - Namespace doesn't exist
   - Permissions problems

2. **Trace format mismatches**
   - Our traces might not match what SimKube expects
   - Actions might not modify traces correctly

3. **Timing issues**
   - Wait duration too short to see pod failures
   - Observations called before pods appear

4. **Integration bugs**
   - Modules work in isolation but fail together
   - Unexpected errors in the flow

5. **Cleanup failures**
   - Simulations don't get deleted
   - Namespace gets polluted

---

## MVP Readiness Checklist

### 🔴 Critical (Must Fix Before MVP Works)

- [ ] **Run end-to-end test on real cluster**
  - Run: `./run_demo.sh`
  - Expected: Completes without errors
  - Owner: Omar + Rui
  - Estimated effort: 1-2 hours

- [ ] **Verify trace persistence between episodes**
  - Run: `python runner/multi_step.py --trace demo/traces/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 60 --policy bump_cpu --steps 5`
  - Expected: CPU increases each episode, eventually pods become ready
  - Owner: Omar
  - Estimated effort: 30 mins

- [ ] **Test cleanup is idempotent**
  - Run demo 5 times in a row
  - Check: `kubectl get pods -n test-ns` (should be empty after each run)
  - Owner: Rui
  - Estimated effort: 30 mins

### 🟡 High Priority (Needed for Reliable MVP)

- [ ] **Test observations on 10 different traces**
  - Verify ready/pending counts are accurate
  - Owner: Cate
  - Estimated effort: 1 hour

- [ ] **Validate actions work on all trace types**
  - Test bump_cpu, bump_mem, scale_replicas on various traces
  - Owner: Bob
  - Estimated effort: 1-2 hours

- [ ] **Verify safeguards actually block actions**
  - Create a trace with 15.5 CPUs, try to bump it
  - Should see "Action blocked" message
  - Owner: Diya
  - Estimated effort: 30 mins

### 🟢 Polish (Makes MVP Better)

- [ ] **Create polished demo script**
  - Show different policies
  - Show successful learning (pending → ready over episodes)
  - Owner: Diya
  - Estimated effort: 2-3 hours

- [ ] **Select 3-4 canonical traces**
  - Very bad CPU, very bad memory, slightly bad, mixed
  - Owner: Bob
  - Estimated effort: 30 mins

---

## Recommended Testing Priority

### **Phase 1: Smoke Test (Do This First!)**
```bash
# Just make sure it runs without crashing
cd sim-arena
source .venv/bin/activate
./run_demo.sh
```

**Expected outcome**: Script completes, logs written, no Python errors

**If this fails**: Fix integration bugs before continuing

### **Phase 2: Multi-Episode Test**
```bash
# Verify learning loop works
python runner/multi_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --policy bump_cpu \
  --steps 5
```

**Expected outcome**: 
- Episode 1: pods pending (CPU too high)
- Episodes 2-5: CPU increases, eventually pods become ready
- Reward goes from 0 → 1

**If this works**: MVP is basically done! Just need polish.

### **Phase 3: Robustness Testing**
```bash
# Test different policies
for policy in noop heuristic random bump_cpu bump_mem scale_replicas; do
  echo "Testing policy: $policy"
  python runner/one_step.py --trace demo/traces/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 60 --policy $policy
done

# Test different traces
for i in {1..10}; do
  echo "Testing trace: trace-$(printf '%04d' $i).msgpack"
  python runner/one_step.py --trace demo/traces/trace-$(printf '%04d' $i).msgpack --ns test-ns --deploy web --target 3 --duration 60 --policy heuristic
done
```

**Expected outcome**: All run without crashing, even if rewards differ

---

## What Would Make This "Production Ready"

Beyond MVP, these would make it publication/demo worthy:

- [ ] Automated test suite that runs against real cluster
- [ ] Multiple reward functions (binary, gradual, penalty)
- [ ] Better observations (CPU usage, node info, events)
- [ ] More action types (reduce resources, set limits)
- [ ] Comprehensive troubleshooting guide
- [ ] Video walkthrough

**But you don't need these for MVP!**

---

## Honest Assessment

### ✅ **What's Actually Complete**
- Code: 95%
- Unit tests: 80%
- Documentation: 90%

### ⚠️ **What's Unknown**
- Integration testing: 0% (nobody ran it end-to-end)
- Multi-episode learning: 0% (theory says it should work, but untested)
- Reliability across traces: 10% (tested on trace-0001 only)

### 🎯 **To Get to 100% Working MVP**

**Minimum work needed:**
1. Run `./run_demo.sh` successfully (1-2 hours of debugging expected)
2. Run `multi_step.py` for 5 episodes and see improvement (30 mins - 1 hour)
3. Fix any bugs discovered (unknown time)

**Best estimate**: 3-5 hours of integration testing and bug fixing

---

## Summary

**You have all the pieces**, you just haven't **assembled and tested them yet**.

It's like having all the ingredients for a cake but not baking it yet. The ingredients are good, the recipe is written, but nobody has turned on the oven.

**Next steps:**
1. Someone needs to run `./run_demo.sh` on a cluster with SimKube
2. Fix any bugs that appear
3. Verify multi-episode learning works
4. Then you're done!

---

## Recommendation for Diya

Since you're waiting for others to complete their integration testing, you could:

1. **Test locally what you can**: Run `test_safeguards.py` (already done ✅)
2. **Draft the demo guide**: Write what the demo SHOULD show (even if it doesn't work yet)
3. **Prepare canonical traces**: Pick 3-4 good examples from the 100 traces
4. **Wait for Omar/Rui** to finish integration testing, then finalize your demo

**OR** you could try running `./run_demo.sh` yourself if you have cluster access!
