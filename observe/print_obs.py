#!/usr/bin/env python3

# observe/print_obs.py
import argparse
import json
from observe.reader import observe, current_requests

# Hardcoded target deployment name
TARGET_DEPLOY = "web"

def main():
    parser = argparse.ArgumentParser(description="Print observations from a namespace.")
    parser.add_argument("--ns", type=str, required=True, help="Namespace to observe (e.g., test-ns)")
    args = parser.parse_args()

    print(f"Observing deployment '{TARGET_DEPLOY}' in namespace '{args.ns}'...")
    
    # Call your reader function
    obs = observe(namespace=args.ns, deployment_name=TARGET_DEPLOY)
    
    # Also print requests
    reqs = current_requests(namespace=args.ns, deploy=TARGET_DEPLOY)
    obs["current_requests"] = reqs
    
    # Print as a clean JSON string
    print(json.dumps(obs, indent=2))

if __name__ == "__main__":
    main()
