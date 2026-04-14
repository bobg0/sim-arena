"""
agent/prompt_builder.py

Converts a raw observation dict and benchmark scenario context into
the system prompt and user message sent to the LLM provider.

Key design decision: action names are NEVER mentioned in the system prompt.
Only numeric indices are shown. This prevents Gemini's function-calling mode
from pattern-matching action names to MCP tool calls.
"""

from __future__ import annotations

# Action descriptions use only indices — NO action names that could be
# mistaken for callable tools.
ACTION_DESCRIPTIONS = {
    0: "do nothing this step",
    1: "increase CPU request by 500m",
    2: "increase memory request by 256Mi",
    3: "add 1 replica",
    4: "decrease CPU request by 500m",
    5: "decrease memory request by 256Mi",
    6: "remove 1 replica",
}

SYSTEM_PROMPT = """\
You are an autonomous Kubernetes resource optimization agent.

Your job is to reach a TARGET number of healthy (Ready, not Pending) pods.

════════════════════════════════════════════════════
PHASE 1 — INVESTIGATE
════════════════════════════════════════════════════
You have EXACTLY FOUR callable tools. These are the ONLY functions you may call:
  • get_pods(namespace)
  • describe_deployment(namespace, deploy)
  • get_events(namespace, deploy, last_n)
  • get_pod_logs(namespace, pod_name, tail_lines)

Use them to understand why pods are failing or why the count differs from the TARGET.

IMPORTANT: "desired replicas" in describe_deployment shows the CURRENT deployment
configuration — it may differ from the benchmark TARGET. Your goal is to reach the
TARGET, not to match the deployment's current desired count.

════════════════════════════════════════════════════
PHASE 2 — DECIDE
════════════════════════════════════════════════════
Choose ONE action index from this list.

WARNING: These are NOT callable tools. Do NOT call them as functions.
Return the index in JSON only.

  0 — do nothing this step
  1 — increase CPU request by 500m
  2 — increase memory request by 256Mi
  3 — add 1 replica
  4 — decrease CPU request by 500m
  5 — decrease memory request by 256Mi
  6 — remove 1 replica

════════════════════════════════════════════════════
OUTPUT FORMAT — your final message must be ONLY this JSON
════════════════════════════════════════════════════
{{
  "action_index": <integer 0–6>,
  "reasoning": "<one sentence>"
}}

RULES:
- Final response must be valid JSON, nothing else.
- Do NOT call action indices as tool functions.
- The four investigation tools above are the only callable functions.
- If CPU/memory is already above node capacity, REDUCE it (don't increase).
- Use action 3 (add replica) to scale up toward the TARGET.
- Use action 6 (remove replica) to scale down toward the TARGET.
- The TARGET shown in the user message is the authoritative goal, not what
  describe_deployment shows as 'desired replicas'.
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_message(
    obs:        dict,
    target:     int,
    namespace:  str,
    deploy:     str,
    step_idx:   int,
    max_steps:  int,
    scenario_name: str = "",
) -> str:
    ready   = obs.get("ready",   0)
    pending = obs.get("pending", 0)
    total   = obs.get("total",   0)
    healthy = ready == target and pending == 0 and total == target

    if healthy:
        status_line = "All pods are healthy and at target."
    elif total > target:
        status_line = f"TOO MANY pods: {total} running, target is {target}. Need to scale DOWN."
    elif pending > 0:
        status_line = f"{pending} pod(s) PENDING (cannot schedule). {ready}/{target} ready."
    else:
        status_line = f"TOO FEW pods: {total} running, target is {target}. Need to scale UP."

    scenario_line = f"Scenario: {scenario_name}\n" if scenario_name else ""

    return (
        f"{scenario_line}"
        f"Step {step_idx + 1}/{max_steps}\n"
        f"\n"
        f"━━━ CURRENT STATE ━━━\n"
        f"  namespace  : {namespace}\n"
        f"  deployment : {deploy}\n"
        f"  ready pods : {ready}\n"
        f"  pending    : {pending}\n"
        f"  total      : {total}\n"
        f"  *** TARGET : {target} ***\n"
        f"\n"
        f"Status: {status_line}\n"
        f"\n"
        f"PHASE 1: Call get_pods / describe_deployment / get_events / get_pod_logs to investigate.\n"
        f"PHASE 2: Return JSON with action_index (0-6). Do NOT call action indices as tools."
    )