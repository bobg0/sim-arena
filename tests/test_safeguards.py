#!/usr/bin/env python3
"""
Quick test to verify safeguards are working correctly.
This script tests that actions get blocked when they would exceed resource caps.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from runner.safeguards import (
    validate_action,
    parse_cpu_to_millicores,
    parse_memory_to_bytes,
    MAX_CPU_MILLICORES,
    MAX_MEMORY_BYTES,
    MAX_REPLICAS
)

def test_cpu_validation():
    """Test CPU cap enforcement"""
    print("Testing CPU validation...")
    
    # Test 1: Safe action (current: 8000m, bump: 500m -> 8500m < 16000m)
    action = {"type": "bump_cpu_small", "step": "500m"}
    current_state = {"cpu": "8000m", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Should allow safe CPU bump"
    print("  ✓ Safe CPU bump: PASS")
    
    # Test 2: Unsafe action (current: 15500m, bump: 1000m -> 16500m > 16000m)
    action = {"type": "bump_cpu_small", "step": "1000m"}
    current_state = {"cpu": "15500m", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == False, "Should block unsafe CPU bump"
    assert "exceed" in error.lower(), "Error message should mention exceeding limit"
    print("  ✓ Unsafe CPU bump blocked: PASS")
    print(f"    Error: {error}")
    
    # Test 3: Edge case (exactly at limit)
    action = {"type": "bump_cpu_small", "step": "500m"}
    current_state = {"cpu": "15500m", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Should allow bump to exactly the limit"
    print("  ✓ Exactly at limit: PASS")

def test_memory_validation():
    """Test memory cap enforcement"""
    print("\nTesting memory validation...")
    
    # Test 1: Safe action
    action = {"type": "bump_mem_small", "step": "256Mi"}
    current_state = {"cpu": "1", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Should allow safe memory bump"
    print("  ✓ Safe memory bump: PASS")
    
    # Test 2: Unsafe action (current: 31Gi, bump: 2Gi -> 33Gi > 32Gi)
    action = {"type": "bump_mem_small", "step": "2Gi"}
    current_state = {"cpu": "1", "memory": "31Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == False, "Should block unsafe memory bump"
    print("  ✓ Unsafe memory bump blocked: PASS")
    print(f"    Error: {error}")

def test_replica_validation():
    """Test replica cap enforcement"""
    print("\nTesting replica validation...")
    
    # Test 1: Safe action
    action = {"type": "scale_up_replicas", "delta": 1}
    current_state = {"cpu": "1", "memory": "1Gi", "replicas": 5}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Should allow safe replica scale"
    print("  ✓ Safe replica scale: PASS")
    
    # Test 2: Unsafe action (current: 99, delta: 2 -> 101 > 100)
    action = {"type": "scale_up_replicas", "delta": 2}
    current_state = {"cpu": "1", "memory": "1Gi", "replicas": 99}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == False, "Should block unsafe replica scale"
    print("  ✓ Unsafe replica scale blocked: PASS")
    print(f"    Error: {error}")

def test_reduce_validation():
    """Test reduce action floor enforcement"""
    print("\nTesting reduce actions...")

    # reduce_cpu: 100m - 500m would go below 50m floor
    action = {"type": "reduce_cpu_small", "step": "500m"}
    current_state = {"cpu": "100m", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == False, "Should block reduce_cpu that goes below floor"
    assert "floor" in error.lower(), "Error should mention floor"
    print("  ✓ reduce_cpu below floor blocked: PASS")

    # reduce_cpu: 1000m - 500m = 500m, OK
    action = {"type": "reduce_cpu_small", "step": "500m"}
    current_state = {"cpu": "1000m", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Should allow reduce_cpu above floor"
    print("  ✓ reduce_cpu above floor allowed: PASS")

    # reduce_mem: 128Mi - 256Mi would go below 64Mi floor
    action = {"type": "reduce_mem_small", "step": "256Mi"}
    current_state = {"cpu": "1", "memory": "128Mi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == False, "Should block reduce_mem that goes below floor"
    print("  ✓ reduce_mem below floor blocked: PASS")

    # scale_down: 1 - 1 = 0, below MIN_REPLICAS=1
    action = {"type": "scale_down_replicas", "delta": 1}
    current_state = {"cpu": "1", "memory": "1Gi", "replicas": 1}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == False, "Should block scale_down that goes below 1"
    print("  ✓ scale_down below floor blocked: PASS")

    # scale_down: 3 - 1 = 2, OK
    action = {"type": "scale_down_replicas", "delta": 1}
    current_state = {"cpu": "1", "memory": "1Gi", "replicas": 3}
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Should allow scale_down when result >= 1"
    print("  ✓ scale_down above floor allowed: PASS")


def test_noop_always_valid():
    """Test that noop is always valid"""
    print("\nTesting noop action...")
    action = {"type": "noop"}
    current_state = {"cpu": "100", "memory": "1Ti", "replicas": 1000}  # Absurd values
    is_valid, error = validate_action(action, current_state)
    assert is_valid == True, "Noop should always be valid"
    print("  ✓ Noop always valid: PASS")

def test_parsing_functions():
    """Test CPU and memory parsing"""
    print("\nTesting parsing functions...")
    
    # CPU parsing
    assert parse_cpu_to_millicores("500m") == 500
    assert parse_cpu_to_millicores("1") == 1000
    assert parse_cpu_to_millicores("2.5") == 2500
    print("  ✓ CPU parsing: PASS")
    
    # Memory parsing
    assert parse_memory_to_bytes("256Mi") == 256 * 1024**2
    assert parse_memory_to_bytes("1Gi") == 1 * 1024**3
    assert parse_memory_to_bytes("512Ki") == 512 * 1024
    print("  ✓ Memory parsing: PASS")

def main():
    print("=" * 60)
    print("SAFEGUARD VALIDATION TEST SUITE")
    print("=" * 60)
    print(f"\nConfigured limits:")
    print(f"  MAX_CPU: {MAX_CPU_MILLICORES}m (16 CPUs)")
    print(f"  MAX_MEMORY: {MAX_MEMORY_BYTES} bytes (32 GB)")
    print(f"  MAX_REPLICAS: {MAX_REPLICAS}")
    print()
    
    try:
        test_cpu_validation()
        test_memory_validation()
        test_replica_validation()
        test_reduce_validation()
        test_noop_always_valid()
        test_parsing_functions()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        return 1
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
