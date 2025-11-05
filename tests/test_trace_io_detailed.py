"""Educational test suite for trace I/O operations with detailed logging.

This demonstrates how MessagePack trace files are loaded and saved,
and how they integrate with the operations module.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from env.actions.ops import bump_cpu_small
from env.actions.trace_io import load_trace, save_trace


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


class DetailedTraceIOTestCase(unittest.TestCase):
    """Educational test suite for trace I/O with detailed logging."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        _print_section("TEST SUITE: Trace I/O Operations Educational Tests", "█")
        print("This test suite demonstrates MessagePack file operations for traces.")

    def test_01_save_and_load_roundtrip(self) -> None:
        """Test 1: Save and load a trace file (roundtrip)."""
        _print_section("TEST 1: Save and Load Trace (Roundtrip)", "═")
        
        # Create sample trace
        trace_data = {
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
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "name": "web",
                                                "resources": {
                                                    "requests": {
                                                        "cpu": "500m",
                                                        "memory": "512Mi",
                                                    }
                                                },
                                            }
                                        ]
                                    }
                                },
                            },
                        }
                    ],
                }
            ],
        }
        
        _print_subsection("Step 1: Create Trace Data Structure")
        print("  Trace is a Python dictionary with:")
        print("    • version: Schema version number")
        print("    • events: List of Kubernetes object state changes")
        print(f"\n  Current trace structure:")
        print(f"    version: {trace_data['version']}")
        print(f"    events: {len(trace_data['events'])} event(s)")
        print(f"      └── Event 0: {len(trace_data['events'][0]['applied_objs'])} object(s)")
        
        # Save to temporary file
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "test_trace.msgpack"
            
            _print_subsection("Step 2: Save Trace to MessagePack File")
            print(f"  Destination: {trace_path}")
            print("\n  What save_trace() does:")
            print("    a) Validates that obj is a dictionary/mapping")
            print("    b) Creates parent directories if needed")
            print("    c) Opens file in binary write mode ('wb')")
            print("    d) Uses msgpack.dump() to serialize dictionary")
            print("    e) Writes compressed binary data to disk")
            print("\n  MessagePack format:")
            print("    • Binary serialization (more compact than JSON)")
            print("    • Preserves Python types (strings, numbers, dicts, lists)")
            print("    • Smaller file size than JSON for nested structures")
            
            save_trace(trace_data, str(trace_path))
            
            _print_subsection("Step 3: Verify File Was Created")
            file_size = trace_path.stat().st_size
            print(f"  ✓ File created: {trace_path}")
            print(f"  ✓ File size: {file_size} bytes")
            print(f"  ✓ File exists: {trace_path.exists()}")
            
            _print_subsection("Step 4: Load Trace from MessagePack File")
            print(f"  Source: {trace_path}")
            print("\n  What load_trace() does:")
            print("    a) Checks if file exists (raises FileNotFoundError if not)")
            print("    b) Opens file in binary read mode ('rb')")
            print("    c) Uses msgpack.load() to deserialize binary data")
            print("    d) Validates that root object is a dictionary")
            print("    e) Returns the parsed Python dictionary")
            
            loaded_trace = load_trace(str(trace_path))
            
            _print_subsection("Step 5: Compare Original vs Loaded")
            print("  Checking if loaded data matches original...")
            
            original_json = json.dumps(trace_data, sort_keys=True)
            loaded_json = json.dumps(loaded_trace, sort_keys=True)
            
            if original_json == loaded_json:
                print("  ✓ Roundtrip successful: data matches exactly")
                print("\n  Verification:")
                print(f"    Original version: {trace_data['version']}")
                print(f"    Loaded version: {loaded_trace['version']}")
                print(f"    Original events: {len(trace_data['events'])}")
                print(f"    Loaded events: {len(loaded_trace['events'])}")
            else:
                print("  ✗ Data mismatch! This should never happen.")
            
            self.assertEqual(trace_data, loaded_trace)
            print("\n✓ TEST PASSED: Roundtrip save/load successful")

    def test_02_file_not_found_error(self) -> None:
        """Test 2: Demonstrate error handling for missing files."""
        _print_section("TEST 2: Error Handling - Missing File", "═")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "does_not_exist.msgpack"
            
            _print_subsection("Step 1: Attempt to Load Non-Existent File")
            print(f"  File path: {missing_path}")
            print(f"  File exists: {missing_path.exists()}")
            
            _print_subsection("Step 2: Error Handling")
            print("  What should happen:")
            print("    • load_trace() checks if file exists")
            print("    • File doesn't exist → raises FileNotFoundError")
            print("    • This prevents silent failures")
            print("\n  Attempting to load...")
            
            with self.assertRaises(FileNotFoundError) as context:
                load_trace(str(missing_path))
            
            error_msg = str(context.exception)
            print(f"\n  ✓ Exception raised: FileNotFoundError")
            print(f"  ✓ Error message: {error_msg}")
            
            print("\n✓ TEST PASSED: Missing file correctly raises FileNotFoundError")

    def test_03_integration_with_operations(self) -> None:
        """Test 3: Full workflow - load, modify, save."""
        _print_section("TEST 3: Integration - Load → Modify → Save", "═")
        
        # Initial trace
        initial_trace = {
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
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "name": "web",
                                                "resources": {
                                                    "requests": {
                                                        "cpu": "500m",
                                                        "memory": "512Mi",
                                                    }
                                                },
                                            }
                                        ]
                                    }
                                },
                            },
                        }
                    ],
                }
            ],
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.msgpack"
            output_path = Path(tmpdir) / "output.msgpack"
            
            _print_subsection("Step 1: Save Initial Trace")
            print(f"  Saving initial state to: {input_path}")
            save_trace(initial_trace, str(input_path))
            print("  ✓ Initial trace saved")
            
            # Show initial state
            cpu_initial = (
                initial_trace["events"][0]["applied_objs"][0]
                ["spec"]["template"]["spec"]["containers"][0]
                ["resources"]["requests"]["cpu"]
            )
            print(f"  Initial CPU: {cpu_initial}")
            
            _print_subsection("Step 2: Load Trace from File")
            print(f"  Loading from: {input_path}")
            loaded_trace = load_trace(str(input_path))
            print("  ✓ Trace loaded into memory")
            
            _print_subsection("Step 3: Modify Trace Using Operations")
            print("  Calling: bump_cpu_small(loaded_trace, 'web', step='500m')")
            print("\n  This modifies the dictionary in-place:")
            print("    • Finds 'web' deployment")
            print("    • Updates CPU from '500m' to '1000m'")
            print("    • Returns True (success)")
            
            changed = bump_cpu_small(loaded_trace, "web", step="500m")
            print(f"\n  Result: changed = {changed}")
            
            cpu_modified = (
                loaded_trace["events"][0]["applied_objs"][0]
                ["spec"]["template"]["spec"]["containers"][0]
                ["resources"]["requests"]["cpu"]
            )
            print(f"  Modified CPU: {cpu_modified}")
            
            _print_subsection("Step 4: Save Modified Trace")
            print(f"  Saving modified state to: {output_path}")
            save_trace(loaded_trace, str(output_path))
            print("  ✓ Modified trace saved")
            
            _print_subsection("Step 5: Verify Roundtrip")
            print("  Reloading output file to verify it was saved correctly...")
            final_trace = load_trace(str(output_path))
            
            cpu_final = (
                final_trace["events"][0]["applied_objs"][0]
                ["spec"]["template"]["spec"]["containers"][0]
                ["resources"]["requests"]["cpu"]
            )
            
            print(f"\n  Input file CPU: {cpu_initial}")
            print(f"  Modified in memory: {cpu_modified}")
            print(f"  Output file CPU: {cpu_final}")
            
            if cpu_final == cpu_modified == "1000m":
                print("\n  ✓ Complete workflow successful!")
                print("    • Load → Modify → Save → Reload works correctly")
            else:
                print("\n  ✗ Workflow failed!")
            
            self.assertEqual(cpu_final, "1000m")
            self.assertTrue(changed)
            print("\n✓ TEST PASSED: Full integration workflow successful")

    def test_04_directory_creation(self) -> None:
        """Test 4: Demonstrate automatic directory creation."""
        _print_section("TEST 4: Automatic Directory Creation", "═")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "nested" / "deep" / "trace.msgpack"
            
            _print_subsection("Step 1: Target Path with Nested Directories")
            print(f"  Target path: {nested_path}")
            print(f"  Parent directories exist: {nested_path.parent.exists()}")
            print("  (They don't exist yet)")
            
            trace_data = {"version": 1, "events": []}
            
            _print_subsection("Step 2: Save Trace")
            print("  Calling save_trace() with non-existent parent directories...")
            print("\n  What save_trace() does:")
            print("    • Calls os.makedirs(dst.parent, exist_ok=True)")
            print("    • Creates all intermediate directories if needed")
            print("    • exist_ok=True means it won't error if dirs already exist")
            print("    • Then creates and writes the file")
            
            save_trace(trace_data, str(nested_path))
            
            _print_subsection("Step 3: Verify Directories and File")
            print(f"  Parent directories exist: {nested_path.parent.exists()}")
            print(f"  File exists: {nested_path.exists()}")
            
            if nested_path.exists():
                print("\n  ✓ Directories created automatically")
                print("  ✓ File written successfully")
            
            self.assertTrue(nested_path.exists())
            self.assertTrue(nested_path.parent.exists())
            print("\n✓ TEST PASSED: Directory creation works correctly")


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
    
    print("\n" + "█" * 80)
    print("END OF TRACE I/O TEST SUITE".center(80))
    print("█" * 80)
    print("\nSummary:")
    print("  • Test 1: Demonstrated roundtrip save/load")
    print("  • Test 2: Showed error handling for missing files")
    print("  • Test 3: Full integration workflow (load → modify → save)")
    print("  • Test 4: Automatic directory creation")
    print("\nKey Concepts:")
    print("  • MessagePack: Binary format for efficient serialization")
    print("  • Roundtrip: Save and load preserve data exactly")
    print("  • In-place modification: Operations modify loaded dictionaries")
    print("  • Error handling: Missing files raise clear exceptions")

