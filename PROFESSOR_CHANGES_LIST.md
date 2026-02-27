# Professor Erin Talvitie's Requested Changes (CSM Clinic Meeting)

Summary of all changes discussed in the meeting. **Reward function changes are done.** The rest are listed for future work.

---

## ✅ 1. Reward Function (DONE)

**Problem:** If the agent can get positive reward before reaching the goal, it has no incentive to finish the episode—it would rather no-op forever than fix the problem.

**Fix applied:**
- All rewards are now **negative** (or 0 only at goal)
- At goal (ready == target, pending == 0, total == target): reward = **0**
- When not at goal: reward is always negative, with shaping (less negative the closer to goal)
- Final clamp: `max(-1.0, min(0.0, r))` so we never return positive

**Files changed:** `sim-arena/observe/reward.py`

---

## 2. Termination vs. Truncation (TODO)

**Problem:** When an episode is cut off (max steps) vs. when it truly terminates (goal reached), the code must treat them differently. Treating truncation like termination is a common RL bug.

**What to do:**
- **Terminal state** (goal reached): Q-value for that state = **0** (no more reward possible)
- **Truncated episode** (hit max steps): Should bootstrap from the next state—do NOT set Q to 0
- Pass a `done`/`terminal` flag into the DQN update function
- When `done=True` (actual termination): manually set target Q-value to 0
- When `done=False` (truncation): use normal bootstrap from next state

**Where to look:** `runner/multi_step.py` (around line 130), DQN agent update logic

---

## 3. High Replay Ratio (TODO)

**Problem:** Experience is expensive to gather (simulation steps), but updates are cheap. Default DQN often does 1 update per step (replay ratio = 1).

**What to do:**
- Use a **high replay ratio**: do many gradient updates per batch of experience
- Professor suggested: "don't do one batch of update, don't do two, do, like, a hundred"
- Try turning up replay ratio even in sequential experiments—might see benefit already
- Find sweet spot: too high → overfitting; too low → doesn't learn much

---

## 4. Parallelization Architecture (TODO)

**Two options discussed:**

### Option A: Simple (recommended first)
- Parallel agents gather experience with current policy
- They add experience to a shared buffer
- Supervisor does many DQN updates on the buffer
- Serialize updated network (e.g., to S3)
- Launch new instances that load the updated network and repeat
- No direct communication between EC2 instances
- Similar to "neural-fitted Q-learning" (gather → update → gather)

### Option B: Asynchronous (more complex)
- Multiple agents run continually, all updating the same value function
- Each step: agent computes update and applies to shared value function
- Requires more communication; no buffer, no target network typically
- Paper: "Asynchronous Methods for Deep Reinforcement Learning" (Mnih et al.)

**Infrastructure notes:**
- Use S3 for trace files to avoid path misplacement
- Build instance once, store as AMI to avoid setup every time
- Ideally: keep instances running, pause for updates, then continue (vs. spin down/up each round)

---

## 5. Target in Observation (Future / Optional)

**Note:** Professor said the current setup (fixed target across traces) is fine for now.

**More sophisticated version:** Include the target in the agent's observation so it can handle different targets per trace. Defer until the simpler setup works.

---

## Summary Checklist

| # | Change | Status |
|---|--------|--------|
| 1 | Reward: all negative except 0 at goal | ✅ Done |
| 2 | Termination vs. truncation in DQN update | TODO |
| 3 | High replay ratio | TODO |
| 4 | Parallelization (simple buffer-based first) | TODO |
| 5 | Target in observation (optional, later) | Deferred |
