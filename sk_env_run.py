#!/usr/bin/env python3
"""
sk_env_run.py — Tiny CLI to time-box a SimKube step:
create() → wait_fixed() → delete()

Examples:
  python sk_env_run.py \
    --name diag-0001 \
    --trace demo/trace-0001.msgpack \
    --ns test-ns \
    --duration 10

  # If your cluster uses a different CRD ID:
  python sk_env_run.py \
    --name diag-0002 \
    --trace demo/trace-0002.msgpack \
    --ns test-ns \
    --duration 10 \
    --group simkube.io --version v1 --plural simulations
"""

import argparse
import json
import sys
import time

# Import the helper class and the module (to override SIM_* at runtime).
from env.sim_env import SimEnv
import env.sim_env as sim_mod


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Start a SimKube Simulation (or ConfigMap fallback), wait, then delete."
    )
    # Required
    p.add_argument("--name", required=True, help="K8s object name (DNS-1123).")
    p.add_argument("--trace", required=True, help="Trace path (as seen by the driver).")
    p.add_argument("--ns", "--namespace", dest="namespace", required=True,
                   help="Target namespace.")
    p.add_argument("--duration", type=int, required=True,
                   help="Step window (seconds).")

    # Optional driver fields
    p.add_argument("--driver-image", default="ghcr.io/simkube/sk-driver:latest",
                   help="Simulation.spec.driver.image (default: sk-driver:latest).")
    p.add_argument("--driver-port", type=int, default=8080,
                   help="Simulation.spec.driver.port (default: 8080).")

    # Allow overriding CRD identifiers without editing sim_env.py
    p.add_argument("--group", default=getattr(sim_mod, "SIM_GROUP", "simkube.dev"),
                   help="CRD API group (e.g., simkube.dev, simkube.io).")
    p.add_argument("--version", default=getattr(sim_mod, "SIM_VER", "v1alpha1"),
                   help="CRD API version (e.g., v1alpha1, v1).")
    p.add_argument("--plural", default=getattr(sim_mod, "SIM_PLURAL", "simulations"),
                   help="CRD plural name (usually 'simulations').")

    # Output behavior
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON summary.")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress human-readable logs (use with --json in scripts).")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # If sim_env.py uses module-level constants, update them from CLI flags.
    sim_mod.SIM_GROUP = args.group
    sim_mod.SIM_VER = args.version
    sim_mod.SIM_PLURAL = args.plural

    # Create the helper (this will load kube config).
    env = SimEnv()

    t0 = time.time()
    handle = None
    exit_code = 0
    err_text = None

    def log(msg: str):
        if not args.quiet and not args.json:
            print(msg, flush=True)

    try:
        log(f"[1/3] create: {args.name!r} in ns {args.namespace!r} "
            f"(group={sim_mod.SIM_GROUP}, version={sim_mod.SIM_VER}, plural={sim_mod.SIM_PLURAL})")
        handle = env.create(
            name=args.name,
            trace_path=args.trace,
            namespace=args.namespace,
            duration_s=args.duration,
            driver_image=args.driver_image,
            driver_port=args.driver_port,
        )

        kind = handle.get("kind", "?")
        log(f"[2/3] wait: {args.duration}s (kind={kind})")
        env.wait_fixed(args.duration)

    except KeyboardInterrupt:
        exit_code = 130  # standard SIGINT
        err_text = "Interrupted by user (Ctrl-C)."
    except Exception as e:
        exit_code = 1
        err_text = f"{type(e).__name__}: {e}"
    finally:
        log(f"[3/3] delete: {args.name!r} (best effort)")
        if handle is not None:
            try:
                env.delete(handle)
            except Exception as e:
                # Don’t hide the original error if there was one.
                if err_text:
                    err_text += f" | delete() error: {type(e).__name__}: {e}"
                else:
                    err_text = f"delete() error: {type(e).__name__}: {e}"
                exit_code = exit_code or 1

    elapsed = round(time.time() - t0, 3)

    if args.json:
        out = {
            "name": args.name,
            "namespace": args.namespace,
            "driver_image": args.driver_image,
            "driver_port": args.driver_port,
            "group": sim_mod.SIM_GROUP,
            "version": sim_mod.SIM_VER,
            "plural": sim_mod.SIM_PLURAL,
            "duration_s": args.duration,
            "elapsed_s": elapsed,
            "kind": (handle or {}).get("kind") if handle else None,
            "ok": exit_code == 0,
            "error": err_text,
        }
        print(json.dumps(out, indent=2), flush=True)
    else:
        if exit_code == 0:
            kind = (handle or {}).get("kind", "?")
            log(f"[OK] {kind} {args.name!r} created → waited {args.duration}s → deleted "
                f"(elapsed {elapsed}s)")
        else:
            print(f"[ERROR] {err_text or 'unknown error'} (elapsed {elapsed}s)", flush=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
