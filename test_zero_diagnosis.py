#!/usr/bin/env python3
"""
Diagnostic test to identify why observe() returns all zeros.

Tests each potential issue:
1. Can we connect to Kubernetes API?
2. Does test-ns namespace exist?
3. Are any pods in test-ns?
4. Are pods with label app=web in test-ns?
5. Can we create/read Simulation CRs?
6. Is sk-ctrl processing simulations?
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from kubernetes import client, config
from kubernetes.client.rest import ApiException

# ============================================================
# TEST 1: Kubernetes API Connection
# ============================================================
print("\n" + "="*60)
print("TEST 1: Kubernetes API Connection")
print("="*60)

try:
    config.load_kube_config()
    v1 = client.CoreV1Api()
    custom = client.CustomObjectsApi()
    
    # Try listing namespaces to verify connection
    namespaces = v1.list_namespace(limit=5)
    print(f"✅ PASS: Connected to Kubernetes API")
    print(f"   Found {len(namespaces.items)} namespaces (showing 5)")
    for ns in namespaces.items[:5]:
        print(f"   - {ns.metadata.name}")
except Exception as e:
    print(f"❌ FAIL: Cannot connect to Kubernetes")
    print(f"   Error: {e}")
    print("\n⚠️  DIAGNOSIS: This is why you get zeros - API not accessible")
    sys.exit(1)

# ============================================================
# TEST 2: test-ns Namespace Exists
# ============================================================
print("\n" + "="*60)
print("TEST 2: test-ns Namespace Exists")
print("="*60)

try:
    ns = v1.read_namespace("test-ns")
    print(f"✅ PASS: test-ns namespace exists")
    print(f"   Status: {ns.status.phase}")
except ApiException as e:
    if e.status == 404:
        print(f"❌ FAIL: test-ns namespace does NOT exist")
        print(f"\n⚠️  DIAGNOSIS: Namespace missing - create it:")
        print(f"   kubectl create namespace test-ns")
        sys.exit(1)
    else:
        print(f"❌ FAIL: Error checking namespace: {e}")
        sys.exit(1)

# ============================================================
# TEST 3: Any Pods in test-ns
# ============================================================
print("\n" + "="*60)
print("TEST 3: Any Pods in test-ns")
print("="*60)

try:
    all_pods = v1.list_namespaced_pod(namespace="test-ns")
    if len(all_pods.items) == 0:
        print(f"❌ FAIL: No pods found in test-ns")
        print(f"\n⚠️  DIAGNOSIS: test-ns is empty - simulations not creating pods")
    else:
        print(f"✅ PASS: Found {len(all_pods.items)} pod(s) in test-ns:")
        for pod in all_pods.items:
            print(f"   - {pod.metadata.name}: {pod.status.phase}")
            if pod.metadata.labels:
                print(f"     Labels: {pod.metadata.labels}")
except Exception as e:
    print(f"❌ FAIL: Error listing pods: {e}")
    sys.exit(1)

# ============================================================
# TEST 4: Pods with Label app=web in test-ns
# ============================================================
print("\n" + "="*60)
print("TEST 4: Pods with Label app=web in test-ns")
print("="*60)

try:
    web_pods = v1.list_namespaced_pod(
        namespace="test-ns",
        label_selector="app=web"
    )
    
    if len(web_pods.items) == 0:
        print(f"❌ FAIL: No pods with label app=web in test-ns")
        print(f"\n⚠️  DIAGNOSIS: Either:")
        print(f"   1. Simulation not creating pods")
        print(f"   2. Pods created without app=web label")
        print(f"   3. Pods created in different namespace")
    else:
        print(f"✅ PASS: Found {len(web_pods.items)} pod(s) with app=web:")
        ready = 0
        pending = 0
        for pod in web_pods.items:
            phase = pod.status.phase
            print(f"   - {pod.metadata.name}: {phase}")
            if phase == "Pending":
                pending += 1
            # Check ready status
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.type == "Ready" and condition.status == "True":
                        ready += 1
                        break
        print(f"\n   Summary: ready={ready}, pending={pending}, total={len(web_pods.items)}")
except Exception as e:
    print(f"❌ FAIL: Error listing pods with label: {e}")
    sys.exit(1)

# ============================================================
# TEST 5: Simulation CRD Exists
# ============================================================
print("\n" + "="*60)
print("TEST 5: Simulation CRD Exists")
print("="*60)

try:
    api_ext = client.ApiextensionsV1Api()
    crd = api_ext.read_custom_resource_definition("simulations.simkube.io")
    print(f"✅ PASS: Simulation CRD exists")
    print(f"   Group: simkube.io")
    print(f"   Version: {crd.spec.versions[0].name if crd.spec.versions else 'unknown'}")
except ApiException as e:
    if e.status == 404:
        print(f"❌ FAIL: Simulation CRD not found")
        print(f"\n⚠️  DIAGNOSIS: SimKube not installed")
        sys.exit(1)
    else:
        print(f"❌ FAIL: Error checking CRD: {e}")
        sys.exit(1)

# ============================================================
# TEST 6: SimKube Controllers Running
# ============================================================
print("\n" + "="*60)
print("TEST 6: SimKube Controllers Running")
print("="*60)

try:
    sk_pods = v1.list_namespaced_pod(namespace="simkube")
    
    if len(sk_pods.items) == 0:
        print(f"❌ FAIL: No SimKube controller pods found")
        print(f"\n⚠️  DIAGNOSIS: SimKube controllers not running")
    else:
        print(f"✅ PASS: Found {len(sk_pods.items)} SimKube pod(s):")
        all_running = True
        for pod in sk_pods.items:
            status = "Running" if pod.status.phase == "Running" else pod.status.phase
            symbol = "✅" if pod.status.phase == "Running" else "❌"
            print(f"   {symbol} {pod.metadata.name}: {status}")
            if pod.status.phase != "Running":
                all_running = False
        
        if not all_running:
            print(f"\n⚠️  WARNING: Some SimKube pods are not Running")
except ApiException as e:
    if e.status == 404:
        print(f"❌ FAIL: simkube namespace not found")
        print(f"\n⚠️  DIAGNOSIS: SimKube not installed")
    else:
        print(f"❌ FAIL: Error checking SimKube pods: {e}")

# ============================================================
# TEST 7: Recent Simulation Activity
# ============================================================
print("\n" + "="*60)
print("TEST 7: Recent Simulation Activity")
print("="*60)

try:
    sims = custom.list_cluster_custom_object(
        group="simkube.io",
        version="v1",
        plural="simulations"
    )
    
    items = sims.get("items", [])
    if len(items) == 0:
        print(f"⚠️  INFO: No active simulations found")
        print(f"   This is expected if no simulation is currently running")
    else:
        print(f"✅ Found {len(items)} simulation(s):")
        for sim in items:
            name = sim.get("metadata", {}).get("name", "unknown")
            state = sim.get("status", {}).get("state", "unknown")
            print(f"   - {name}: {state}")
except Exception as e:
    print(f"⚠️  Cannot list simulations: {e}")

# ============================================================
# TEST 8: Check Default Namespace (Trace Says "default")
# ============================================================
print("\n" + "="*60)
print("TEST 8: Pods in 'default' Namespace (trace uses this)")
print("="*60)

try:
    default_pods = v1.list_namespaced_pod(
        namespace="default",
        label_selector="app=web"
    )
    
    if len(default_pods.items) > 0:
        print(f"⚠️  FOUND: {len(default_pods.items)} pod(s) with app=web in 'default':")
        for pod in default_pods.items:
            print(f"   - {pod.metadata.name}: {pod.status.phase}")
        print(f"\n⚠️  DIAGNOSIS: Pods are in 'default' but observe() checks 'test-ns'")
        print(f"   FIX: Either:")
        print(f"   1. Change observe(namespace='default') in one_step.py")
        print(f"   2. Change trace to use namespace='test-ns'")
    else:
        print(f"✅ No pods with app=web in 'default' (as expected)")
except Exception as e:
    print(f"❌ Error checking default namespace: {e}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

print("\nTo get non-zero observations, you need:")
print("1. ✅ Kubernetes API accessible")
print("2. ✅ test-ns namespace exists")
print("3. ❓ Pods created in test-ns with label app=web")
print("4. ✅ SimKube CRD installed")
print("5. ❓ SimKube controllers running")
print("6. ❓ Simulations actually creating pods")

print("\nMost likely issue:")
print("⚠️  SimKube driver is not creating pods from the trace")
print("\nNext steps:")
print("1. Check sk-ctrl logs: kubectl logs -n simkube -l app=sk-ctrl --tail=100")
print("2. Create a simulation and watch: kubectl get simulations -w")
print("3. Check driver pods: kubectl get pods -A | grep driver")

print("\n" + "="*60)
