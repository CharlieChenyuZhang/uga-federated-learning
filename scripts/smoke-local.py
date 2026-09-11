#!/usr/bin/env python3
"""Opt-in real-model end-to-end smoke test, using only built-in synthetic data.
Creates one adapter per school, publishes UGA model access, and checks guest inference.
Usage: .venv/bin/python scripts/smoke-local.py --steps 2
Requires the complete local website (3000) and worker (8000) to be running.
"""

import argparse
import json
import os
import time
from pathlib import Path

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--steps", type=int, default=2, choices=range(2, 101))
args = parser.parse_args()
client = httpx.Client(
    base_url="http://127.0.0.1:3000/api",
    timeout=600,
    headers={"Origin": "http://127.0.0.1:3000", "Sec-Fetch-Site": "same-origin"},
)
results = []
for school in ["uga", "gatech", "emory"]:
    r = client.post(
        "/auth/login",
        json={
            "account": school,
            "password": os.environ.get("CAMPUS_DEMO_PASSWORD", "local-lab"),
        },
    )
    r.raise_for_status()
    dataset = client.post("/datasets/sample")
    dataset.raise_for_status()
    run = client.post(
        "/runs",
        json={
            "dataset_id": dataset.json()["id"],
            "steps": args.steps,
            "name": f"{school.upper()} local verification",
        },
    )
    run.raise_for_status()
    rid = run.json()["id"]
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        response = client.get("/runs")
        response.raise_for_status()
        status = next(row for row in response.json() if row["id"] == rid)
        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            raise RuntimeError(status["error"])
        time.sleep(2)
    else:
        raise TimeoutError("Training exceeded 30 minutes; inspect the worker.")
    assert (
        status["metrics"]["baseline"]["tokens"]
        == status["metrics"]["tuned"]["tokens"]
        > 0
    )
    print(
        f"{school}: {status['metrics']['baseline']['loss']} -> {status['metrics']['tuned']['loss']} on {status['metrics']['device']}",
        flush=True,
    )
    response = client.post(
        "/chat",
        json={"model_id": rid, "prompt": "Explain why evidence matters in science."},
    )
    response.raise_for_status()
    assert response.json()["answer"]
    if school == "uga":
        shared = client.patch(
            f"/runs/{rid}/sharing", json={"shared": True, "acknowledge_risk": True}
        )
        shared.raise_for_status()
    results.append(
        {
            "school": school,
            "run_id": rid,
            "metrics": {k: v for k, v in status["metrics"].items() if k != "samples"},
            "inference_seconds": response.json()["seconds"],
        }
    )
client.post(
    "/auth/login",
    json={
        "account": "user",
        "password": os.environ.get("CAMPUS_DEMO_PASSWORD", "local-lab"),
    },
).raise_for_status()
assert client.get("/datasets").status_code == 403
models = client.get("/models")
models.raise_for_status()
assert all("samples" not in m.get("metrics", {}) for m in models.json())
response = client.post(
    "/chat",
    json={
        "model_id": results[0]["run_id"],
        "prompt": "Explain why evidence matters in science.",
    },
)
response.raise_for_status()
assert response.json()["answer"]
assert (
    client.post(
        "/chat", json={"model_id": results[1]["run_id"], "prompt": "hello"}
    ).status_code
    == 404
)
Path(".local").mkdir(exist_ok=True)
Path(".local/verification.json").write_text(json.dumps(results, indent=2))
print(
    "Verified: three real adapters, guest shared inference, private model denied. Results: .local/verification.json"
)
