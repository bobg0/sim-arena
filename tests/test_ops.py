from __future__ import annotations

import copy
import unittest

from env.actions.ops import (
    bump_cpu_small,
    bump_mem_small,
    reduce_cpu_small,
    reduce_mem_small,
    scale_up_replicas,
    scale_down_replicas,
)


def _sample_trace() -> dict:
    return {
        "version": 1,
        "events": [
            {
                "ts": 1,
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


class OpsTestCase(unittest.TestCase):
    def test_bump_cpu_small(self) -> None:
        trace = _sample_trace()
        changed = bump_cpu_small(trace, "web")
        self.assertTrue(changed)
        cpu = trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"]
        self.assertEqual(cpu, "1000m")

    def test_bump_mem_small(self) -> None:
        trace = _sample_trace()
        changed = bump_mem_small(trace, "web")
        self.assertTrue(changed)
        mem = trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["memory"]
        self.assertEqual(mem, "768Mi")

    def test_scale_up_replicas(self) -> None:
        trace = _sample_trace()
        changed = scale_up_replicas(trace, "web", delta=2)
        self.assertTrue(changed)
        replicas = trace["events"][0]["applied_objs"][0]["spec"]["replicas"]
        self.assertEqual(replicas, 4)

    def test_reduce_cpu_small(self) -> None:
        trace = _sample_trace()
        changed = reduce_cpu_small(trace, "web", step="500m")
        self.assertTrue(changed)
        cpu = trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"]
        # 500m - 500m = 0, floor is 50m -> 50m
        self.assertEqual(cpu, "50m")

    def test_reduce_mem_small(self) -> None:
        trace = _sample_trace()
        changed = reduce_mem_small(trace, "web", step="256Mi")
        self.assertTrue(changed)
        mem = trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["memory"]
        self.assertEqual(mem, "256Mi")  # 512Mi - 256Mi = 256Mi

    def test_scale_down_replicas(self) -> None:
        trace = _sample_trace()
        changed = scale_down_replicas(trace, "web", delta=1)
        self.assertTrue(changed)
        replicas = trace["events"][0]["applied_objs"][0]["spec"]["replicas"]
        self.assertEqual(replicas, 1)

    def test_reduce_cpu_respects_floor(self) -> None:
        trace = _sample_trace()
        # Set CPU to 100m, reduce by 500m -> would go to -400, floor is 50m
        trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "100m"
        changed = reduce_cpu_small(trace, "web", step="500m", floor_m=50)
        self.assertTrue(changed)
        cpu = trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"]
        self.assertEqual(cpu, "50m")

    def test_scale_down_respects_floor(self) -> None:
        trace = _sample_trace()
        trace["events"][0]["applied_objs"][0]["spec"]["replicas"] = 1
        changed = scale_down_replicas(trace, "web", delta=2, floor=1)
        self.assertFalse(changed)  # 1 - 2 would be -1, floor is 1, so no change

    def test_deployment_not_found_leaves_trace_unchanged(self) -> None:
        trace = _sample_trace()
        before = copy.deepcopy(trace)
        changed = bump_cpu_small(trace, "api")
        self.assertFalse(changed)
        self.assertEqual(trace, before)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

