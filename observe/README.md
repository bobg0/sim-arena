# /observe Module

This module is responsible for the "Observe" and "Reward" steps of the agent loop. Its sole purpose is to read the state of a specific deployment in the cluster and calculate a simple, binary reward based on that observation.

## File Overview

### observe/reader.py

This file contains the logic for connecting to the Kubernetes API and reading state.

* `observe(namespace: str, deployment_name: str) -> dict`
    * Connects to the cluster using the `CoreV1Api` client.
    * Finds all pods belonging to the `deployment_name` by using a label selector (`app=<deployment_name>`).
    * Iterates over the pods to count their status.
    * **Returns:** A dictionary: `{"ready": int, "pending": int, "total": int}`.

* `current_requests(namespace: str, deploy: str) -> dict`
    * Connects to the cluster using the `AppsV1Api` client.
    * Reads the specified `deploy` object.
    * Pulls the resource requests (`cpu`, `memory`) from the *first container* in the pod template.
    * **Returns:** A dictionary: `{"cpu": "...", "memory": "..."}`.

### `observe/reward.py`

This file contains pure, stateless reward logic. It does not interact with the cluster.

* `reward(obs: dict, target_total: int, T_s: int) -> int`
    * Takes the observation dictionary from `reader.py` as input.
    * **Returns `1` (success)** only if `obs["ready"] == target_total`, `obs["total"] == target_total`, and `obs["pending"] == 0`.
    * **Returns `0` (failure)** in all other cases.

### `observe/print_obs.py`

This is a small utility script to satisfy the acceptance criteria. Its only job is to call the `observe()` function and print the resulting dictionary to the console.

We can use this to manually verify that the `reader.py` module works correctly against a live cluster.

### `observe/test_observe.py`

This file contains all the unit tests for the module.

* **Reward Tests (`test_reward_*`)**:
    * These test the `reward.py` logic.
    * They pass in different `obs` dictionaries and assert that the correct reward (`0` or `1`) is returned.
    * These tests **do not** require mocks or a cluster.

* **Reader Tests (`test_observe_*`)**:
    * These test the `reader.py` logic.
    * They use `unittest.mock.patch` to "mock" the Kubernetes API clients (`v1` and `apps_v1`).
    * This allows us to test the pod-parsing logic (e.g., "does it correctly identify a 'Pending' pod?") without needing a live Kubernetes cluster.
    * This satisfies the "mocked Kubernetes clients" acceptance check.

---

## Connecting to the rest of the project

The `/observe` component is between the simulated environment and the agent's decision-making.


**Inputs:**

1.  **Interacting with SimKube:** We do not call Diya's code directly. Diya's `sk-env` module tells the SimKube controller to create a `Simulation`. The controller then creates **real** Kubernetes Pods in the `test-ns` namespace. Our `observe` function reads these pods.
2.  **From (`/runner`):** Omar's script should **call** our `observe()` and `reward()` functions. It passes us the `namespace` and `target_total` as parameters.

**Outputs:**

1.  **To (`/runner`):**
    * The `obs` dictionary (`{"ready": ...}`) is returned to Omar's script. This is the "observation" the agent uses to make a decision.
    * The `reward` integer (`0` or `1`) is returned to Omar's script, which he then logs somewhere.

**Note that this part doesn't directly interact with the (`/actions`) or (`/ops`) components. Also do not read or create simulation custom resource definitions. Only read standard pods and deployments**

---

## Usage

This module requires the official Kubernetes client:
```bash
pip install kubernetes pytest
