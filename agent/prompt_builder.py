"""
agent/prompt_builder.py

Converts a raw observation dict and benchmark scenario context into
the system prompt and user message that are sent to the Anthropic API.

Design principles:
- The system prompt explains the task, action space, and output format ONCE.
- The user message carries the current cluster state and step context.
- The LLM is told it MAY call MCP tools before responding, and that it
  MUST eventually return a JSON action object.
- Action indices are kept consistent with ACTION_SPACE in runner/one_step.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Action space — must stay in sync with ACTION_SPACE in runner/one_step.py
# ---------------------------------------------------------------------------

ACTION_DESCRIPTIONS = {
    0: "noop          — do nothing this step",
    1: "bump_cpu      — increase CPU request by 500m",
    2: "bump_mem      — increase memory request by 256Mi",
    3: "scale_up      — add 1 replica",
    4: "reduce_cpu    — decrease CPU request by 500m",
    5: "reduce_mem    — decrease memory request by 256Mi",
    6: "scale_down    — remove 1 replica",
}

# ---------------------------------------------------------------------------
# System prompt (static, sent once per conversation)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an autonomous Kubernetes resource optimization agent.
Your goal is to fix a resource problem in a running Kubernetes cluster so
that the target number of pods become healthy (Ready and not Pending).

You have access to four tools that let you inspect the live cluster state:
  • get_pods(namespace)                            — pod phases and container states
  • describe_deployment(namespace, deploy)         — current CPU/memory requests, replica counts
  • get_events(namespace, deploy, last_n)          — recent Warning and Normal events
  • get_pod_logs(namespace, pod_name, tail_lines)  — container log tail

Workflow per step:
1. Use the tools above (as many calls as you need) to understand the current
   cluster state and the root cause of the resource problem.
2. Once you have enough information, decide on exactly ONE action from the
   action space below.
3. Respond with ONLY a JSON object — no markdown, no explanation outside JSON.

Action space (use the integer index in your response):
{action_space}

Output format (JSON only, nothing else):
{{
  "action_index": <integer 0-6>,
  "reasoning": "<one sentence explaining why>"
}}

Constraints:
- You MUST respond with valid JSON as your final message.
- Choose action_index 0 (noop) if the cluster is already healthy or if
  you are genuinely uncertain and want to observe before acting.
- Do NOT over-allocate resources. Prefer the smallest change that could fix
  the problem.
- Resource safeguards are enforced server-side (CPU max 16000m, mem max 32Gi,
  replicas max 100). Blocked actions are treated as noop and penalised.
"""

# ---------------------------------------------------------------------------
# User message builder
# ---------------------------------------------------------------------------

def build_user_message(
    obs:        dict,
    target:     int,
    namespace:  str,
    deploy:     str,
    step_idx:   int,
    max_steps:  int,
    scenario_name: str = "",
) -> str:
    """
    Build the user-turn message for a single agent step.

    Args:
        obs:           Raw observation dict {"ready": int, "pending": int, "total": int}
        target:        Target number of ready pods
        namespace:     Kubernetes namespace (e.g. "virtual-default")
        deploy:        Deployment name      (e.g. "web")
        step_idx:      Current step index within the episode (0-based)
        max_steps:     Maximum steps in the episode
        scenario_name: Human-readable scenario label (optional)

    Returns:
        Formatted user message string.
    """
    ready   = obs.get("ready",   0)
    pending = obs.get("pending", 0)
    total   = obs.get("total",   0)
    healthy = ready == target and pending == 0 and total == target

    status_line = (
        "✅ All pods are healthy — consider noop unless you want to reduce waste."
        if healthy
        else f"⚠️  {pending} pod(s) pending, {ready}/{target} ready."
    )

    scenario_line = f"Scenario: {scenario_name}\n" if scenario_name else ""

    return (
        f"{scenario_line}"
        f"Step {step_idx + 1}/{max_steps}\n"
        f"\n"
        f"Current observation:\n"
        f"  namespace : {namespace}\n"
        f"  deployment: {deploy}\n"
        f"  ready     : {ready}\n"
        f"  pending   : {pending}\n"
        f"  total     : {total}\n"
        f"  target    : {target}\n"
        f"\n"
        f"Status: {status_line}\n"
        f"\n"
        f"Use the available tools to investigate, then return your JSON action."
    )


def build_system_prompt() -> str:
    """Return the fully formatted system prompt with the action space embedded."""
    action_space_str = "\n".join(
        f"  {idx}: {desc}"
        for idx, desc in ACTION_DESCRIPTIONS.items()
    )
    return SYSTEM_PROMPT.format(action_space=action_space_str)
