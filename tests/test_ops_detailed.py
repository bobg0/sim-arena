"""Educational test suite with detailed logging for understanding trace mutations.

This test file provides comprehensive, beginner-friendly demonstrations of how
the actions module manipulates Kubernetes deployment traces. Each test includes
extensive logging to show:

1. The structure of the trace data
2. How operations navigate through the trace
3. Before/after state comparisons
4. What happens at each step of the mutation process

This is designed for presentations and learning purposes.
"""

from __future__ import annotations

import copy
import json
import unittest
from pprint import pprint

from env.actions.ops import bump_cpu_small, bump_mem_small, scale_up_replicas


def _sample_trace() -> dict:
    """Create a sample trace with a Deployment named 'web'."""
    return {
        "version": 1,
        "events": [
            {
                "ts": 1730390400,
                "applied_objs": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "web", "namespace": "default"},
                        "spec": {
                            "replicas": 2,
                            "selector": {"matchLabels": {"app": "web"}},
                            "template": {
                                "metadata": {"labels": {"app": "web"}},
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "web",
                                            "image": "nginx:latest",
                                            "resources": {
                                                "requests": {
                                                    "cpu": "500m",
                                                    "memory": "512Mi",
                                                }
                                            },
                                        }
                                    ]
                                },
                            },
                        },
                    }
                ],
                "deleted_objs": [],
            }
        ],
    }


def _print_section(title: str, char: str = "=") -> None:
    """Print a visual section divider."""
    print(f"\n{char * 80}")
    print(f"{title:^80}")
    print(f"{char * 80}\n")


def _print_subsection(title: str) -> None:
    """Print a subsection header."""
    print(f"\n{'─' * 80}")
    print(f"  {title}")
    print(f"{'─' * 80}\n")


def _show_trace_structure(trace: dict, label: str = "Trace Structure") -> None:
    """Display the trace structure in a readable format."""
    _print_subsection(label)
    print("Trace is a dictionary with the following structure:")
    print("\n  trace")
    print("    ├── version: 1")
    print("    └── events: [list of events]")
    print("          └── event[0]")
    print("                ├── ts: timestamp")
    print("                └── applied_objs: [list of Kubernetes objects]")
    print("                      └── applied_objs[0] (Deployment)")
    print("                            ├── apiVersion: 'apps/v1'")
    print("                            ├── kind: 'Deployment'")
    print("                            ├── metadata")
    print("                            │     └── name: 'web'")
    print("                            └── spec")
    print("                                  ├── replicas: 2")
    print("                                  └── template")
    print("                                        └── spec")
    print("                                              └── containers: [list]")
    print("                                                    └── containers[0]")
    print("                                                          ├── name: 'web'")
    print("                                                          └── resources")
    print("                                                                └── requests")
    print("                                                                      ├── cpu: '500m'")
    print("                                                                      └── memory: '512Mi'")


