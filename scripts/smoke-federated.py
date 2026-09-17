#!/usr/bin/env python3
"""Real federated TinyLlama smoke test through the local website API.

Creates three consented synthetic datasets of different sizes, trains a global
adapter over multiple rounds, verifies inheritance and weighted aggregation,
checks participant/guest inference, then revokes guest access. Keeps artifacts
for inspection under ignored .local/; it never publishes a remote model.
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.data import sample_rows, split_dataset

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, choices=range(2, 6), default=2)
    parser.add_argument("--steps", type=int, choices=range(1, 21), default=2)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    origin = args.url.rstrip("/")
    with httpx.Client(base_url=origin + "/api", timeout=600,
                      headers={"Origin": origin, "Sec-Fetch-Site": "same-origin"}) as client:
        def login(school):
            client.post("/auth/login", json={"account": school, "password": os.environ.get("CAMPUS_DEMO_PASSWORD", "local-lab")}).raise_for_status()

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        login("uga")
        created = request("POST", "/federations", json={"name": "Federated STEM verification", "rounds": args.rounds, "local_steps": args.steps})
        fid = created["id"]
        sizes = {"uga": 24, "gatech": 18, "emory": 12}
        expected = {}
        for school, count in sizes.items():
            login(school)
            rows = sample_rows(school)[:count]
            training, evaluation = split_dataset(rows)
            expected[school] = {"train": len(training), "eval": len(evaluation)}
            dataset = request("POST", "/datasets", files={"file": (f"federated-{school}-{count}.jsonl", "\n".join(json.dumps(row) for row in rows))})
            request("POST", f"/federations/{fid}/participants", json={"dataset_id": dataset["id"], "acknowledge_risk": True})
        login("uga")
        request("POST", f"/federations/{fid}/start")
        previous = ""
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            result = next(row for row in request("GET", "/federations") if row["id"] == fid)
            if result["phase"] != previous:
                print(result["phase"], flush=True)
                previous = result["phase"]
            if result["status"] == "completed":
                break
            if result["status"] == "failed":
                raise RuntimeError(result["error"])
            time.sleep(2)
        else:
            raise TimeoutError("Federation exceeded 30 minutes; inspect the local worker.")
        assert len(result["history"]) == args.rounds
        total = sum(s["train"] for s in expected.values())
        for number, entry in enumerate(result["history"]):
            assert entry["round"] == number + 1
            assert len(entry["clients"]) == len(sizes)
            if number:
                assert entry["start_sha256"] == result["history"][number - 1]["adapter_sha256"]
            for member in entry["clients"]:
                counts = expected[member["school_id"]]
                assert member["train_examples"] == counts["train"]
                assert member["eval_examples"] == counts["eval"]
                assert math.isclose(member["weight"], counts["train"] / total)
                assert member["start_sha256"] == entry["start_sha256"]
                assert member["update_sha256"] != entry["start_sha256"]
            pooled = sum(c["global"]["loss"] * c["global"]["tokens"] for c in entry["clients"]) / sum(c["global"]["tokens"] for c in entry["clients"])
            assert abs(pooled - entry["global"]["loss"]) < .000011
        metrics = result["metrics"]
        assert metrics["train_examples"] == total
        assert metrics["eval_examples"] == sum(s["eval"] for s in expected.values())
        assert metrics["tuned"] == result["history"][-1]["global"]
        assert metrics["baseline"]["tokens"] == metrics["tuned"]["tokens"] > 0
        report = request("GET", f"/federations/{fid}/evaluation")
        assert all("dataset_id" not in p for p in report["participants"])
        assert "samples" not in report["metrics"]
        for school in sizes:
            login(school)
            assert fid in {m["id"] for m in request("GET", "/models")}
        answer = request("POST", "/chat", json={"model_id": fid, "prompt": "Explain why evidence matters in science."})
        assert answer["answer"]
        login("user")
        assert client.post("/chat", json={"model_id": fid, "prompt": "hello"}).status_code == 404
        assert client.get(f"/federations/{fid}/evaluation").status_code == 404
        login("uga")
        request("PATCH", f"/federations/{fid}/sharing", json={"shared": True, "acknowledge_risk": True})
        try:
            login("user")
            guest_answer = request("POST", "/chat", json={"model_id": fid, "prompt": "Explain why evidence matters in science."})
            assert guest_answer["answer"] == answer["answer"]
            assert request("GET", f"/federations/{fid}/evaluation")["metrics"] == metrics
        finally:
            login("gatech")
            request("PATCH", f"/federations/{fid}/sharing", json={"shared": False})
        login("user")
        assert fid not in {m["id"] for m in request("GET", "/models")}
        assert client.post("/chat", json={"model_id": fid, "prompt": "hello"}).status_code == 404
        output = Path(__file__).resolve().parents[1] / ".local" / "federated-verification.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps({"federation": report, "inference_seconds": answer["seconds"], "guest_access_revoked": True}, indent=2))
        print(f"Verified {fid}: {metrics['baseline']['loss']} -> {metrics['tuned']['loss']} on {metrics['device']}. {args.rounds} rounds, weights {[expected[s]['train'] / total for s in sizes]}. Report: {output}", flush=True)


if __name__ == "__main__":
    main()
