from __future__ import annotations

import copy
import unittest

from env.actions.ops import bump_cpu_small, bump_mem_small, scale_up_replicas


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

    def test_deployment_not_found_leaves_trace_unchanged(self) -> None:
        trace = _sample_trace()
        before = copy.deepcopy(trace)
        changed = bump_cpu_small(trace, "api")
        self.assertFalse(changed)
        self.assertEqual(trace, before)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