def _extract_deployment_info(trace: dict) -> dict:
    """Extract key information from the first deployment for display."""
    deployment = trace["events"][0]["applied_objs"][0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    resources = container.get("resources", {}).get("requests", {})
    
    return {
        "name": deployment["metadata"]["name"],
        "namespace": deployment["metadata"]["namespace"],
        "replicas": deployment["spec"]["replicas"],
        "cpu": resources.get("cpu", "NOT SET"),
        "memory": resources.get("memory", "NOT SET"),
    }


class DetailedOpsTestCase(unittest.TestCase):
    """Educational test suite with detailed logging."""

    def setUp(self) -> None:
        """Set up test fixtures and print header."""
        _print_section("TEST SUITE: Actions Module Educational Tests", "█")
        print("This test suite demonstrates how the actions module mutates Kubernetes traces.")
        print("Each test walks through the process step-by-step with detailed logging.")

    def test_01_trace_structure_overview(self) -> None:
        """Test 1: Show the structure of a trace file."""
        _print_section("TEST 1: Understanding Trace Structure", "═")
        
        trace = _sample_trace()
        
        print("STEP 1: Create a sample trace")
        print("  - A trace is a JSON-like dictionary representing Kubernetes object states")
        print("  - It contains events with 'applied_objs' (what was created/updated)")
        print("  - Each object follows the Kubernetes API structure\n")
        
        _show_trace_structure(trace)
        
        _print_subsection("Current Deployment State")
        info = _extract_deployment_info(trace)
        print(f"  Deployment Name: {info['name']}")
        print(f"  Namespace: {info['namespace']}")
        print(f"  Replicas: {info['replicas']}")
        print(f"  CPU Request: {info['cpu']}")
        print(f"  Memory Request: {info['memory']}")
        
        print("\n✓ This trace represents a deployment with:")
        print("  - 2 replica pods")
        print("  - Each pod requests 500 millicores of CPU")
        print("  - Each pod requests 512 MiB of memory")

    def test_02_cpu_bump_detailed(self) -> None:
        """Test 2: Detailed walkthrough of bump_cpu_small operation."""
        _print_section("TEST 2: Bumping CPU Requests (bump_cpu_small)", "═")
        
        trace = _sample_trace()
        original_trace = copy.deepcopy(trace)
        
        _print_subsection("Step 1: Initial State")
        info_before = _extract_deployment_info(trace)
        print(f"  CPU Request BEFORE: {info_before['cpu']}")
        print(f"  (500m = 500 millicores = 0.5 CPU cores)")
        
        _print_subsection("Step 2: Call bump_cpu_small()")
        print("  Function: bump_cpu_small(trace, deploy='web', step='500m')")
        print("\n  What happens inside:")
        print("    a) _iter_deployments() searches through:")
        print("         - trace['events'][0]['applied_objs']")
        print("         - Finds Deployment with metadata.name == 'web'")
        print("    b) _first_container() navigates to:")
        print("         - deployment['spec']['template']['spec']['containers'][0]")
        print("    c) _ensure_requests() ensures resources.requests exists")
        print("    d) _parse_cpu('500m') converts '500m' → (500, 'm') millicores")
        print("    e) Current CPU: 500m → 500 millicores")
        print("    f) Step: 500m → 500 millicores")
        print("    g) New value: 500 + 500 = 1000 millicores")
        print("    h) _format_cpu(1000, 'm') → '1000m'")
        print("    i) Updates trace['events'][0]['applied_objs'][0]")
        print("         ['spec']['template']['spec']['containers'][0]")
        print("         ['resources']['requests']['cpu'] = '1000m'")
        
        changed = bump_cpu_small(trace, "web", step="500m")
        
        _print_subsection("Step 3: Result")
        print(f"  Return value: changed = {changed}")
        print(f"  (True means at least one deployment was modified)")
        
        info_after = _extract_deployment_info(trace)
        print(f"\n  CPU Request AFTER: {info_after['cpu']}")
        
        _print_subsection("Step 4: Verification")
        cpu_path = (
            "trace['events'][0]['applied_objs'][0]"
            "['spec']['template']['spec']['containers'][0]"
            "['resources']['requests']['cpu']"
        )
        print(f"  Path to CPU value: {cpu_path}")
        print(f"  Original value: {info_before['cpu']}")
        print(f"  New value: {info_after['cpu']}")
        print(f"  Change: +500m (0.5 cores)")
        
        self.assertTrue(changed, "Operation should report success")
        self.assertEqual(info_after['cpu'], "1000m", "CPU should increase by 500m")
        self.assertNotEqual(trace, original_trace, "Trace should be modified")
        
        print("\n✓ TEST PASSED: CPU successfully bumped from 500m to 1000m")

    def test_03_memory_bump_detailed(self) -> None:
        """Test 3: Detailed walkthrough of bump_mem_small operation."""
        _print_section("TEST 3: Bumping Memory Requests (bump_mem_small)", "═")
        
        trace = _sample_trace()
        original_trace = copy.deepcopy(trace)
        
        _print_subsection("Step 1: Initial State")
        info_before = _extract_deployment_info(trace)
        print(f"  Memory Request BEFORE: {info_before['memory']}")
        print(f"  (512Mi = 512 * 1024² bytes = 536,870,912 bytes)")
        
        _print_subsection("Step 2: Memory Unit Conversion")
        print("  Memory units use binary prefixes (powers of 1024):")
        print("    - B (bytes): 1")
        print("    - Ki (kibibytes): 1024")
        print("    - Mi (mebibytes): 1024² = 1,048,576")
        print("    - Gi (gibibytes): 1024³ = 1,073,741,824")
        print("\n  Current: 512Mi = 512 × 1,048,576 = 536,870,912 bytes")
        print("  Step: 256Mi = 256 × 1,048,576 = 268,435,456 bytes")
        
        _print_subsection("Step 3: Call bump_mem_small()")
        print("  Function: bump_mem_small(trace, deploy='web', step='256Mi')")
        print("\n  What happens inside:")
        print("    a) _parse_mem('512Mi') → (536870912, 'Mi') bytes")
        print("    b) _parse_mem('256Mi') → (268435456, 'Mi') bytes")
        print("    c) Add: 536870912 + 268435456 = 805306368 bytes")
        print("    d) _format_mem(805306368, 'Mi') → '768Mi'")
        print("       (805306368 / 1048576 = 768 exactly)")
        
        changed = bump_mem_small(trace, "web", step="256Mi")
        
        _print_subsection("Step 4: Result")
        info_after = _extract_deployment_info(trace)
        print(f"  Memory Request BEFORE: {info_before['memory']}")
        print(f"  Memory Request AFTER: {info_after['memory']}")
        print(f"  Change: +256Mi")
        
        self.assertTrue(changed)
        self.assertEqual(info_after['memory'], "768Mi")
        self.assertNotEqual(trace, original_trace)
        
        print("\n✓ TEST PASSED: Memory successfully bumped from 512Mi to 768Mi")

    def test_04_replica_scale_detailed(self) -> None:
        """Test 4: Detailed walkthrough of scale_up_replicas operation."""
        _print_section("TEST 4: Scaling Up Replicas (scale_up_replicas)", "═")
        
        trace = _sample_trace()
        original_trace = copy.deepcopy(trace)
        
        _print_subsection("Step 1: Initial State")
        info_before = _extract_deployment_info(trace)
        print(f"  Replicas BEFORE: {info_before['replicas']}")
        print(f"  (This means Kubernetes will create {info_before['replicas']} pod instances)")
        
        _print_subsection("Step 2: Call scale_up_replicas()")
        print("  Function: scale_up_replicas(trace, deploy='web', delta=2)")
        print("\n  What happens inside:")
        print("    a) _iter_deployments() finds the 'web' deployment")
        print("    b) Navigates to: deployment['spec']['replicas']")
        print("    c) Current value: 2")
        print("    d) Delta: 2")
        print("    e) New value: 2 + 2 = 4")
        print("    f) Updates: deployment['spec']['replicas'] = 4")
        
        changed = scale_up_replicas(trace, "web", delta=2)
        
        _print_subsection("Step 3: Result")
        info_after = _extract_deployment_info(trace)
        print(f"  Replicas BEFORE: {info_before['replicas']}")
        print(f"  Replicas AFTER: {info_after['replicas']}")
        print(f"  Change: +2 replicas")
        print(f"\n  This means Kubernetes will now create {info_after['replicas']} pods")
        print(f"  instead of {info_before['replicas']}")
        
        self.assertTrue(changed)
        self.assertEqual(info_after['replicas'], 4)
        self.assertNotEqual(trace, original_trace)
        
        print("\n✓ TEST PASSED: Replicas successfully scaled from 2 to 4")

    def test_05_deployment_not_found_safety(self) -> None:
        """Test 5: Demonstrate safe handling when deployment is not found."""
        _print_section("TEST 5: Safety Check - Deployment Not Found", "═")
        
        trace = _sample_trace()
        original_trace = copy.deepcopy(trace)
        
        _print_subsection("Step 1: Initial State")
        info = _extract_deployment_info(trace)
        print(f"  Trace contains deployment: '{info['name']}'")
        print(f"  We will search for: 'api' (which does NOT exist)")
        
        _print_subsection("Step 2: Attempt Mutation on Non-Existent Deployment")
        print("  Function: bump_cpu_small(trace, deploy='api', step='500m')")
        print("\n  What happens inside:")
        print("    a) _iter_deployments(trace, 'api') searches all events")
        print("    b) Looks for Deployment with metadata.name == 'api'")
        print("    c) No matching deployment found → iterator yields nothing")
        print("    d) Loop body never executes")
        print("    e) changed remains False")
        print("    f) Returns False")
        
        changed = bump_cpu_small(trace, "api", step="500m")
        
        _print_subsection("Step 3: Verification")
        print(f"  Return value: changed = {changed}")
        print(f"  (False means no deployment was modified)")
        print("\n  Critical safety check:")
        print("    - Original trace should be UNCHANGED")
        print("    - This prevents accidental modifications to wrong deployments")
        
        _print_subsection("Step 4: Compare Original vs Modified")
        print("  Checking that trace == original_trace...")
        trace_json = json.dumps(trace, sort_keys=True)
        original_json = json.dumps(original_trace, sort_keys=True)
        
        if trace_json == original_json:
            print("  ✓ Trace is unchanged (correct behavior)")
        else:
            print("  ✗ Trace was modified (ERROR!)")
        
        self.assertFalse(changed, "Should return False when deployment not found")
        self.assertEqual(trace, original_trace, "Trace must remain unchanged")
        
        print("\n✓ TEST PASSED: Trace correctly left unchanged when deployment not found")
        print("  This satisfies the acceptance criteria for safe mutation operations")

    def test_06_multiple_mutations_sequence(self) -> None:
        """Test 6: Show a sequence of multiple mutations."""
        _print_section("TEST 6: Multiple Mutations in Sequence", "═")
        
        trace = _sample_trace()
        
        _print_subsection("Initial State")
        info = _extract_deployment_info(trace)
        print(f"  Deployment: {info['name']}")
        print(f"  Replicas: {info['replicas']}")
        print(f"  CPU: {info['cpu']}")
        print(f"  Memory: {info['memory']}")
        
        _print_subsection("Mutation Sequence")
        
        print("\n  1) Bump CPU by 500m")
        changed1 = bump_cpu_small(trace, "web", step="500m")
        info1 = _extract_deployment_info(trace)
        print(f"     Result: CPU = {info1['cpu']} (changed={changed1})")
        
        print("\n  2) Bump Memory by 256Mi")
        changed2 = bump_mem_small(trace, "web", step="256Mi")
        info2 = _extract_deployment_info(trace)
        print(f"     Result: Memory = {info2['memory']} (changed={changed2})")
        
        print("\n  3) Scale replicas by +1")
        changed3 = scale_up_replicas(trace, "web", delta=1)
        info3 = _extract_deployment_info(trace)
        print(f"     Result: Replicas = {info3['replicas']} (changed={changed3})")
        
        print("\n  4) Bump CPU again by 1000m")
        changed4 = bump_cpu_small(trace, "web", step="1000m")
        info4 = _extract_deployment_info(trace)
        print(f"     Result: CPU = {info4['cpu']} (changed={changed4})")
        
        _print_subsection("Final State")
        final_info = _extract_deployment_info(trace)
        print(f"  Replicas: {info['replicas']} → {final_info['replicas']} (+{final_info['replicas'] - info['replicas']})")
        print(f"  CPU: {info['cpu']} → {final_info['cpu']}")
        print(f"  Memory: {info['memory']} → {final_info['memory']}")
        
        self.assertTrue(changed1 and changed2 and changed3 and changed4)
        self.assertEqual(final_info['replicas'], 3)
        self.assertEqual(final_info['cpu'], "2000m")
        self.assertEqual(final_info['memory'], "768Mi")
        
        print("\n✓ TEST PASSED: Multiple mutations applied successfully")
        print("  Each operation independently modifies the trace in-place")

    def test_07_code_interaction_flow(self) -> None:
        """Test 7: Visualize how different code sections interact."""
        _print_section("TEST 7: Code Interaction Flow Diagram", "═")
        
        print("""
        This test shows how different functions in ops.py work together:
        
        ┌─────────────────────────────────────────────────────────────┐
        │                     USER CALLS                              │
        │  bump_cpu_small(trace, "web", step="500m")                  │
        └─────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────────────────────┐
        │           bump_cpu_small() - Main Orchestrator              │
        │  • Parses step value using _parse_cpu()                     │
        │  • Calls _iter_deployments() to find deployments           │
        │  • For each deployment:                                     │
        │    - Calls _first_container() to get container              │
        │    - Calls _ensure_requests() to ensure structure           │
        │    - Parses current CPU with _parse_cpu()                  │
        │    - Calculates new value                                   │
        │    - Formats result with _format_cpu()                       │
        │    - Updates trace in-place                                  │
        └─────────────────────┬───────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┬───────────────┬─────────────┐
                    ▼                   ▼               ▼             ▼
        ┌───────────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐
        │_iter_deployments()│ │_first_       │ │_parse_cpu() │ │_format_    │
        │                   │ │container()   │ │             │ │cpu()       │
        │ Searches through: │ │               │ │ Converts:   │ │            │
        │ • events[]        │ │ Navigates:   │ │ "500m" →    │ │ Converts:  │
        │   • applied_objs[]│ │ • spec       │ │ (500, "m")  │ │ 1000, "m" →│
        │   • Finds Deploys │ │ • template   │ │             │ │ "1000m"    │
        │   • Filters by    │ │ • spec       │ │             │ │            │
        │     name          │ │ • containers │ │             │ │            │
        │                   │ │ [0]          │ │             │ │            │
        └───────────────────┘ └──────────────┘ └──────────────┘ └────────────┘
        
        Each helper function has a single responsibility:
        • _iter_deployments: Navigation/filtering
        • _first_container: Navigation
        • _ensure_requests: Structure initialization
        • _parse_cpu/_format_cpu: Value conversion
        """)
        
        trace = _sample_trace()
        print("\n  Executing actual operation to demonstrate flow...")
        print("  ─────────────────────────────────────────────────────")
        print("\n  1. bump_cpu_small() called")
        print("     ↓")
        print("  2. _parse_cpu('500m') → (500, 'm')")
        print("     ↓")
        print("  3. _iter_deployments(trace, 'web')")
        print("     • Scanning events[0]['applied_objs'][0]")
        print("     • Found: Deployment 'web'")
        print("     ↓")
        print("  4. _first_container(deployment)")
        print("     • Navigating: spec → template → spec → containers[0]")
        print("     • Found container 'web'")
        print("     ↓")
        print("  5. _ensure_requests(container)")
        print("     • Ensuring resources.requests exists")
        print("     ↓")
        print("  6. _parse_cpu('500m') → (500, 'm') [current value]")
        print("     ↓")
        print("  7. Calculation: 500 + 500 = 1000 millicores")
        print("     ↓")
        print("  8. _format_cpu(1000, 'm') → '1000m'")
        print("     ↓")
        print("  9. Update: trace[...]['cpu'] = '1000m'")
        print("     ↓")
        print(" 10. Return: True")
        
        changed = bump_cpu_small(trace, "web", step="500m")
        
        print(f"\n  ✓ Operation completed: changed={changed}")
        
        self.assertTrue(changed)
        
        print("\n✓ TEST PASSED: Code interaction flow demonstrated")


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2, exit=False)
    
    print("\n" + "█" * 80)
    print("END OF TEST SUITE".center(80))
    print("█" * 80)
    print("\nSummary:")
    print("  • Test 1: Explored trace structure")
    print("  • Test 2: Demonstrated CPU bumping with detailed steps")
    print("  • Test 3: Demonstrated memory bumping with unit conversions")
    print("  • Test 4: Demonstrated replica scaling")
    print("  • Test 5: Showed safe handling of missing deployments")
    print("  • Test 6: Showed multiple sequential mutations")
    print("  • Test 7: Visualized code interaction flow")
    print("\nAll operations work by:")
    print("  1. Navigating through the trace structure")
    print("  2. Finding the target deployment")
    print("  3. Locating the container/field to modify")
    print("  4. Parsing current values (with unit conversion)")
    print("  5. Calculating new values")
    print("  6. Formatting and updating the trace")
    print("  7. Returning success/failure status")

